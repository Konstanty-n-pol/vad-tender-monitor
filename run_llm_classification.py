"""One-off batch run: LLM-classify every company currently in the database.

Not part of the automated weekly pipeline (main.py) — run manually whenever you want to
(re-)classify the current company list, e.g. after a fresh fetch adds new companies:

    python run_llm_classification.py

Fetches full purpose descriptions from LINDAS via a single VALUES-clause lookup by known
company URI (fast — bounded to ~190 subjects, unlike the full-corpus regex scans in
sources/zefix*.py), then classifies them all in one Message Batches run
(llm_classify.classify_companies_batch — 50% cheaper than sync calls), and writes results back
to both `records` and `distributor_records` via storage.set_llm_classification().
"""
import requests

import storage
import llm_classify

LINDAS_ENDPOINT = "https://lindas.admin.ch/query"


def fetch_descriptions(uris: list) -> dict:
    """Direct URI lookup (VALUES clause), not a full-corpus scan — fast even for ~190 companies.
    Deliberately no GROUP BY/aggregation: an earlier full-corpus query timed out when combined
    with GROUP BY (see sources/zefix.py docstring) — dedup in Python instead, same as there."""
    if not uris:
        return {}
    values = " ".join(f"<{u}>" for u in uris)
    query = f"""
    PREFIX schema: <http://schema.org/>
    SELECT ?uri ?description WHERE {{
      VALUES ?uri {{ {values} }}
      ?uri <http://schema.org/description> ?description .
    }}
    """
    resp = requests.post(
        LINDAS_ENDPOINT,
        data=query.encode("utf-8"),
        headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    result = {}
    for b in data.get("results", {}).get("bindings", []):
        uri = b["uri"]["value"]
        if uri not in result:  # first one wins, same policy as the fetch modules
            result[uri] = b["description"]["value"]
    return result


def main():
    main_companies = [r for r in storage.all_records() if r["category"] == "company"]
    distributor_companies = storage.all_distributor_records()
    print(f"[run_llm] {len(main_companies)} main-digest companies, {len(distributor_companies)} distributor-report companies")

    all_uris = list({r["url"] for r in main_companies + distributor_companies if r["url"]})
    print(f"[run_llm] fetching descriptions for {len(all_uris)} distinct compan(y/ies) from LINDAS...")
    descriptions = fetch_descriptions(all_uris)
    print(f"[run_llm] got {len(descriptions)} description(s)")

    # The Batches API requires custom_id to match ^[a-zA-Z0-9_-]{1,64}$ — dedup_key is a full URL
    # (colons/slashes/dots), so it can't be embedded directly. Use a positional index as custom_id
    # instead and keep the (table, dedup_key) mapping on the Python side.
    batch_input = []
    index_map = {}
    missing = []
    for table, rows in [("records", main_companies), ("distributor_records", distributor_companies)]:
        for r in rows:
            desc = descriptions.get(r["url"])
            if desc:
                idx = str(len(batch_input))
                batch_input.append((idx, r["title"], desc))
                index_map[idx] = (table, r["dedup_key"])
            else:
                missing.append(r["title"])

    if missing:
        print(f"[run_llm] {len(missing)} companies had no description found in LINDAS, skipping:")
        for name in missing:
            print(f"  - {name}")

    print(f"[run_llm] classifying {len(batch_input)} companies via Message Batches API...")
    results = llm_classify.classify_companies_batch(batch_input)

    written, failed = 0, 0
    for custom_id, classification in results.items():
        table, dedup_key = index_map[custom_id]
        if classification is None:
            failed += 1
            continue
        storage.set_llm_classification(table, dedup_key, classification)
        written += 1
    print(f"[run_llm] wrote {written} classification(s) to the database ({failed} failed)")


if __name__ == "__main__":
    main()
