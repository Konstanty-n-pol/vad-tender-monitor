"""One-off lookup: cross-reference the Swiss entries from a third-party supplier landscape
research file (~/Downloads/supplier_landscape_GIS_aftermarket_new_version.xlsx, "Aman
Engineering benchmarking research") against the Zefix commercial register via LINDAS.

That file lists ~80 candidate suppliers/competitors/customers across CH, PL, UAE and other
international markets, compiled from external research — it has no Zefix URIs or UIDs, just
company names. Zefix only covers Swiss-registered entities, so the bulk of the search is the
rows whose Country / Base mentions Switzerland; it does not touch storage.py or the weekly
pipeline.

Special focus on direct competitors (per user request): rows classified "Direct Competitor" in
the sheet are currently all UAE-based (Aman Engineering Equipment LLC, RAGA Technotricks FZE) --
outside Zefix's normal CH-registered-entity scope -- but a foreign competitor can still show up
in Zefix if it has a Swiss branch (Zweigniederlassung) or subsidiary. Those rows are searched
too, regardless of Country/Base, and reported in their own section so a "no match" there reads
as "no Swiss presence found", not as noise mixed into the CH supplier list.

Run manually:

    python search_supplier_landscape.py

Search strategy: build one cleaned "core term" per supplier (strip legal-form suffixes and
generic glosses like "Switzerland"/"Suisse" that a real Zefix schema:name won't literally
contain), then run a SINGLE combined regex-alternation query against schema:name — same
endpoint/dedup pattern as sources/zefix.py, but matching on name instead of description, and a
targeted name search is far cheaper than that module's full-description scan.
"""
import re
import requests
import pandas as pd

XLSX_PATH = "/Users/kacperkonstanty/Downloads/supplier_landscape_GIS_aftermarket_new_version.xlsx"
ENDPOINT = "https://lindas.admin.ch/query"
TIMEOUT = 150

# legal-form / generic tokens stripped from the raw supplier name before building a search term
_STRIP_TOKENS = [
    "switzerland", "suisse", "svizzera", "schweiz", "global", "europe", "poland",
    "ag", "gmbh", "sa", "sàrl", "llc", "ltd", "inc", "corp", "s.a.", "sp. z o.o.",
]


def _sparql_regex_escape(term: str) -> str:
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", term)


def _core_terms(raw_name: str) -> list:
    """Return 1-2 distinctive search terms for a supplier name. Parenthetical asides in this
    file usually name the actual CH legal entity or brand behind a trade name (e.g. "Rexel
    Switzerland (Elektro-Material AG)") so each parenthetical becomes its own term too."""
    terms = []
    paren = re.findall(r"\(([^)]+)\)", raw_name)
    base = re.sub(r"\([^)]*\)", "", raw_name).strip()

    for chunk in [base] + paren:
        words = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9\-]+", chunk)
                 if w.lower() not in _STRIP_TOKENS]
        if not words:
            continue
        # keep up to the first 2 distinctive words -- enough to be specific, short enough to
        # survive minor punctuation/spacing differences between this doc and the CH register
        term = " ".join(words[:2])
        if len(term) >= 3:
            terms.append(term)
            if "-" in term:  # hyphen/space are used inconsistently between this doc and Zefix
                terms.append(term.replace("-", " "))
    return terms or [raw_name]


def load_supplier_sheet() -> pd.DataFrame:
    raw = pd.read_excel(XLSX_PATH, sheet_name="Supplier Database", header=None)
    hdr_idx = raw[raw[0] == "Supplier Name"].index[0]
    return pd.read_excel(XLSX_PATH, sheet_name="Supplier Database", header=hdr_idx)


def load_swiss_suppliers() -> pd.DataFrame:
    df = load_supplier_sheet()
    return df[df["Country / Base"].str.contains("Switzerland", na=False)].reset_index(drop=True)


def load_direct_competitors() -> pd.DataFrame:
    """Direct-competitor rows regardless of Country/Base -- searched for a CH footprint too,
    see module docstring."""
    df = load_supplier_sheet()
    return df[df["Classification"].str.contains("Direct Competitor", na=False)].reset_index(drop=True)


