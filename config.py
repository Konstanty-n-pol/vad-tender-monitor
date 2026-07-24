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
COMPANY_MATCH_TERMS = [
    "mittelspannung", "hochspannung", "schaltanlage", "umspannwerk", "trafostation",
    "schaltschrank", "leistungsschalter", "trennschalter", "schaltfeld", "gussteil",
    "sf6", "transformator", "switchgear", "disconnector", "circuit breaker",
    "medium voltage", "high voltage", "substation",
    "elektrotechnik", "energieversorgung", "schaltanlagenbau",
    ("dystrybucj", "energi"), "energetyk", "electrical engineering",
    "power distribution", "switchgear manufactur",
    # French/Italian variants — Zefix purpose text isn't only German, and until now we only
    # matched companies with a German-tagged name (excluding Suisse Romande/Ticino entirely).
    "haute tension", "moyenne tension", "poste électrique", "sous-station",
    "disjoncteur", "sectionneur",
    "alta tensione", "media tensione", "sottostazione", "interruttore",
]

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
