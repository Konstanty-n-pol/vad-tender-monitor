"""Zefix company data via the public LINDAS SPARQL endpoint — no credentials required.

This replaces the original plan of using the Zefix REST API (which needs Basic Auth
credentials obtained out-of-band). LINDAS (lindas.admin.ch) is the Swiss Confederation's
Linked Data Service and exposes the Zefix commercial register as public, unauthenticated
RDF, queryable via SPARQL. Verified live on 2026-07-24 against https://lindas.admin.ch/query.

Dataset notes (also verified live):
- Company purpose text lives at schema:description (German descriptions available via
  filtering on language of schema:name; description itself has no language tag).
- schema:dateCreated exists in this graph but is dataset-level publication metadata, not a
  per-company registration date — there is no way to ask "companies registered this week"
  directly. We rely on our own storage.py dedup (data/records.sqlite3) to surface companies
  that are new *to us* on a given run, same as the other sources.
- Company URIs (https://register.ld.admin.ch/zefix/company/{id}) resolve to a human-readable
  LINDAS page when requested with Accept: text/html — used directly as the record URL.
- The endpoint is slow for a full-text regex scan across the whole company register
  (~90-210s observed) — expected and fine for a once-a-week batch job, not for interactive use.
  requests' `timeout=` is a per-read (inactivity) timeout, not a wall-clock cap, so a slow-but-
  steadily-streaming response like this one won't get killed early.
- Matching uses config.COMPANY_MATCH_TERMS, a narrower list than KEYWORDS/BRANCH_HINTS used
  elsewhere: generic terms like "ersatzteil" (spare parts) or "casting" are extremely common in
  Swiss boilerplate purpose statements ("Handel mit Waren und Ersatzteilen aller Art") and in
  unrelated industries (film/talent casting agencies) — confirmed by testing, where those terms
  pulled in travel agencies and production companies. See COMPANY_MATCH_TERMS in config.py.
- A company is included if its purpose text (schema:description) mentions ANY COMPANY_MATCH_TERMS
  hit — this covers both manufacturers/operators and distributors, since a reseller's purpose
  text ("Handel mit Mittelspannungsschaltanlagen") still names the technical domain term. On top
  of that, DISTRIBUTOR_ROLE_TERMS (config.py) is checked separately to *classify* the match in the
  digest reason as "dystrybucja/handel" vs a plain domain match — it never gates inclusion on its
  own, since role terms alone (Handel, distribution, ...) are far too generic.
- No FILTER on lang(?name): an earlier version restricted to lang(?name) IN de/fr/it (to fix an
  even earlier German-only bug that excluded Suisse Romande/Ticino companies) but that itself
  silently dropped every company whose ONLY schema:name literal has NO language tag at all —
  confirmed live for real, active companies (e.g. "Exista AG", "BIBUS AG", "avintos AG",
  "MTS Messtechnik Schaffhausen GmbH" all carry lang(?name) = "" and were being excluded
  entirely, not just mislabeled, since schema:name is a required triple pattern here). Also seen:
  legitimate hits tagged lang="en" (e.g. a German company's Swiss Zweigniederlassung). No lang
  filter at all is correct; per-language duplicate name rows are already deduped client-side in
  fetch() below.
- Companies commonly have multiple schema:name literals (per-language trade names) and multiple
  schema:additionalType labels (per-language legal form) — the un-aggregated SELECT below returns
  the full cross product of all of those per company (confirmed live: one company showed up 8x).
  Tried fixing this server-side with GROUP BY + SAMPLE(...), but that made the query time out
  (aggregation forces the server to compute the whole grouped result before it can stream
  anything back, unlike a plain SELECT+LIMIT which streams incrementally) — reverted. Instead we
  dedup client-side in fetch() by company_uri, merging keywords across the duplicate rows.
- IMPORTANT, discovered 2026-07-30: this query's results are a non-deterministic PARTIAL sample
  of matching companies, not an exhaustive scan, once the combined regex pattern gets expensive
  enough (it's ~500 chars / 100+ alternatives here). Raised LIMIT 400 -> 3000 after finding "GE
  Vernova (Switzerland) GmbH" (purpose text literally names "Schaltanlagen", an unambiguous
  match) completely absent from results — but the LIMIT wasn't the (whole) story: two back-to-
  back runs of the *identical* query, LIMIT 3000, no ORDER BY, returned 248 and then 1371
  distinct companies, and GE Vernova was missing from BOTH. Isolating the same regex pattern to
  just that one company_uri via a FILTER matches it correctly every time — so the pattern itself
  is fine; the LINDAS/Virtuoso endpoint is doing some form of early-stopping/best-effort
  evaluation on the full unordered scan under this query's cost, and which subset of the register
  it manages to evaluate before giving up varies per run. Tried adding ORDER BY ?company_uri to
  force deterministic full evaluation (same idea as `sort | uniq`) — that made the query time out
  entirely (504 after 180s), so ordering is not viable here, matching the earlier GROUP BY
  finding in this same docstring history.
  Practical consequence: no single run of fetch() should be treated as a complete list of
  matching CH companies — treat it as a large, changing sample. The weekly job's persistence
  (storage.py upserts rather than replaces) partially compensates over successive runs, but a
  one-off "how many companies match X" question needs multiple repeated runs merged together to
  approach completeness, and even then completeness isn't guaranteed. This also means every
  "confirmed live: N companies" figure recorded elsewhere in this project's history (config.py,
  session notes) was itself such a sample, not a ground-truth count.
- FIX applied 2026-08-02: split COMPANY_MATCH_TERM_GROUPS (config.py) into 5 smaller queries
  (one per category) run sequentially, results merged/deduped by company_uri, instead of one
  ~500-char/35-term combined regex. Each group's pattern is far shorter, which should make the
  per-query cost (and therefore the non-determinism above) much less likely to bite — verified
  live by running fetch() twice in a row and confirming both the company count and the presence
  of "GE Vernova (Switzerland) GmbH" were stable across both runs. This does NOT prove the
  endpoint is now deterministic in general, just that it held up for this term set at this size
  — re-verify (run fetch() twice, diff the results) if COMPANY_MATCH_TERM_GROUPS grows
  significantly.
"""
import re
import requests
from datetime import date
from sources import Record
from config import COMPANY_MATCH_TERM_GROUPS
from filters import (
    match_company_purpose, match_distributor_role, match_manufacturing,
    classify_commodity_tier, classify_activity_category,
)

