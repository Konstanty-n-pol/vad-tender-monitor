"""Weekly pipeline: fetch all enabled sources -> filter -> dedup/store -> render -> email.

Run: python main.py
Env vars used: see mailer.py and sources/zefix.py docstrings.
"""
import os
from config import SOURCES_ENABLED, DISTRIBUTOR_REPORT_ENABLED
from sources import zefix, simap, ted, ezamowienia, zefix_distributors
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


def run_distributor_report(dashboard_url: str):
    """Separate weekly report: CH distribution/broker/reseller companies in industrial-machinery
    or marine/ship-equipment branches. Independent of SOURCES_ENABLED/the main digest — see
    sources/zefix_distributors.py docstring for why this is kept apart."""
    print("[main] fetching zefix_distributors...")
    try:
        fetched = zefix_distributors.fetch()
    except Exception as e:
        print(f"[main] zefix_distributors failed: {e}")
        return
    print(f"[main] zefix_distributors: {len(fetched)} relevant record(s)")

    new_records = storage.upsert_distributor_records(fetched)
    print(f"[main] {len(new_records)} brand-new distributor record(s) this run")

    generate.write_distributors_dashboard()

    distributors_url = dashboard_url.rstrip("/") + "/distributors.html"
    email_html = generate.render_distributors_email(new_records, distributors_url)
    mailer.send_digest(email_html, has_content=bool(new_records), subject_prefix="VAD Monitor — Dystrybutorzy")


def main():
    all_records = fetch_all()
    all_records = dedup_across_sources(all_records)

    new_records = storage.upsert_records(all_records)
    print(f"[main] {len(new_records)} brand-new record(s) this run")

    generate.write_dashboard()

    dashboard_url = os.environ.get("DASHBOARD_URL", "https://<your-username>.github.io/vad-tender-monitor/")
    email_html = generate.render_email(new_records, dashboard_url)
    mailer.send_digest(email_html, has_content=bool(new_records))

    if DISTRIBUTOR_REPORT_ENABLED:
        run_distributor_report(dashboard_url)


if __name__ == "__main__":
    main()
