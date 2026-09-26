"""Repeatable real SEC universe + batched ingestion; no invented company identities."""

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.config import get_settings
from app.services.ingestion.http_client import SourceClient
from app.services.ingestion.news import GdeltNews
from app.services.ingestion.repository import reconcile, save_signal, upsert_company, writer_lock
from app.services.ingestion.sec_edgar import SecEdgar

# Selection preferences only: every company is resolved against the actual SEC directory.
DEFAULT_TICKERS = (
    "AAPL MSFT NVDA AMD INTC TSM ASML AMAT LRCX KLAC MU QCOM AVGO TXN ADI NXPI "
    "ON STM AMKR GLW DELL HPE HPQ CSCO IBM ORCL GOOGL AMZN META TSLA TM HMC GM F "
    "STLA RIVN CAT DE BA AIR RTX LMT NOC GD GE HON MMM EMR ETN PH ITW UPS FDX UNP "
    "CSX NSC WAB MATX ZIM XOM CVX COP OXY SLB HAL EOG BKR VLO MPC PSX LNG EQNR "
    "SHEL BP TTE BHP RIO VALE FCX SCCO NEM GOLD NUE STLD AA CLF DOW DD LYB BASFY "
    "LIN APD SHW CTVA MOS NTR CF ADM BG CAG GIS KHC MDLZ PEP KO PG UL CL KMB "
    "WMT COST TGT HD LOW NKE SBUX MCD JNJ PFE MRK ABBV LLY NVS AZN GSK SAN "
    "JPM BAC C WFC GS MS HSBC UBS DB ING SANM SAP SONY NOK ERIC SE V BABA BIDU"
).split()

TOPICS = {
    "red-sea": '"Red Sea" (shipping OR blockade OR port)',
    "taiwan-strait": '"Taiwan Strait" (shipping OR semiconductor OR military)',
    "hormuz": '"Hormuz" (shipping OR oil OR tanker)',
    "panama-canal": '"Panama Canal" (drought OR shipping OR restrictions)',
    "black-sea": '"Black Sea" (grain OR shipping OR port)',
    "export-controls": '"export controls" (chips OR semiconductor OR minerals)',
    "critical-minerals": '"critical minerals" (supply OR ban OR mining)',
    "sanctions": '"sanctions" (trade OR shipping OR energy)',
}


class WindowedNews(GdeltNews):
    """Daily windows, capped result visibility, canonical-URL deduplication."""

    def fetch_query(self, query: str, since: datetime) -> list[dict]:
        end = datetime.now(UTC)
        cursor = since
        articles: dict[str, dict] = {}
        while cursor < end:
            until = min(cursor + timedelta(days=1), end)
            result = self.client.json(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                {
                    "query": query,
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": 250,
                    "sort": "datedesc",
                    "startdatetime": cursor.strftime("%Y%m%d%H%M%S"),
                    "enddatetime": until.strftime("%Y%m%d%H%M%S"),
                },
                ttl=900,
            )
            rows = self.parse_response(result, cursor, until)
            saturated = len(result.get("articles", [])) >= 250
            for row in rows:
                row["query_window"] = [cursor.isoformat(), until.isoformat()]
                row["query_saturated"] = saturated
                articles.setdefault(row["url"], row)
            cursor = until
        return list(articles.values())

    def fetch_recent_events(self, keywords: str, since: datetime) -> list[dict]:
        import re

        phrase = re.sub(r"[^\w &.-]", " ", keywords).strip()
        if not phrase:
            raise ValueError("Company name is required")
        return self.fetch_query(f'"{phrase}" sourcelang:english', since)


