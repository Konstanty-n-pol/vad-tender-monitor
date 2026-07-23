"""Zefix REST API — new/changed Swiss company entries in relevant branches.

Requires credentials (HTTP Basic). Request access by emailing zefix@bj.admin.ch (free).
Set env vars ZEFIX_USER / ZEFIX_PASS once you have them.
Verified live: base URL + endpoint shape confirmed against
https://www.zefix.admin.ch/ZefixPublicREST/v3/api-docs on 2026-07-23; auth not yet obtained
so response shape for /sogc/bydate is inferred from the OpenAPI spec, not a live call.
"""
import os
from datetime import date, timedelta
import requests
from sources import Record
from filters import match_branch, match_keywords

BASE_URL = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"


def fetch() -> list:
    user = os.environ.get("ZEFIX_USER")
    pw = os.environ.get("ZEFIX_PASS")
    if not user or not pw:
        print("[zefix] skipped: ZEFIX_USER/ZEFIX_PASS not set (request credentials from zefix@bj.admin.ch)")
        return []

    records = []
    today = date.today()
    try:
        resp = requests.get(
            f"{BASE_URL}/sogc/bydate/{today.isoformat()}",
            auth=(user, pw),
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[zefix] fetch failed: {e}")
        return records

    for entry in data if isinstance(data, list) else []:
        company = entry.get("companyShort", {}) or {}
        name = company.get("name", "")
        purpose = company.get("purpose", "") or ""
        canton = company.get("cantonalExcerptWeb") or company.get("registryOffice", "")
        if not name:
            continue
        matched = match_branch(name, purpose) or match_keywords(name, purpose)
        if not matched:
            continue
        uid = company.get("uid", "")
        records.append(Record(
            title=name,
            url=f"https://www.zefix.ch/en/search/entity/list?name={requests.utils.quote(name)}",
            source="zefix",
            country="CH",
            category="company",
            date_found=today.isoformat(),
            keywords_matched=matched,
            reason=f"nowy/zmieniony wpis SOGC, branża: {matched[0]}",
        ))
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
