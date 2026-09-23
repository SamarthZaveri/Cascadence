import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from app.services.ingestion.http_client import SourceClient, SourceError


class SecEdgar:
    def __init__(self, client: SourceClient):
        self.client = client

    def company_directory(self) -> list[dict]:
        data = self.client.json("https://www.sec.gov/files/company_tickers.json", ttl=86400)
        if not isinstance(data, dict):
            raise SourceError("Unexpected SEC directory shape")
        return [
            {"cik": str(row["cik_str"]).zfill(10), "ticker": row["ticker"], "name": row["title"]}
            for row in data.values()
        ]

    def fetch_filing_index(self, cik: str) -> dict:
        if not re.fullmatch(r"\d{1,10}", cik):
            raise ValueError("CIK must be 1–10 digits")
        return self.client.json(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json")

    def latest_annual_filing(self, cik: str, profile: dict) -> dict:
        candidates = self._annual_rows(cik, profile.get("filings", {}).get("recent", {}))
        if not candidates:
            for segment in profile.get("filings", {}).get("files", [])[:3]:
                name = segment["name"]
                if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name):
                    continue
                candidates.extend(
                    self._annual_rows(
                        cik, self.client.json(f"https://data.sec.gov/submissions/{name}", ttl=86400)
                    )
                )
                if candidates:
                    break
        if not candidates:
            raise SourceError("No supported annual filing found (10-K, 20-F, 40-F)")
        return max(candidates, key=lambda row: (row["filing_date"], row["accession"]))

    @staticmethod
    def _annual_rows(cik: str, data: dict) -> list[dict]:
        rows = []
        for i, form in enumerate(data.get("form", [])):
            if form not in {"10-K", "20-F", "40-F"}:
                continue
            accession, document = data["accessionNumber"][i], data["primaryDocument"][i]
            if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                raise SourceError("Invalid SEC accession")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", document):
                raise SourceError("Invalid primary document")
            date = data["filingDate"][i]
            rows.append(
                {
                    "accession": accession,
                    "form": form,
                    "filing_date": date,
                    "observed_at": datetime.fromisoformat(date).replace(tzinfo=UTC),
                    "url": (
                        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                        f"{accession.replace('-', '')}/{document}"
                    ),
                }
            )
        return rows

    def fetch_filing_text(self, url: str) -> str:
        if not re.fullmatch(r"https://www\.sec\.gov/Archives/edgar/data/\d+/\d{18}/[\w.-]+", url):
            raise SourceError("Invalid SEC filing URL")
        soup = BeautifulSoup(self.client.get(url, ttl=365 * 86400), "html.parser")
        for element in soup(["script", "style", "noscript", "ix:header"]):
            element.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
        if len(text) < 300:
            raise SourceError("Filing text was empty or too short")
        return text
