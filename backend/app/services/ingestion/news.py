import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.ingestion.http_client import SourceClient, SourceError


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username:
        raise ValueError("Article URL must be HTTP(S)")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    )
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(query), ""))


class GdeltNews:
    def __init__(self, client: SourceClient):
        self.client = client

    def fetch_recent_events(self, keywords: str, since: datetime) -> list[dict]:
        if since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        phrase = re.sub(r"[^\w &.-]", " ", keywords).strip()
        if not phrase:
            raise ValueError("Company name is required")
        params = {
            "query": f'"{phrase}" sourcelang:english',
            "mode": "artlist",
            "format": "json",
            "maxrecords": 50,
            "sort": "datedesc",
            "startdatetime": since.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
        }
        data = self.client.json("https://api.gdeltproject.org/api/v2/doc/doc", params, ttl=900)
        return self.parse_response(data, since, datetime.now(UTC))

    @staticmethod
    def parse_response(data, since: datetime, until: datetime) -> list[dict]:
        if not isinstance(data, dict) or (data and "articles" not in data):
            raise SourceError("Unexpected GDELT response")
        articles = data.get("articles", [])
        if not isinstance(articles, list):
            raise SourceError("Invalid article list")
        rows = []
        for article in articles:
            try:
                observed = datetime.strptime(article["seendate"], "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=UTC
                )
                url = canonical_url(article["url"])
                if (
                    not isinstance(article.get("title"), str)
                    or not article["title"]
                    or observed < since
                    or observed > until
                ):
                    continue
                rows.append({**article, "url": url, "observed_at": observed})
            except (KeyError, ValueError, TypeError):
                continue
        return rows
