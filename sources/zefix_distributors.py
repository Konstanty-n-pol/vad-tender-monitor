"""Separate report: Swiss distribution/broker/reseller companies in industrial-machinery or
marine/ship-equipment branches. Same LINDAS SPARQL endpoint as sources/zefix.py, see that
module's docstring for dataset notes (auth, name/type language handling, dedup-by-URI, why
GROUP BY was reverted). This module differs only in what it requires a match on:

Requested by the user as "wszystkie firmy zajmujące się dystrybucją/brokerstwem/resellingiem"
(all companies doing distribution/brokerage/reselling) — but role terms alone (Handel, Vertrieb,
distribution, ...) match ~29,900 CH companies (confirmed live, 2026-07-25), which is neither
fetchable in a weekly job nor reviewable as a report, and has nothing to do with this business.
Narrowed, per follow-up instruction, to companies whose purpose ALSO mentions industrial
machinery/equipment or marine/ship equipment (config.INDUSTRIAL_DOMAIN_TERMS) — confirmed live
at ~156 companies, a genuinely reviewable weekly size. Kept as a fully separate report (own
SQLite table via storage.upsert_distributor_records/all_distributor_records, own dashboard page,
own short email) rather than folded into the curated GIS/MV-HV digest in sources/zefix.py, so
that digest's precision/size stays untouched.
"""
import re
import requests
from datetime import date
from sources import Record
from config import INDUSTRIAL_DOMAIN_TERMS, DISTRIBUTOR_ROLE_TERMS
from filters import (
    match_industrial_domain, match_distributor_role, match_manufacturing,
    classify_commodity_tier, classify_activity_category,
)

ENDPOINT = "https://lindas.admin.ch/query"
TIMEOUT = 250  # combined two-regex query observed ~166s for a COUNT; give headroom for a full SELECT

_QUERY_TEMPLATE = """
PREFIX schema: <http://schema.org/>
PREFIX admin: <https://schema.ld.admin.ch/>
SELECT ?company_uri ?name ?description ?company_type ?municipality ?street ?locality WHERE {{
  ?company_uri a admin:ZefixOrganisation ;
       schema:name ?name ;
       schema:description ?description .
  FILTER regex(str(?description), "{domain_pattern}", "i")
  FILTER regex(str(?description), "{role_pattern}", "i")
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
LIMIT 500
"""


def _sparql_regex_escape(term: str) -> str:
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", term)


def _pattern(terms_config) -> str:
    terms = set()
    for kw in terms_config:
        terms.update(kw) if isinstance(kw, tuple) else terms.add(kw)
    return "|".join(_sparql_regex_escape(t) for t in sorted(terms))


def fetch() -> list:
    records = []
    query = _QUERY_TEMPLATE.format(
        domain_pattern=_pattern(INDUSTRIAL_DOMAIN_TERMS),
        role_pattern=_pattern(DISTRIBUTOR_ROLE_TERMS),
    )
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
        print(f"[zefix_distributors] SPARQL query failed: {e}")
        return records

    # Dedup by company_uri — see sources/zefix.py docstring for why (name/legal-form language
    # cross product).
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
        domain_matched = match_industrial_domain(*entry["names"], description)
        role_matched = match_distributor_role(*entry["names"], description)
        if not (domain_matched and role_matched):
            continue  # re-confirm both in Python; SPARQL side uses the same term lists
        manufacturing_matched = match_manufacturing(*entry["names"], description)

        company_type = entry["company_type"]
        place = entry["place"]
        buyer_context = f"{company_type}, {place}".strip(", ") if (company_type or place) else None
        # Manufacturing-specific terms (Décolletage, Feinmechanik, ...) outrank the generic
        # distributor-role label in the reason — see MANUFACTURING_TERMS docstring in config.py:
        # a real machining shop shouldn't read as "dystrybucja/handel" just because its statutory
        # purpose also carries boilerplate "Handel"/"Import/Export" language.
        if manufacturing_matched:
            reason = f"producent/obróbka mechaniczna ({manufacturing_matched[0]}) w branży: {domain_matched[0]}"
        else:
            reason = f"dystrybucja/handel ({role_matched[0]}) w branży: {domain_matched[0]}"
        if place:
            reason += f"; {place}"

        all_matched = domain_matched + role_matched + manufacturing_matched
        records.append(Record(
            title=name,
            url=uri,
            source="zefix",
            country="CH",
            category="distributor",
            date_found=today,
            buyer=buyer_context,
            keywords_matched=all_matched,
            commodity_tier=classify_commodity_tier(all_matched),
            activity_category=classify_activity_category(all_matched),
            reason=reason,
        ))
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
