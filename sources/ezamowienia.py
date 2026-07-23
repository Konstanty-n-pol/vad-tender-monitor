"""e-Zamowienia (BZP) public notice endpoint.

CONFIRMED: https://ezamowienia.gov.pl/mo-board/api/v1/notice is public, no OAuth needed for reads.
BLOCKED: the `NoticeType` query param is a required enum whose accepted values were not
discoverable via trial-and-error (server returns "value not in allowed range" without listing
options). The valid values are documented in Attachment 3 to the API Usage Regulations, linked
from https://ezamowienia.gov.pl/pl/integracja/ — download that PDF and fill in NOTICE_TYPE below
before enabling this source in config.py (SOURCES_ENABLED["ezamowienia"]).
"""
import requests
from datetime import date, timedelta
from sources import Record
from filters import match_keywords

BASE_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/notice"
NOTICE_TYPE = None  # TODO: fill in once confirmed from integration docs


def fetch() -> list:
    if not NOTICE_TYPE:
        print("[ezamowienia] skipped: NOTICE_TYPE not configured, see module docstring")
        return []

    records = []
    today = date.today()
    params = {
        "PageSize": 50,
        "PageNumber": 1,
        "NoticeType": NOTICE_TYPE,
        "PublicationDateFrom": (today - timedelta(days=7)).isoformat(),
        "PublicationDateTo": today.isoformat(),
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[ezamowienia] fetch failed: {e}")
        return records

    for notice in data.get("notices", data.get("items", [])):
        title = notice.get("title", "") or notice.get("name", "")
        buyer = notice.get("buyerName", "") or notice.get("organizationName", "")
        if not title:
            continue
        matched = match_keywords(title)
        if not matched:
            continue
        notice_id = notice.get("id", "")
        records.append(Record(
            title=title,
            url=f"https://ezamowienia.gov.pl/mp-client/search/list/{notice_id}",
            source="ezamowienia",
            country="PL",
            category="tender",
            date_found=today.isoformat(),
            buyer=buyer,
            keywords_matched=matched,
            reason=f"słowo kluczowe: {matched[0]}; zamawiający: {buyer or 'n/a'}",
        ))
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
