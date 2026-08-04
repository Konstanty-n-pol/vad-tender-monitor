"""Central config: keywords, CPV codes, source toggles. Edit this file to tune what counts as relevant."""

# CPV codes relevant to MV/HV switchgear, spare parts, GIS components.
# 31000000 = electrical machinery/apparatus (root); narrower codes below are more precise.
CPV_CODES = [
    "31000000",  # Electrical machinery, apparatus, equipment (root)
    "31200000",  # Electricity distribution and control apparatus
    "31213000",  # Distribution transformers... substations
    "31214000",  # Switches
    "31216000",  # High-voltage equipment
    "31625000",  # Alarm/switchgear related
    "31681000",  # Electrical accessories
    "45232210",  # Construction works for substations (Bauleistungen Umspannwerk)
]

# Keyword sets per language. Entries are stems, matched as substrings (see filters.py docstring
# for why: German compounds and Polish inflection both attach to a stable stem). A tuple means
# "all these stems must appear somewhere in the text" (for multi-word phrases where inflection
# would break a single fixed phrase match).
# NOTE: "GIS" (Gas-Insulated Switchgear) is deliberately excluded — it's indistinguishable from
# the far more common "Geographic Information System" acronym and produced false positives in
# testing (e.g. Hungarian GIS/mapping tenders). The other terms below already cover this domain
# unambiguously (Schaltanlage, SF6, switchgear, Mittelspannung, ...).
KEYWORDS_DE = [
    "mittelspannung", "hochspannung", "schaltanlage", "ersatzteil",
    "gussteil", "umspannwerk", "sf6", "trafostation", "schaltschrank",
    "leistungsschalter", "trennschalter", "schaltfeld",
]

KEYWORDS_PL = [
    "rozdzielnic",  # rozdzielnica/-y/-ę/-ą/-ami
    ("częś", "zamien"),  # część/części zamienna/zamiennych
    ("stacj", "elektroenergetyczn"),
    ("stacj", "transformatorow"),
    "wyłącznik", "rozłącznik", "sf6",
    "transformator", "rozdzielni",  # rozdzielnia/-i/-ę/-ą
]

KEYWORDS_EN = [
    "switchgear", "spare part", "substation", "sf6", "circuit breaker",
    "disconnector", "medium voltage", "high voltage", "cast part", "casting",
]

ALL_KEYWORDS = KEYWORDS_DE + KEYWORDS_PL + KEYWORDS_EN

# PKD/NOGA/branch codes signalling relevant new companies (electrotechnical / energy distribution)
# Used loosely as substring match against a company's purpose/branch text where available.
BRANCH_HINTS = [
    "elektrotechnik", "energieversorgung", "schaltanlagenbau",
    "elektrotechnik",  # covers PL "elektrotechnika" too (substring)
    ("dystrybucj", "energi"), "energetyk",
    "electrical engineering", "power distribution", "switchgear manufactur",
]

