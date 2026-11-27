"""English display layer for the dashboard and email digests (added 2026-11-27).

Internal values stay as they are: activity-category keys in config.py are Polish and are stored in
the DB and matched in filters.py, and ~700 stored `reason` strings were written in Polish. Rather
than migrate the DB, everything is translated here at render time, so old and new rows both
show in English. Tender TITLES are a separate concern: see translate.py (Claude, stored in title_en).
"""
import re

# ISO 3166-1 alpha-2 -> English short name (dropdown + country column).
COUNTRY_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia", "CY": "Cyprus",
    "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia", "FI": "Finland", "FR": "France",
    "DE": "Germany", "GR": "Greece", "HU": "Hungary", "IE": "Ireland", "IT": "Italy",
    "LV": "Latvia", "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia",
    "ES": "Spain", "SE": "Sweden", "NO": "Norway", "IS": "Iceland", "LI": "Liechtenstein",
    "CH": "Switzerland", "GB": "United Kingdom", "UA": "Ukraine", "MD": "Moldova",
    "MK": "North Macedonia", "AL": "Albania", "RS": "Serbia", "ME": "Montenegro",
    "BA": "Bosnia and Herzegovina", "GE": "Georgia", "TR": "Türkiye",
}

# Stored activity-category values (Polish keys from config.py / older source code) -> English.
CATEGORY_EN = {
    "Rozdzielnice / Switchgear": "Switchgear",
    "Transformatory": "Transformers",
    "Wyłączniki / rozłączniki": "Circuit breakers / disconnectors",
    "SN/WN ogólne": "MV/HV general",
    "Obróbka mechaniczna / produkcja precyzyjna": "Machining / precision manufacturing",
    "Odlewy / komponenty": "Castings / components",
    "Wyposażenie morskie / stoczniowe": "Marine / shipbuilding equipment",
    "Maszyny przemysłowe": "Industrial machinery",
    "Elektrotechnika / energetyka ogólna": "Electrical engineering / power (general)",
    "Zakład energetyczny / dostawca energii": "Utility / energy supplier",
    "Dystrybucja komponentów elektrycznych": "Electrical component distribution",
    "Elektronika / automatyka": "Electronics / automation",
    "Hydraulika / pneumatyka": "Hydraulics / pneumatics",
    "Inżynieria / projektowanie": "Engineering / design",
    "Kable / przewody": "Cables / wires",
    "Uszczelnienia": "Seals / gaskets",
    "Łożyska": "Bearings",
    "Starlink / łączność satelitarna": "Starlink / satellite comms",
}

# Fixed phrases inside stored `reason` strings, longest first so compound phrases win.
_REASON_PHRASES = sorted({
    "producent/obróbka mechaniczna": "manufacturer/machining",
    "dystrybucja/handel": "distribution/trade",
    "cel działalności zawiera": "company purpose contains",
    "słowo kluczowe": "keyword",
    "zamawiający": "buyer",
    "w branży": "in sector",
    "(poza tytułem)": "(not in title)",
    "akcesoria": "accessories",
    "relacja handlowa potwierdzona przez użytkownika": "business relationship confirmed by user",
    "client_of": "client of",
}.items(), key=lambda kv: -len(kv[0]))
_REASON_RE = re.compile("|".join(re.escape(k) for k, _ in _REASON_PHRASES))
_REASON_MAP = dict(_REASON_PHRASES)


def country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code, code or "")


def category_en(value: str) -> str:
    return CATEGORY_EN.get(value, value) if value else (value or "")


def reason_en(text: str) -> str:
    return _REASON_RE.sub(lambda m: _REASON_MAP[m.group(0)], text) if text else (text or "")
