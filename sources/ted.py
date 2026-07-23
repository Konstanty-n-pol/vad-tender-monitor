"""TED (Tenders Electronic Daily) Search API — no auth required.

Verified live against POST https://api.ted.europa.eu/v3/notices/search on 2026-07-23.
Docs: https://docs.ted.europa.eu/api/latest/search.html
"""
import requests
from datetime import date
from sources import Record
from config import ALL_KEYWORDS
from filters import match_keywords

BASE_URL = "https://api.ted.europa.eu/v3/notices/search"
TARGET_COUNTRIES = ["DEU", "POL"]  # TED covers EU procurement; CH is out of scope here


def fetch() -> list:
    records = []
    query_terms = " OR ".join(f'FT ~ "{kw}"' for kw in ALL_KEYWORDS[:8])  # keep query bounded
    country_clause = " OR ".join(f"buyer-country={c}" for c in TARGET_COUNTRIES)
    query = f"({query_terms}) AND ({country_clause})"

    try:
        resp = requests.post(
            BASE_URL,
            json={
                "query": query,
                "fields": [
                    "publication-number", "notice-title", "buyer-name",
                    "buyer-country", "deadline-date-lot", "links",
                ],
                "limit": 30,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[ted] fetch failed: {e}")
        return records

    today = date.today().isoformat()
    for notice in data.get("notices", []):
        title = _first_val(notice.get("notice-title", {}))
        buyer = _first_val(notice.get("buyer-name", {}))
        country = _first_val(notice.get("buyer-country", {})) or ""
        country_iso = {"DEU": "DE", "POL": "PL"}.get(country, country[:2])
        if not title:
            continue
        matched = match_keywords(title)
        if not matched:
            continue
        pub_number = notice.get("publication-number", "")
        url = notice.get("links", {}).get("html", {}).get("ENG") or f"https://ted.europa.eu/en/notice/{pub_number}"
        records.append(Record(
            title=title,
            url=url,
            source="ted",
            country=country_iso,
            category="tender",
            date_found=today,
            buyer=buyer,
            keywords_matched=matched,
            reason=f"słowo kluczowe: {matched[0]}; zamawiający: {buyer or 'n/a'}",
        ))
    return records


def _first_val(v):
    if isinstance(v, dict):
        for val in v.values():
            if isinstance(val, list) and val:
                return val[0]
            if isinstance(val, str) and val:
                return val
        return ""
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


if __name__ == "__main__":
    for r in fetch():
        print(r)