# Stricter term set for matching free-text *company purpose* descriptions (used by sources/zefix.py).
# Swiss commercial-register purpose statements routinely include generic boilerplate like "Handel
# mit Waren und Ersatzteilen aller Art" (trade in goods and spare parts of all kinds) or reference
# "Casting" (film/talent casting agencies) — so the generic KEYWORDS_*/BRANCH_HINTS above are too
# noisy for this specific use case (confirmed by testing: "ersatzteil" and "casting" pulled in
# travel agencies, film production companies, generic trading firms). This list sticks to terms
# specific enough to the GIS/MV-HV switchgear domain that they're unlikely to be generic boilerplate.
# Split into groups on 2026-08-02 so sources/zefix.py can query each group as its own smaller
# SPARQL request instead of one combined ~500-char/35-term regex — see that module's docstring
# for why: the LINDAS/Virtuoso endpoint gives non-deterministic, incomplete results once a
# regex-scan query gets expensive enough (confirmed live: identical query, two runs, 248 vs.
# 1371 companies, a known-good match missing from both). Groups mirror ACTIVITY_CATEGORY_MAP's
# categories so no new taxonomy was invented. "gussteil" (Odlewy/komponenty) dropped entirely
# per user decision 2026-08-02 — doesn't fit the current mission-critical-components product
# categories (see memory: user-role-vad-business).
COMPANY_MATCH_TERM_GROUPS = {
    "Rozdzielnice / Switchgear": [
        "schaltanlage", "switchgear", "switchgear manufactur", "schaltschrank", "schaltfeld",
        "schaltanlagenbau", "poste électrique", "sous-station", "sottostazione", "substation",
        "umspannwerk", "trafostation", "sf6",
    ],
    "SN/WN ogólne": [
        "mittelspannung", "hochspannung", "moyenne tension", "haute tension", "alta tensione",
        "media tensione", "medium voltage", "high voltage",
    ],
    "Wyłączniki / rozłączniki": [
        "leistungsschalter", "circuit breaker", "trennschalter", "disconnector", "disjoncteur",
        "sectionneur", "interruttore",
    ],
    "Elektrotechnika / energetyka ogólna": [
        "elektrotechnik", "energieversorgung", "energetyk", "electrical engineering",
        "power distribution", ("dystrybucj", "energi"),
    ],
    "Transformatory": ["transformator"],
}

# Flat union of the groups above, kept for Python-side re-confirmation (filters.py's
# match_company_purpose) — same term set as before the SPARQL side was split into per-group
# queries, just restructured.
COMPANY_MATCH_TERMS = [t for terms in COMPANY_MATCH_TERM_GROUPS.values() for t in terms]

# Terms indicating a distribution / brokerage / reselling business model rather than
# manufacturing. On their own these are far too generic to filter on (a large share of all
# Swiss trading companies mention "Handel"/"distribution" in their purpose) — only meaningful
# combined with a COMPANY_MATCH_TERMS hit in the same text. Used to *classify* company matches
# (distributor/broker/reseller vs. manufacturer/operator) for the digest, not to decide inclusion.
DISTRIBUTOR_ROLE_TERMS = [
    "handel", "vertrieb", "grosshandel", "vermittlung", "handelsvertretung",
    "wiederverkauf", "distribution", "import", "export",
    "négoce", "commerce de gros", "courtage", "représentation", "revente",
    "distribuzione", "commercio all'ingrosso", "intermediazione", "rappresentanza",
    "wholesale", "brokerage", "broker", "reseller", "reselling", "trading", "agency",
    "dystrybucj", "pośrednictw", "hurt", "odsprzedaż",
]

