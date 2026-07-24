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
"""
import re
import requests
from datetime import date
from sources import Record
from config import COMPANY_MATCH_TERMS
from filters import match_company_purpose

ENDPOINT = "https://lindas.admin.ch/query"
TIMEOUT = 150  # the full-register regex scan is genuinely slow, see module docstring

_QUERY_TEMPLATE = """
PREFIX schema: <http://schema.org/>
PREFIX admin: <https://schema.ld.admin.ch/>
SELECT ?company_uri ?name ?description ?company_type ?municipality ?street ?locality WHERE {{
  ?company_uri a admin:ZefixOrganisation ;
       schema:name ?name ;
       schema:description ?description .
  FILTER(lang(?name) = "de")
  FILTER regex(str(?description), "{pattern}", "i")
  OPTIONAL {{ ?company_uri admin:municipality ?muni_id . ?muni_id schema:name ?municipality . }}
  OPTIONAL {{
    ?company_uri schema:additionalType ?type_id .
    ?type_id schema:name ?company_type .
    FILTER(lang(?company_type) = "de")
  }}
  OPTIONAL {{
    ?company_uri schema:address ?adr .
    ?adr schema:streetAddress ?street ; schema:addressLocality ?locality .
  }}
}}
LIMIT 200
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

    today = date.today().isoformat()
    for b in data.get("results", {}).get("bindings", []):
        name = b.get("name", {}).get("value", "")
        description = b.get("description", {}).get("value", "")
        if not name:
            continue
        matched = match_company_purpose(name, description)
        if not matched:
            continue  # re-confirm in Python; the SPARQL side uses the same term list but re-checking is cheap and safe

        company_type = b.get("company_type", {}).get("value", "")
        municipality = b.get("municipality", {}).get("value", "")
        locality = b.get("locality", {}).get("value", "")
        place = municipality or locality
        buyer_context = f"{company_type}, {place}".strip(", ") if (company_type or place) else None

        records.append(Record(
            title=name,
            url=b.get("company_uri", {}).get("value", ""),
            source="zefix",
            country="CH",
            category="company",
            date_found=today,
            buyer=buyer_context,
            keywords_matched=matched,
            reason=f"cel działalności zawiera: {matched[0]}" + (f"; {place}" if place else ""),
        ))
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
