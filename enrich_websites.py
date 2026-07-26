"""One-off manual enrichment: write researched company websites into the database.

Zefix/LINDAS has no website field (confirmed against the live schema) — this is the only way
to get real company websites into the reports, and it's a one-time pass, not part of the
automated weekly fetch. Re-run manually (with a fresh input file) whenever new companies show
up that you want enriched. Source files are pipe-separated `Title|URL|confidence` lines,
confidence one of HIGH/MEDIUM/NONE (NONE rows are skipped).
"""
import html
import sys
import storage

FILES_TO_TABLE = {
    "/tmp/websites_main.txt": "records",
    "/tmp/websites_dist1.txt": "distributor_records",
    "/tmp/websites_dist2.txt": "distributor_records",
}


def normalize(title: str) -> str:
    return html.unescape(title).strip().lower()


def load_mapping(path: str) -> dict:
    mapping = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) != 3:
                print(f"[enrich] skipping malformed line: {line!r}")
                continue
            title, url, confidence = parts
            if confidence == "NONE" or url == "NONE":
                continue
            mapping[normalize(title)] = url
    return mapping


def main():
    matched, unmatched = 0, []
    for path, table in FILES_TO_TABLE.items():
        mapping = load_mapping(path)
        rows = storage.all_records() if table == "records" else storage.all_distributor_records()
        db_titles = {normalize(r["title"]): r["dedup_key"] for r in rows}
        for title_norm, url in mapping.items():
            dedup_key = db_titles.get(title_norm)
            if dedup_key:
                storage.set_website(table, dedup_key, url)
                matched += 1
            else:
                unmatched.append((table, title_norm))
    print(f"[enrich] set website on {matched} record(s)")
    if unmatched:
        print(f"[enrich] {len(unmatched)} title(s) from source files had no DB match:")
        for table, title in unmatched:
            print(f"  - [{table}] {title}")


if __name__ == "__main__":
    main()