# Separate, standalone report (see sources/zefix_distributors.py): distribution/broker/reseller
# companies (DISTRIBUTOR_ROLE_TERMS above) whose purpose ALSO mentions general industrial
# machinery/equipment or marine/ship equipment — broader than the GIS/MV-HV-specific
# COMPANY_MATCH_TERMS, but still bounded to technical/industrial branches, not "any industry".
# Confirmed live: role-terms alone match ~29,900 CH companies (unusable); role+this list
# narrows it to ~156 (2026-07-25) — a reviewable weekly size. Kept as its own list/report rather
# than folded into COMPANY_MATCH_TERMS so the original curated GIS/MV-HV digest stays untouched.
#
# TRIED AND REVERTED 2026-07-30: to catch Omni Ray SA ("Handel mit Bedarfsartikeln der Elektro-,
# Elektronik- und Computerindustrie ... sowie Übernahme von Vertretungen"), tried adding
# "vertretung" to DISTRIBUTOR_ROLE_TERMS and an "elektroindustrie"/"elektronikindustrie"/
# "computerindustrie"/etc. section here. Confirmed live that EITHER change alone (let alone both
# together) blows the report up from ~227 to ~1300 companies — "electrical/electronics/computer
# industry" and "Vertretung" both turn out to be extremely common phrasing in ordinary Swiss
# company purposes generally, unlike the machinery/marine wording below. Reverted rather than
# shipped unreviewed; catching Omni-Ray-like companies needs either a much more specific phrase
# (e.g. matching Omni Ray's actual multi-clause wording, not the bare sector name) or a manual
# add, not a broadened term list. See conversation 2026-07-30 for the full before/after counts.
INDUSTRIAL_DOMAIN_TERMS = [
    # Industrial machinery / equipment
    "maschinenbau", "industriemaschinen", "industrieanlagen", "anlagenbau", "industrieausrüstung",
    "machines industrielles", "équipement industriel", "construction de machines", "ingénierie industrielle",
    "macchine industriali", "attrezzature industriali", "impianti industriali",
    "industrial machinery", "industrial equipment", "machine building", "plant engineering",
    # Ship / marine equipment
    "schiffsausrüstung", "schiffbau", "schiffstechnik", "maritime ausrüstung",
    "équipement naval", "construction navale", "équipement de navires",
    "attrezzature navali", "cantieristica navale",
    "marine equipment", "shipbuilding", "naval equipment", "vessel equipment", "maritime equipment",
]

# Toggle for the separate distributor/broker/reseller report (main.py runs it independently
# of SOURCES_ENABLED above).
DISTRIBUTOR_REPORT_ENABLED = True

# Commodity tier classification, applied on top of already-matched keywords purely for display —
# see filters.classify_commodity_tier(). Never gates inclusion; a record is already relevant by
# the time this runs. Tier 1 = the core GIS/MV-HV switchgear commodities this business deals in
# directly (the actual products). Tier 2 = supporting/adjacent commodities and broader branch
# descriptors (general industrial machinery, marine equipment, generic "electrical engineering"
# sector language) — still relevant, but one step removed from the core product.
# NOTE: entries here must match the *label* form produced by filters._label() — tuples like
# ("dystrybucj", "energi") become the space-joined string "dystrybucj energi" once matched.
COMMODITY_TIER_1_TERMS = {
    "mittelspannung", "hochspannung", "moyenne tension", "haute tension",
    "alta tensione", "media tensione",
    "schaltanlage", "switchgear", "poste électrique", "sous-station", "sottostazione",
    "substation", "umspannwerk", "trafostation",
    "leistungsschalter", "circuit breaker",
    "trennschalter", "disconnector", "disjoncteur", "sectionneur", "interruttore",
    "transformator", "sf6", "schaltschrank", "schaltfeld",
}

COMMODITY_TIER_2_TERMS = {
    "gussteil",
    "elektrotechnik", "energieversorgung", "schaltanlagenbau",
    "electrical engineering", "power distribution", "switchgear manufactur",
    "energetyk", "dystrybucj energi",
    "maschinenbau", "industriemaschinen", "industrieanlagen", "anlagenbau", "industrieausrüstung",
    "machines industrielles", "équipement industriel", "construction de machines", "ingénierie industrielle",
    "macchine industriali", "attrezzature industriali", "impianti industriali",
    "industrial machinery", "industrial equipment", "machine building", "plant engineering",
    "schiffsausrüstung", "schiffbau", "schiffstechnik", "maritime ausrüstung",
    "équipement naval", "construction navale", "équipement de navires",
    "attrezzature navali", "cantieristica navale",
    "marine equipment", "shipbuilding", "naval equipment", "vessel equipment", "maritime equipment",
}

