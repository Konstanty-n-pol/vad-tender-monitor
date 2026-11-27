"""TED (Tenders Electronic Daily) Search API — no auth required.

Verified live against POST https://api.ted.europa.eu/v3/notices/search on 2026-07-23.
Docs: https://docs.ted.europa.eu/api/latest/search.html
"""
import requests
from datetime import date
from sources import Record
from config import (
    ALL_KEYWORDS, KEYWORDS_STARLINK, STARLINK_SEARCH_PHRASES_TED, STARLINK_TED_COUNTRIES, STARLINK_SOURCES,
)
from filters import match_keywords
from config import STARLINK_ACCESSORY_TERMS

BASE_URL = "https://api.ted.europa.eu/v3/notices/search"
TARGET_COUNTRIES = ["DEU", "POL"]  # switchgear group only; CH is out of scope here
STARLINK_CATEGORY = "Starlink / satellite comms"

# TED returns ISO 3166-1 alpha-3; a plain [:2] slice is wrong for e.g. PRT, AUT, SWE, SVK, SVN.
ISO3_TO_ISO2 = {
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "HRV": "HR", "CYP": "CY", "CZE": "CZ", "DNK": "DK",
    "EST": "EE", "FIN": "FI", "FRA": "FR", "DEU": "DE", "GRC": "GR", "HUN": "HU", "IRL": "IE",
    "ITA": "IT", "LVA": "LV", "LTU": "LT", "LUX": "LU", "MLT": "MT", "NLD": "NL", "POL": "PL",
    "PRT": "PT", "ROU": "RO", "SVK": "SK", "SVN": "SI", "ESP": "ES", "SWE": "SE", "NOR": "NO",
    "ISL": "IS", "LIE": "LI", "CHE": "CH", "GBR": "GB", "UKR": "UA", "MDA": "MD", "MKD": "MK",
    "ALB": "AL", "SRB": "RS", "MNE": "ME", "BIH": "BA", "GEO": "GE", "TUR": "TR",
}


def fetch() -> list:
    """Switchgear group (DEU/POL) + Starlink group (all countries), merged and deduped by URL."""
    records = _fetch_group(
        terms=ALL_KEYWORDS[:8],  # keep query bounded
        countries=TARGET_COUNTRIES,
        keywords=ALL_KEYWORDS,
    )
    if "ted" in STARLINK_SOURCES:
        seen = {r.url for r in records}
        for r in _fetch_group(
            terms=STARLINK_SEARCH_PHRASES_TED,
            countries=STARLINK_TED_COUNTRIES,
            keywords=KEYWORDS_STARLINK,
            activity_category=STARLINK_CATEGORY,
            limit=100,
        ):
            if r.url not in seen:
                seen.add(r.url)
                records.append(r)
    return records


def _fetch_group(terms, countries, keywords, activity_category: str = "", limit: int = 30) -> list:
    records = []
    query = "(" + " OR ".join(f'FT ~ "{kw}"' for kw in terms) + ")"
    if countries:
        query += " AND (" + " OR ".join(f"buyer-country={c}" for c in countries) + ")"
    # newest first, so a bounded limit still catches this week's notices
    query += " SORT BY publication-number DESC"

    try:
        resp = requests.post(
            BASE_URL,
            json={
                "query": query,
                "fields": [
                    "publication-number", "notice-title", "buyer-name",
                    "buyer-country", "deadline-date-lot", "links", "publication-date",
                ],
                "limit": limit,
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
        country_iso = ISO3_TO_ISO2.get(country, country[:2])
        if not title:
            continue
        matched = match_keywords(title, keywords=keywords)
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
            activity_category=activity_category,
            reason=(("🔌 accessories; " if activity_category and any(t in title.lower() for t in STARLINK_ACCESSORY_TERMS) else "")
                    + f"keyword: {matched[0]}; buyer: {buyer or 'n/a'}"),
        ))
    return records


PREFERRED_LANGS = ("eng", "pol", "deu")  # notice-title comes in all 24 EU languages, hun first


def _first_val(v):
    if isinstance(v, dict):
        for lang in PREFERRED_LANGS:
            val = v.get(lang)
            if isinstance(val, list) and val:
                return val[0]
            if isinstance(val, str) and val:
                return val
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
