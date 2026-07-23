"""SIMAP.ch public tender search — no auth required for the public project-search endpoint.

Verified live against https://www.simap.ch/api/publications/v2/project/project-search on 2026-07-23.
Required query params: language, orderAddressCountryOnlySwitzerland.
NOTE: the full-text search param name is not yet confirmed (searchText had no observed filtering
effect during verification) — until confirmed against the full API docs at
https://www.simap.ch/api/specifications/, this module fetches recent publications unfiltered
and relies on our own keyword matching over the title, which is safe either way.
"""
import requests
from datetime import date
from sources import Record
from filters import match_keywords

BASE_URL = "https://www.simap.ch/api/publications/v2/project/project-search"


def fetch() -> list:
    records = []
    try:
        resp = requests.get(
            BASE_URL,
            params={
                "language": "de",
                "orderAddressCountryOnlySwitzerland": "true",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[simap] fetch failed: {e}")
        return records

    today = date.today().isoformat()
    for project in data.get("projects", []):
        title = _first_lang(project.get("title", {}))
        buyer = _first_lang(project.get("procOfficeName", {}))
        if not title:
            continue
        matched = match_keywords(title, buyer or "")
        if not matched:
            continue
        canton = (project.get("orderAddress") or {}).get("cantonId", "")
        url = f"https://www.simap.ch/en/notices/{project.get('publicationId', '')}"
        records.append(Record(
            title=title,
            url=url,
            source="simap",
            country="CH",
            category="tender",
            date_found=today,
            buyer=buyer,
            keywords_matched=matched,
            reason=f"słowo kluczowe: {matched[0]}; zamawiający: {buyer or 'n/a'} ({canton})",
        ))
    return records


def _first_lang(d: dict) -> str:
    if not d:
        return ""
    for lang in ("de", "fr", "en", "it"):
        if d.get(lang):
            return d[lang]
    return ""


if __name__ == "__main__":
    for r in fetch():
        print(r)