# Human-readable activity-category grouping, derived purely from which keyword actually matched
# (see filters.classify_activity_category()) — a finer-grained sibling to the Tier 1/Tier 2 split
# above, for grouping companies on the dashboard by what they concretely deal in. Same caveat as
# commodity tier: this reflects the matched text, not the company's true specialty (a company
# could easily do more than what its one matched keyword suggests).
ACTIVITY_CATEGORY_MAP = {
    # Rozdzielnice / Switchgear (incl. SF6 gas-insulated switchgear)
    "schaltanlage": "Rozdzielnice / Switchgear", "switchgear": "Rozdzielnice / Switchgear",
    "switchgear manufactur": "Rozdzielnice / Switchgear",
    "schaltschrank": "Rozdzielnice / Switchgear", "schaltfeld": "Rozdzielnice / Switchgear",
    "schaltanlagenbau": "Rozdzielnice / Switchgear", "poste électrique": "Rozdzielnice / Switchgear",
    "sous-station": "Rozdzielnice / Switchgear", "sottostazione": "Rozdzielnice / Switchgear",
    "substation": "Rozdzielnice / Switchgear", "umspannwerk": "Rozdzielnice / Switchgear",
    "trafostation": "Rozdzielnice / Switchgear", "sf6": "Rozdzielnice / Switchgear",
    # Transformatory
    "transformator": "Transformatory",
    # Wyłączniki / rozłączniki
    "leistungsschalter": "Wyłączniki / rozłączniki", "circuit breaker": "Wyłączniki / rozłączniki",
    "trennschalter": "Wyłączniki / rozłączniki", "disconnector": "Wyłączniki / rozłączniki",
    "disjoncteur": "Wyłączniki / rozłączniki", "sectionneur": "Wyłączniki / rozłączniki",
    "interruttore": "Wyłączniki / rozłączniki",
    # SN/WN ogólne
    "mittelspannung": "SN/WN ogólne", "hochspannung": "SN/WN ogólne",
    "moyenne tension": "SN/WN ogólne", "haute tension": "SN/WN ogólne",
    "alta tensione": "SN/WN ogólne", "media tensione": "SN/WN ogólne",
    "medium voltage": "SN/WN ogólne", "high voltage": "SN/WN ogólne",
    # Odlewy / komponenty
    "gussteil": "Odlewy / komponenty",
    # Wyposażenie morskie / stoczniowe
    "schiffsausrüstung": "Wyposażenie morskie / stoczniowe", "schiffbau": "Wyposażenie morskie / stoczniowe",
    "schiffstechnik": "Wyposażenie morskie / stoczniowe", "maritime ausrüstung": "Wyposażenie morskie / stoczniowe",
    "équipement naval": "Wyposażenie morskie / stoczniowe", "construction navale": "Wyposażenie morskie / stoczniowe",
    "équipement de navires": "Wyposażenie morskie / stoczniowe", "attrezzature navali": "Wyposażenie morskie / stoczniowe",
    "cantieristica navale": "Wyposażenie morskie / stoczniowe", "marine equipment": "Wyposażenie morskie / stoczniowe",
    "shipbuilding": "Wyposażenie morskie / stoczniowe", "naval equipment": "Wyposażenie morskie / stoczniowe",
    "vessel equipment": "Wyposażenie morskie / stoczniowe", "maritime equipment": "Wyposażenie morskie / stoczniowe",
    # Maszyny przemysłowe
    "maschinenbau": "Maszyny przemysłowe", "industriemaschinen": "Maszyny przemysłowe",
    "industrieanlagen": "Maszyny przemysłowe", "anlagenbau": "Maszyny przemysłowe",
    "industrieausrüstung": "Maszyny przemysłowe", "machines industrielles": "Maszyny przemysłowe",
    "équipement industriel": "Maszyny przemysłowe", "construction de machines": "Maszyny przemysłowe",
    "ingénierie industrielle": "Maszyny przemysłowe", "macchine industriali": "Maszyny przemysłowe",
    "attrezzature industriali": "Maszyny przemysłowe", "impianti industriali": "Maszyny przemysłowe",
    "industrial machinery": "Maszyny przemysłowe", "industrial equipment": "Maszyny przemysłowe",
    "machine building": "Maszyny przemysłowe", "plant engineering": "Maszyny przemysłowe",
    # Elektrotechnika / energetyka ogólna — najbardziej ogólna, traktowana jako fallback
    "elektrotechnik": "Elektrotechnika / energetyka ogólna",
    "energieversorgung": "Elektrotechnika / energetyka ogólna",
    "energetyk": "Elektrotechnika / energetyka ogólna",
    "electrical engineering": "Elektrotechnika / energetyka ogólna",
    "power distribution": "Elektrotechnika / energetyka ogólna",
    "dystrybucj energi": "Elektrotechnika / energetyka ogólna",
    # Obróbka mechaniczna / produkcja precyzyjna
    "feinmechanik": "Obróbka mechaniczna / produkcja precyzyjna",
    "präzisionsmechanik": "Obróbka mechaniczna / produkcja precyzyjna",
    "décolletage": "Obróbka mechaniczna / produkcja precyzyjna",
    "mechanische bearbeitung": "Obróbka mechaniczna / produkcja precyzyjna",
    "zerspanung": "Obróbka mechaniczna / produkcja precyzyjna",
    "metallbearbeitung": "Obróbka mechaniczna / produkcja precyzyjna",
    "cnc-bearbeitung": "Obróbka mechaniczna / produkcja precyzyjna",
    "cnc bearbeitung": "Obróbka mechaniczna / produkcja precyzyjna",
    "fräsen": "Obróbka mechaniczna / produkcja precyzyjna",
    "drehen": "Obróbka mechaniczna / produkcja precyzyjna",
    "schweisserei": "Obróbka mechaniczna / produkcja precyzyjna",
    "usinage": "Obróbka mechaniczna / produkcja precyzyjna",
    "mécanique de précision": "Obróbka mechaniczna / produkcja precyzyjna",
    "lavorazione meccanica": "Obróbka mechaniczna / produkcja precyzyjna",
    "meccanica di precisione": "Obróbka mechaniczna / produkcja precyzyjna",
    "cnc machining": "Obróbka mechaniczna / produkcja precyzyjna",
    "precision machining": "Obróbka mechaniczna / produkcja precyzyjna",
    "metalworking": "Obróbka mechaniczna / produkcja precyzyjna",
}