def expand(limit=100, offset=0):
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("Limit must be 1–500; offset must be nonnegative")
    client = SourceClient()
    try:
        directory = SecEdgar(client).company_directory()
    finally:
        client.close()
    by_ticker = {r["ticker"]: r for r in directory}
    resolved = [by_ticker[t] for t in DEFAULT_TICKERS if t in by_ticker]
    remainder = sorted(
        (r for r in directory if r["ticker"] not in DEFAULT_TICKERS), key=lambda r: r["ticker"]
    )
    rows = (resolved + remainder)[offset : offset + limit]
    with writer_lock():
        ids = [str(upsert_company(row)) for row in rows]
        projection = reconcile()
    body = json.dumps(directory, sort_keys=True).encode()
    manifest = {
        "source_url": "https://www.sec.gov/files/company_tickers.json",
        "downloaded_at": datetime.now(UTC).isoformat(),
        "directory_sha256": hashlib.sha256(body).hexdigest(),
        "companies": rows,
        "ids": ids,
        "offset": offset,
        "unresolved_preferred_tickers": [t for t in DEFAULT_TICKERS if t not in by_ticker],
        "coverage": "SEC-listed universe, not a global supplier census",
    }
    path = Path(get_settings().INGESTION_CACHE_DIR) / "universe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))
    return {
        "status": "success",
        "manifest": str(path),
        "companies": len(rows),
        "projection": projection,
    }


def ingest_batches(tickers, days=7):
    from app.services.ingestion.pipeline import run_ingestion_cycle, validate_tickers

    tickers = list(dict.fromkeys(tickers))
    if not 1 <= len(tickers) <= 500:
        raise ValueError("Select 1–500 tickers")
    for i in range(0, len(tickers), 5):
        validate_tickers(tickers[i : i + 5])
    runs = []
    client = SourceClient()
    try:
        for i in range(0, len(tickers), 5):
            result = run_ingestion_cycle(
                tickers[i : i + 5], days, sec=SecEdgar(client), news=WindowedNews(client)
            )
            runs.append(result)
    finally:
        client.close()
    return {
        "status": "success" if all(r["status"] == "success" for r in runs) else "partial",
        "runs": runs,
    }


def collect_topics(days=7):
    from app.services.extra_signals.pipeline import audited

    if not 1 <= days <= 30:
        raise ValueError("days must be 1–30")

    def work():
        client, saved, errors, capped = SourceClient(), 0, [], 0
        try:
            for topic, query in TOPICS.items():
                try:
                    rows = WindowedNews(client).fetch_query(
                        query, datetime.now(UTC) - timedelta(days=days)
                    )
                    for row in rows:
                        raw = {k: v for k, v in row.items() if k != "observed_at"}
                        save_signal(
                            {
                                "id": uuid5(NAMESPACE_URL, f"topic:{topic}:{row['url']}"),
                                "company_id": None,
                                "location_id": None,
                                "source_type": "news",
                                "raw_payload": raw,
                                "severity_score": None,
                                "observed_at": row["observed_at"],
                                "ingested_at": datetime.now(UTC),
                                "extracted_data": {
                                    "topic": topic,
                                    "eligible_for_scoring": False,
                                    "origin": "geopolitical_context",
                                    "observed_at_basis": "gdelt_discovery_time",
                                },
                            }
                        )
                        saved += 1
                        capped += int(row["query_saturated"])
                except Exception as exc:
                    errors.append({"source": topic, "message": str(exc)[:300]})
        finally:
            client.close()
        return {
            "observations": saved,
            "saturated_window_articles": capped,
            "coverage": "Search results; capped windows may omit articles",
        }, errors

    return audited("geopolitical_context", work)


def main():
    parser = argparse.ArgumentParser(description="Expand and refresh a real research universe")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("expand")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--offset", type=int, default=0)
    p = sub.add_parser("ingest")
    p.add_argument("--tickers", nargs="+")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=100)
    p = sub.add_parser("topics")
    p.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if args.command == "expand":
        result = expand(args.limit, args.offset)
    elif args.command == "topics":
        result = collect_topics(args.days)
    else:
        if not 1 <= args.limit <= 500 or args.offset < 0:
            parser.error("limit must be 1–500 and offset nonnegative")
        tickers = args.tickers
        if tickers is None:
            path = Path(get_settings().INGESTION_CACHE_DIR) / "universe.json"
            tickers = [c["ticker"] for c in json.loads(path.read_text())["companies"]]
        result = ingest_batches(tickers[args.offset : args.offset + args.limit], args.days)
    print(json.dumps(result, indent=2, default=str))
    if result["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
