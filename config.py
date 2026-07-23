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