# Terms indicating real mechanical machining / precision manufacturing capability (as opposed
# to distribution/trading). Found via a data spot-check (2026-07-27): companies like
# "hr-Feinmechanik SA" (Feinmechanik = precision mechanics, literally in the name) and
# "Precisteel Sàrl" (purpose text: "Décolletage, Metall im Allgemeinen, Schweisserei" — precision
# turning, metalwork, welding) were labelled "dystrybucja/handel" in the digest because their
# purpose text also contains generic "Handel"/"Import/Export" boilerplate (extremely common
# Swiss legal-purpose language covering the sale of one's own manufactured goods) — the reason
# text picked the generic distributor-role label over their actual, more specific trade. These
# terms take priority over DISTRIBUTOR_ROLE_TERMS when building the digest reason/activity
# category (see sources/zefix.py, sources/zefix_distributors.py) so a real machining shop reads
# as "producent/obróbka mechaniczna", not "dystrybucja/handel".
MANUFACTURING_TERMS = [
    "feinmechanik", "präzisionsmechanik", "décolletage", "mechanische bearbeitung", "zerspanung",
    "metallbearbeitung", "cnc-bearbeitung", "cnc bearbeitung", "fräsen", "drehen", "schweisserei",
    "usinage", "mécanique de précision", "lavorazione meccanica", "meccanica di precisione",
    "cnc machining", "precision machining", "metalworking",
]