def search_lindas(term_map: dict) -> dict:
    """term_map: {supplier_name: [term1, term2, ...]}. One combined query, all terms
    alternated. Returns {company_uri: {names, description, company_type, place}}."""
    all_terms = sorted({t for terms in term_map.values() for t in terms})
    pattern = "|".join(_sparql_regex_escape(t) for t in all_terms)
    query = f"""
    PREFIX schema: <http://schema.org/>
    PREFIX admin: <https://schema.ld.admin.ch/>
    SELECT ?company_uri ?name ?description ?company_type ?municipality WHERE {{
      ?company_uri a admin:ZefixOrganisation ;
           schema:name ?name .
      FILTER regex(str(?name), "{pattern}", "i")
      OPTIONAL {{ ?company_uri schema:description ?description . }}
      OPTIONAL {{ ?company_uri admin:municipality ?muni_id . ?muni_id schema:name ?municipality . }}
      OPTIONAL {{
        ?company_uri schema:additionalType ?type_id .
        ?type_id schema:name ?company_type .
        FILTER(lang(?company_type) = "de" || lang(?company_type) = "fr" || lang(?company_type) = "it")
      }}
    }}
    """
    resp = requests.post(
        ENDPOINT,
        data=query.encode("utf-8"),
        headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    by_company = {}
    for b in data.get("results", {}).get("bindings", []):
        uri = b.get("company_uri", {}).get("value", "")
        name = b.get("name", {}).get("value", "")
        if not uri or not name:
            continue
        entry = by_company.setdefault(uri, {"names": set(), "description": "", "company_type": "", "place": ""})
        entry["names"].add(name)
        if not entry["description"]:
            entry["description"] = b.get("description", {}).get("value", "")
        if not entry["company_type"]:
            entry["company_type"] = b.get("company_type", {}).get("value", "")
        if not entry["place"]:
            entry["place"] = b.get("municipality", {}).get("value", "")
    return by_company


# Extra terms for suppliers whose xlsx spelling is an ASCII transliteration/abbreviation that
# likely differs from the literal Zefix register name (confirmed by a first pass returning no
# hits for the plain cleaned name) -- e.g. "Zuercher" in the source file vs. "Zürcher" in the
# register.
_MANUAL_EXTRA_TERMS = {
    "Zuercher Technik AG": ["Zürcher Technik"],
}


def _match_hits(terms: list, by_company: dict) -> list:
    # word-boundary match in Python (not in the SPARQL regex itself -- SPARQL's XPath-flavor
    # regex has no \b support, and its string-literal escaping treats \b as a backspace
    # escape rather than passing it through) -- this is what rules out "Rexel" substring-
    # matching inside "PARexel", or "hawa" inside "Kahawatu"/"Hathaway"/"HAWAG"/"Khawaja".
    term_patterns = [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in terms]
    hits = []
    for uri, entry in by_company.items():
        if any(any(p.search(n) for p in term_patterns) for n in entry["names"]):
            hits.append((uri, entry))
    return hits


def _print_section(title: str, term_map: dict, by_company: dict, no_match_label: str):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    for supplier_name, terms in term_map.items():
        hits = _match_hits(terms, by_company)
        print(f"\n{supplier_name}")
        print(f"  search terms: {terms}")
        if not hits:
            print(f"  -> {no_match_label}")
            continue
        for uri, entry in hits:
            names = " / ".join(sorted(entry["names"]))
            print(f"  -> {names}")
            print(f"     {uri}")
            if entry["company_type"]:
                print(f"     forma prawna: {entry['company_type']}")
            if entry["place"]:
                print(f"     siedziba: {entry['place']}")
            if entry["description"]:
                desc = entry["description"]
                print(f"     opis: {desc[:200]}{'...' if len(desc) > 200 else ''}")


def main():
    suppliers = load_swiss_suppliers()
    competitors = load_direct_competitors()
    print(f"[search] {len(suppliers)} Swiss-based suppliers, {len(competitors)} Direct Competitor row(s) from the xlsx")

    ch_term_map = {row["Supplier Name"]: _core_terms(row["Supplier Name"]) for _, row in suppliers.iterrows()}
    for name, extra in _MANUAL_EXTRA_TERMS.items():
        if name in ch_term_map:
            ch_term_map[name] = ch_term_map[name] + extra
    competitor_term_map = {row["Supplier Name"]: _core_terms(row["Supplier Name"]) for _, row in competitors.iterrows()}

    for name, terms in {**ch_term_map, **competitor_term_map}.items():
        print(f"  {name!r} -> search terms: {terms}")

    print("[search] querying LINDAS (single combined query)...")
    by_company = search_lindas({**ch_term_map, **competitor_term_map})
    print(f"[search] {len(by_company)} distinct Zefix entities matched at least one term")

    _print_section("CH-BASED SUPPLIERS", ch_term_map, by_company, "NO MATCH in Zefix")
    _print_section(
        "DIRECT COMPETITORS -- checking for a Swiss branch/subsidiary footprint",
        competitor_term_map, by_company, "NO Swiss presence found in Zefix",
    )
    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
