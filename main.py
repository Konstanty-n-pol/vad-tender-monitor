"""Weekly pipeline: fetch all enabled sources -> filter -> dedup/store -> render -> email.

Run: python main.py
Env vars used: see mailer.py and sources/zefix.py docstrings.
"""
import os
from config import SOURCES_ENABLED
from sources import zefix, simap, ted, ezamowienia
import storage
import generate
import mailer

SOURCE_MODULES = {
    "zefix": zefix,
    "simap": simap,
    "ted": ted,
    "ezamowienia": ezamowienia,
}


def fetch_all() -> list:
    records = []
    for name, enabled in SOURCES_ENABLED.items():
        if not enabled:
            continue
        module = SOURCE_MODULES[name]
        print(f"[main] fetching {name}...")
        try:
            fetched = module.fetch()
            print(f"[main] {name}: {len(fetched)} relevant record(s)")
            records.extend(fetched)
        except Exception as e:
            print(f"[main] {name} failed: {e}")
    return records


def dedup_across_sources(records: list) -> list:
    """Same tender/company appearing under two sources -> keep first, drop rest (by title match)."""
    seen_titles = set()
    deduped = []
    for r in records:
        key = r.title.strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(r)
    return deduped


def main():
    all_records = fetch_all()
    all_records = dedup_across_sources(all_records)

    new_records = storage.upsert_records(all_records)
    print(f"[main] {len(new_records)} brand-new record(s) this run")

    generate.write_dashboard()

    dashboard_url = os.environ.get("DASHBOARD_URL", "https://<your-username>.github.io/vad-tender-monitor/")
    email_html = generate.render_email(new_records, dashboard_url)
    mailer.send_digest(email_html, has_content=bool(new_records))


if __name__ == "__main__":
    main()