# Priority order when a record matched keywords from more than one category — most specific
# first, most generic last, so e.g. a record matching both "schaltanlage" and "elektrotechnik"
# is grouped under "Rozdzielnice / Switchgear", not the generic fallback. Manufacturing/machining
# ranks above the generic industrial-machinery/electrotechnical buckets since it's a much more
# specific, concrete signal of what the company actually does.
ACTIVITY_CATEGORY_PRIORITY = [
    "Rozdzielnice / Switchgear", "Transformatory", "Wyłączniki / rozłączniki", "SN/WN ogólne",
    "Obróbka mechaniczna / produkcja precyzyjna",
    "Odlewy / komponenty", "Wyposażenie morskie / stoczniowe", "Maszyny przemysłowe",
    "Elektrotechnika / energetyka ogólna",
]

# Display-time category override (see filters.classify_activity_category_display, used by
# generate.py): once a company has an LLM classification (llm_classify.py product_tags), that's
# a far richer/more accurate signal than the keyword-derived ACTIVITY_CATEGORY_MAP above — e.g.
# it split what used to be one "Elektrotechnika / energetyka ogólna" bucket covering 57% of the
# main digest into real categories (confirmed live 2026-07-30: 38/67 -> 12/67 in that fallback
# bucket, 343/363 -> 125/363 for the distributor report). Maps llm_classify.PRODUCT_TAGS values
# to the SAME category label already used above where the concept is identical (e.g. "rozdzielnice
# SN/WN" -> "Rozdzielnice / Switchgear"), so the two systems don't produce parallel/duplicate
# category names on the dashboard. Order is priority (most specific first), same spirit as
# ACTIVITY_CATEGORY_PRIORITY -- picks the first matching tag if a company has several.
LLM_TAG_TO_ACTIVITY_CATEGORY = {
    "rozdzielnice SN/WN": "Rozdzielnice / Switchgear",
    "transformatory": "Transformatory",
    "wyłączniki/rozłączniki": "Wyłączniki / rozłączniki",
    "obróbka mechaniczna/CNC": "Obróbka mechaniczna / produkcja precyzyjna",
    "odlewy/odlewnictwo": "Odlewy / komponenty",
    "łożyska": "Łożyska",
    "hydraulika/pneumatyka": "Hydraulika / pneumatyka",
    "uszczelnienia": "Uszczelnienia",
    "kable/przewody": "Kable / przewody",
    "elektronika/automatyka": "Elektronika / automatyka",
    "dystrybucja komponentów elektrycznych": "Dystrybucja komponentów elektrycznych",
    "wyposażenie morskie": "Wyposażenie morskie / stoczniowe",
    "inżynieria/projektowanie": "Inżynieria / projektowanie",
    "maszyny przemysłowe (ogólne)": "Maszyny przemysłowe",
    # "inne" deliberately unmapped -- falls through to the keyword-derived category below
}
LLM_TAG_PRIORITY = list(LLM_TAG_TO_ACTIVITY_CATEGORY.keys())

# One keyword-only split kept as a fallback for companies without an LLM classification yet
# (e.g. brand new finds from this week's fetch, before the next classification batch runs):
# "energieversorgung"-matched companies are literally power utilities/cooperatives, not
# switchgear-parts companies, and were previously lumped into the generic fallback category.
ENERGY_UTILITY_KEYWORD = "energieversorgung"
ENERGY_UTILITY_CATEGORY = "Zakład energetyczny / dostawca energii"

# Countries in scope
COUNTRIES = ["DE", "CH", "PL"]

# Relevance thresholds per category (see sources/*.py for how these are applied)
CATEGORY_THRESHOLDS = {
    "tender": "high",       # 🔴 hard keyword + branch match required
    "company": "medium",    # 🟡 new/changed company in relevant branch
    "news": "low",          # ⚪ headline + link only, no full analysis
}

# Which source modules are enabled. Toggle here as credentials/access become available.
SOURCES_ENABLED = {
    "zefix": True,
    "simap": True,
    "ted": True,
    "ezamowienia": False,  # enable once NoticeType enum values are confirmed from integration docs
}