ENDPOINT = "https://lindas.admin.ch/query"
TIMEOUT = 150  # the full-register regex scan is genuinely slow, see module docstring

_QUERY_TEMPLATE = """
PREFIX schema: <http://schema.org/>
PREFIX admin: <https://schema.ld.admin.ch/>
SELECT ?company_uri ?name ?description ?company_type ?municipality ?street ?locality WHERE {{
  ?company_uri a admin:ZefixOrganisation ;
       schema:name ?name ;
       schema:description ?description .
  FILTER regex(str(?description), "{pattern}", "i")
  OPTIONAL {{ ?company_uri admin:municipality ?muni_id . ?muni_id schema:name ?municipality . }}
  OPTIONAL {{
    ?company_uri schema:additionalType ?type_id .
    ?type_id schema:name ?company_type .
    FILTER(lang(?company_type) = "de" || lang(?company_type) = "fr" || lang(?company_type) = "it")
  }}
  OPTIONAL {{
    ?company_uri schema:address ?adr .
    ?adr schema:streetAddress ?street ; schema:addressLocality ?locality .
  }}
}}
LIMIT 3000
"""


def _sparql_regex_escape(term: str) -> str:
    """Escape regex metacharacters for a SPARQL string literal. NOTE: don't use re.escape() —
    it backslash-escapes spaces too, which the SPARQL string lexer rejects outright."""
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", term)


def _build_pattern(terms) -> str:
    flat = set()
    for kw in terms:
        flat.update(kw) if isinstance(kw, tuple) else flat.add(kw)
    return "|".join(_sparql_regex_escape(t) for t in sorted(flat))


def _fetch_group(group_name: str, terms: list) -> list:
    """Run one SPARQL query scoped to a single term group. Returns raw bindings, or [] on
    failure (a failed group shouldn't take down the whole fetch)."""
    query = _QUERY_TEMPLATE.format(pattern=_build_pattern(terms))
    try:
        resp = requests.post(
            ENDPOINT,
            data=query.encode("utf-8"),
            headers={
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
    except requests.RequestException as e:
        print(f"[zefix] group '{group_name}' SPARQL query failed: {e}")
        return []
    print(f"[zefix] group '{group_name}': {len(bindings)} raw row(s)")
    return bindings


def fetch() -> list:
    records = []

    # Dedup by company_uri across ALL groups: the query returns one row per (name-language x
    # legal-form-language) combination for the same company, see module docstring, and a company
    # can legitimately match more than one group. Merge all variants' name/description text so
    # we don't lose a keyword that only shows up in e.g. the French name/description.
    by_company = {}
    for group_name, terms in COMPANY_MATCH_TERM_GROUPS.items():
        print(f"[zefix] querying group '{group_name}' ({len(terms)} term(s))...")
        for b in _fetch_group(group_name, terms):
            uri = b.get("company_uri", {}).get("value", "")
            name = b.get("name", {}).get("value", "")
            if not uri or not name:
                continue
            entry = by_company.setdefault(uri, {
                "names": [], "descriptions": set(), "company_type": "", "place": "",
            })
            entry["names"].append(name)
            desc = b.get("description", {}).get("value", "")
            if desc:
                entry["descriptions"].add(desc)
            if not entry["company_type"]:
                entry["company_type"] = b.get("company_type", {}).get("value", "")
            if not entry["place"]:
                entry["place"] = b.get("municipality", {}).get("value", "") or b.get("locality", {}).get("value", "")

    today = date.today().isoformat()
    for uri, entry in by_company.items():
        name = entry["names"][0]
        description = " ".join(entry["descriptions"])
        matched = match_company_purpose(*entry["names"], description)
        if not matched:
            continue  # re-confirm in Python; the SPARQL side uses the same term list but re-checking is cheap and safe
        role_matched = match_distributor_role(*entry["names"], description)
        manufacturing_matched = match_manufacturing(*entry["names"], description)

        company_type = entry["company_type"]
        place = entry["place"]
        buyer_context = f"{company_type}, {place}".strip(", ") if (company_type or place) else None

        # Manufacturing-specific terms outrank the generic distributor-role label — see
        # MANUFACTURING_TERMS docstring in config.py.
        if manufacturing_matched:
            reason = f"producent/obróbka mechaniczna ({manufacturing_matched[0]}) + {matched[0]}"
        elif role_matched:
            reason = f"dystrybucja/handel ({role_matched[0]}) + {matched[0]}"
        else:
            reason = f"cel działalności zawiera: {matched[0]}"
        if place:
            reason += f"; {place}"

        all_matched = matched + role_matched + manufacturing_matched
        records.append(Record(
            title=name,
            url=uri,
            source="zefix",
            country="CH",
            category="company",
            date_found=today,
            buyer=buyer_context,
            keywords_matched=all_matched,
            reason=reason,
            commodity_tier=classify_commodity_tier(all_matched),
            activity_category=classify_activity_category(all_matched),
        ))
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
