"""Prozorro (Ukraine public procurement) public search — no auth required.

Verified live 2026-10-30 and again 2026-11-26:
  POST https://prozorro.gov.ua/api/search/tenders?text=<url-encoded phrase>&page=N
  headers: Content-Type: application/json + a browser User-Agent
  -> {page, per_page: 20, total, data: [{tenderID, title, procuringEntity{name, address{locality}},
      value{amount, currency}, status, tenderPeriod{endDate}, ...}]}
Results are ordered by relevance, NOT by date, so we can't stop paginating at the first old notice.
Instead the JSON body {"date": {"tender": {"start": "YYYY-MM-DD"}}} narrows the result set
server-side (verified 2026-11-26: "starlink" 1000 -> 207), and we still filter client-side on the
date embedded in tenderID (UA-YYYY-MM-DD-NNNNNN-x) — the authoritative window. If the server
rejects the date body we retry without it and rely on the client-side filter alone.
`total` is capped at 1000 by the API.
KNOWN ISSUE (measured 2026-11-26): relevance-sorted paging is not stable between calls — 3 back-to-
back runs returned 179/182/180 tenders, 163 common to all (~10% churn), even with every page fetched.
A date "end" bound in the body returned 0 results, so slicing into single-page windows isn't
available. Mitigation: PROZORRO_LOOKBACK_DAYS (30) >> weekly cadence, so each tender gets ~4 weekly
chances; storage dedups by URL. Rapid repeated calls trigger 429 — handled by _post() backoff. Only the "starlink" keyword group is used for this source
(see config.STARLINK_SEARCH_PHRASES_PROZORRO); the switchgear group isn't relevant for UA.
"""
import re
import time
import urllib.parse
from datetime import date, timedelta

import requests

from config import (
    KEYWORDS_STARLINK, STARLINK_SEARCH_PHRASES_PROZORRO, PROZORRO_LOOKBACK_DAYS, PROZORRO_MAX_PAGES,
)
from filters import match_keywords
from config import STARLINK_ACCESSORY_TERMS
from sources import Record

BASE_URL = "https://prozorro.gov.ua/api/search/tenders"
TENDER_URL = "https://prozorro.gov.ua/tender/{}"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
}
TENDER_ID_DATE = re.compile(r"^UA-(\d{4}-\d{2}-\d{2})-")
PAGE_DELAY_S = 0.3  # be polite to the public endpoint


def fetch(lookback_days: int = PROZORRO_LOOKBACK_DAYS, max_pages: int = PROZORRO_MAX_PAGES,
          phrases: list = None) -> list:
    since = date.today() - timedelta(days=lookback_days)
    by_id = {}  # tenderID -> (raw notice, set of phrases that found it)
    for phrase in phrases or STARLINK_SEARCH_PHRASES_PROZORRO:
        for notice in _search(phrase, since, max_pages):
            tid = notice.get("tenderID")
            if not tid:
                continue
            tender_date = _tender_date(tid)
            if tender_date is None or tender_date < since:
                continue
            by_id.setdefault(tid, (notice, set()))[1].add(phrase)

    today = date.today().isoformat()
    records = []
    for tid, (notice, found_by) in by_id.items():
        title = (notice.get("title") or "").strip()
        if not title:
            continue
        entity = notice.get("procuringEntity") or {}
        buyer = entity.get("name") or (entity.get("identifier") or {}).get("legalName")
        locality = ((entity.get("address") or {}).get("locality") or "").strip()
        matched = match_keywords(title, keywords=KEYWORDS_STARLINK)
        # The search engine also matches item descriptions/documents, so a hit whose title doesn't
        # mention Starlink (e.g. "Кабель" or a bare CPV code) is still kept — labelled as a
        # search-only hit so it's easy to tell apart in the digest.
        kw_label = matched[0] if matched else f"Prozorro search: \"{sorted(found_by)[0]}\" (not in title)"
        records.append(Record(
            title=title,
            url=TENDER_URL.format(tid),
            source="prozorro",
            country="UA",
            category="tender",
            date_found=today,
            buyer=f"{buyer} ({locality})" if buyer and locality else buyer,
            deadline=((notice.get("tenderPeriod") or {}).get("endDate") or "")[:10] or None,
            value_estimate=_format_value(notice.get("value")),
            keywords_matched=matched or ["starlink (search)"],
            activity_category="Starlink / satellite comms",
            reason=f"{_accessory_prefix(title)}{kw_label}; {tid}; status: {notice.get('status', 'n/a')}; buyer: {buyer or 'n/a'}",
        ))
    records.sort(key=lambda r: r.url, reverse=True)  # tenderIDs sort chronologically
    return records


def _search(phrase: str, since: date, max_pages: int) -> list:
    url = f"{BASE_URL}?text={urllib.parse.quote(phrase)}"
    body = {"date": {"tender": {"start": since.isoformat()}}}
    out = []
    page = 1
    while page <= max_pages:
        try:
            resp = _post(f"{url}&page={page}", body)
            if resp.status_code == 422 and body:
                print(f"[prozorro] date filter rejected for '{phrase}', retrying without it")
                body = {}
                continue
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[prozorro] fetch failed for '{phrase}' page {page}: {e}")
            break
        batch = data.get("data") or []
        out.extend(batch)
        per_page = data.get("per_page") or 20
        total = min(data.get("total") or 0, 1000)
        if not batch or page * per_page >= total:
            break
        if page == max_pages:
            print(f"[prozorro] '{phrase}': hit max_pages={max_pages} ({total} results) — raise PROZORRO_MAX_PAGES")
        page += 1
        time.sleep(PAGE_DELAY_S)
    return out


def _post(url: str, body: dict, retries: int = 4):
    """POST with backoff on 429 Too Many Requests (seen when several phrases run back to back)."""
    for attempt in range(retries + 1):
        resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
        if resp.status_code != 429 or attempt == retries:
            return resp
        wait = float(resp.headers.get("Retry-After") or 2 ** (attempt + 1))
        time.sleep(min(wait, 30))
    return resp


def _accessory_prefix(title: str) -> str:
    t = title.lower()
    return "🔌 accessories; " if any(term in t for term in STARLINK_ACCESSORY_TERMS) else ""


def _tender_date(tender_id: str):
    m = TENDER_ID_DATE.match(tender_id)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _format_value(value) -> str:
    if not value or value.get("amount") is None:
        return None
    amount = value["amount"]
    return f"{amount:,.0f}".replace(",", " ") + f" {value.get('currency', '')}".rstrip()


if __name__ == "__main__":
    for r in fetch():
        print(r)
