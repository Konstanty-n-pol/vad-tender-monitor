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
"""
import re
import requests
from datetime import date
from sources import Record
from config import COMPANY_MATCH_TERMS
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
LIMIT 400
"""


def _sparql_regex_escape(term: str) -> str:
    """Escape regex metacharacters for a SPARQL string literal. NOTE: don't use re.escape() —
    it backslash-escapes spaces too, which the SPARQL string lexer rejects outright."""
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", term)


def _build_pattern() -> str:
    terms = set()
    for kw in COMPANY_MATCH_TERMS:
        terms.update(kw) if isinstance(kw, tuple) else terms.add(kw)
    return "|".join(_sparql_regex_escape(t) for t in sorted(terms))


def fetch() -> list:
    records = []
    query = _QUERY_TEMPLATE.format(pattern=_build_pattern())
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
        data = resp.json()
    except requests.RequestException as e:
        print(f"[zefix] SPARQL query failed: {e}")
        return records

    # Dedup by company_uri first: the query returns one row per (name-language x legal-form-
    # language) combination for the same company, see module docstring. Merge all variants'
    # name/description text before matching so we don't lose a keyword that only shows up in
    # e.g. the French name/description while keeping the first non-empty context fields.
    by_company = {}
    for b in data.get("results", {}).get("bindings", []):
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
