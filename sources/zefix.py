"""Zefix REST API — new/changed Swiss company entries in relevant branches.

Requires credentials (HTTP Basic, scheme "Zefix-Credentials" per the OpenAPI spec at
https://www.zefix.admin.ch/ZefixPublicREST/swagger-ui/index.html). Community wrapper docs
(e.g. github.com/jschwendener/zefix-php) point to zefix@bj.admin.ch to request access —
unverified against an official page, worth double-checking when you write. Set env vars
ZEFIX_USER / ZEFIX_PASS once you have them.

Two-step fetch, confirmed against the live OpenAPI schema on 2026-07-23:
1. GET /sogc/bydate/{date} -> SogcPublicationAndCompanyShort[], name + ehraid only
   (CompanyShort has no `purpose` or `cantonalExcerptWeb` field).
2. GET /company/ehraid/{id} -> CompanyFull, which has `purpose` (for branch matching) and
   `cantonalExcerptWeb` (link to the full cantonal register extract — the "cantonal excerpt"
   view on the Zefix website that shows fuller company background).
Step 2 only runs for companies whose name alone doesn't already rule them out, to keep the
number of extra requests bounded.
"""
import os
from datetime import date
import requests
from sources import Record
from filters import match_branch, match_keywords

BASE_URL = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"


def fetch() -> list:
    user = os.environ.get("ZEFIX_USER")
    pw = os.environ.get("ZEFIX_PASS")
    if not user or not pw:
        print("[zefix] skipped: ZEFIX_USER/ZEFIX_PASS not set (see module docstring)")
        return []

    auth = (user, pw)
    records = []
    today = date.today()
    try:
        resp = requests.get(f"{BASE_URL}/sogc/bydate/{today.isoformat()}", auth=auth, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[zefix] fetch failed: {e}")
        return records

    for entry in data if isinstance(data, list) else []:
        company = entry.get("companyShort", {}) or {}
        name = company.get("name", "")
        ehraid = company.get("ehraid")
        if not name or not ehraid:
            continue

        purpose, cantonal_excerpt_url = _fetch_purpose(ehraid, auth)
        matched = match_branch(name, purpose) or match_keywords(name, purpose)
        if not matched:
            continue

        records.append(Record(
            title=name,
            url=cantonal_excerpt_url or f"https://www.zefix.ch/en/search/entity/list?name={requests.utils.quote(name)}",
            source="zefix",
            country="CH",
            category="company",
            date_found=today.isoformat(),
            keywords_matched=matched,
            reason=f"nowy/zmieniony wpis SOGC, branża/cel działalności: {matched[0]}",
        ))
    return records


def _fetch_purpose(ehraid, auth) -> tuple:
    """Second call to get CompanyFull.purpose + cantonalExcerptWeb, not present on CompanyShort."""
    try:
        resp = requests.get(f"{BASE_URL}/company/ehraid/{ehraid}", auth=auth, timeout=20)
        resp.raise_for_status()
        full = resp.json()
        return full.get("purpose", "") or "", full.get("cantonalExcerptWeb")
    except requests.RequestException as e:
        print(f"[zefix] company/ehraid/{ehraid} failed: {e}")
        return "", None


if __name__ == "__main__":
    for r in fetch():
        print(r)
