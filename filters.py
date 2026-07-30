"""Shared keyword-matching logic used by every source module.

Matching is substring-based (not whole-word) on purpose: German compounds glue words together
without spaces (Mittelspannungsschaltanlage) and Polish nouns inflect their endings
(rozdzielnica/rozdzielnicy/rozdzielnicami) — both are naturally handled by matching on a stem
substring rather than a whole word. Keywords in config.py are chosen/trimmed as stems for this
reason. Multi-word phrases (e.g. Polish "stacja transformatorowa") are stored as a tuple of
stems that must ALL appear somewhere in the text, since inflection can also change which exact
word form glues to which in a phrase.
"""
from config import (
    ALL_KEYWORDS, BRANCH_HINTS, COMPANY_MATCH_TERMS, DISTRIBUTOR_ROLE_TERMS, INDUSTRIAL_DOMAIN_TERMS,
    COMMODITY_TIER_1_TERMS, COMMODITY_TIER_2_TERMS, ACTIVITY_CATEGORY_MAP, ACTIVITY_CATEGORY_PRIORITY,
    MANUFACTURING_TERMS, LLM_TAG_TO_ACTIVITY_CATEGORY, LLM_TAG_PRIORITY, ENERGY_UTILITY_KEYWORD,
    ENERGY_UTILITY_CATEGORY,
)


def _matches(keyword, haystack: str) -> bool:
    if isinstance(keyword, tuple):
        return all(part in haystack for part in keyword)
    return keyword in haystack


def _label(keyword) -> str:
    return " ".join(keyword) if isinstance(keyword, tuple) else keyword


def match_keywords(*texts: str) -> list:
    """Return the configured keywords/phrases found (case-insensitive stem match) in the given text(s)."""
    haystack = " ".join(t for t in texts if t).lower()
    return [_label(kw) for kw in ALL_KEYWORDS if _matches(kw, haystack)]


def match_branch(*texts: str) -> list:
    haystack = " ".join(t for t in texts if t).lower()
    return [_label(hint) for hint in BRANCH_HINTS if _matches(hint, haystack)]


def match_company_purpose(*texts: str) -> list:
    """Stricter match for free-text company purpose statements — see COMPANY_MATCH_TERMS docstring
    in config.py for why this is a separate, narrower list from match_keywords/match_branch."""
    haystack = " ".join(t for t in texts if t).lower()
    return [_label(kw) for kw in COMPANY_MATCH_TERMS if _matches(kw, haystack)]


def match_distributor_role(*texts: str) -> list:
    """Distribution/broker/reseller business-model terms — see DISTRIBUTOR_ROLE_TERMS docstring
    in config.py. Meant to be used together with match_company_purpose(), never on its own:
    these terms are too generic (common Swiss trading-company boilerplate) to filter on alone."""
    haystack = " ".join(t for t in texts if t).lower()
    return [_label(kw) for kw in DISTRIBUTOR_ROLE_TERMS if _matches(kw, haystack)]


def match_manufacturing(*texts: str) -> list:
    """Mechanical machining / precision manufacturing terms — see MANUFACTURING_TERMS docstring
    in config.py. Takes priority over match_distributor_role() when building a digest reason:
    generic 'Handel'/'Import' boilerplate shouldn't outrank a specific, concrete signal like
    'Décolletage' or 'Feinmechanik' that the company is really a machining shop, not a trader."""
    haystack = " ".join(t for t in texts if t).lower()
    return [_label(kw) for kw in MANUFACTURING_TERMS if _matches(kw, haystack)]


def match_industrial_domain(*texts: str) -> list:
    """Industrial machinery / marine equipment terms — see INDUSTRIAL_DOMAIN_TERMS docstring in
    config.py. Used only by the separate distributor/broker/reseller report, always combined
    (AND) with match_distributor_role()."""
    haystack = " ".join(t for t in texts if t).lower()
    return [_label(kw) for kw in INDUSTRIAL_DOMAIN_TERMS if _matches(kw, haystack)]


def classify_commodity_tier(matched_keywords: list) -> str:
    """Label already-matched keywords as Tier 1 (core switchgear commodities), Tier 2 (adjacent
    industrial/marine equipment or broad branch language), both, or "" — purely informational,
    never gates inclusion. See COMMODITY_TIER_1_TERMS/_2_TERMS in config.py."""
    has_tier1 = any(kw in COMMODITY_TIER_1_TERMS for kw in matched_keywords)
    has_tier2 = any(kw in COMMODITY_TIER_2_TERMS for kw in matched_keywords)
    if has_tier1 and has_tier2:
        return "Tier 1 + Tier 2"
    if has_tier1:
        return "Tier 1"
    if has_tier2:
        return "Tier 2"
    return ""


def classify_activity_category(matched_keywords: list) -> str:
    """Human-readable activity grouping derived from which keyword(s) matched — see
    ACTIVITY_CATEGORY_MAP/_PRIORITY in config.py. Purely a display grouping (same caveat as
    classify_commodity_tier: reflects matched text, not necessarily the company's true
    specialty). Picks the single most specific category present, per ACTIVITY_CATEGORY_PRIORITY."""
    present = {ACTIVITY_CATEGORY_MAP[kw] for kw in matched_keywords if kw in ACTIVITY_CATEGORY_MAP}
    for category in ACTIVITY_CATEGORY_PRIORITY:
        if category in present:
            return category
    return ""


def classify_activity_category_display(keywords_matched: str, llm_product_tags, stored_category: str) -> str:
    """Render-time override of the stored (keyword-derived) activity_category, called from
    generate.py — never written back to storage, so it automatically improves as more companies
    get an LLM classification without needing a backfill migration each time.

    Prefers llm_classify.py's product_tags (semantically grounded, reads the actual purpose
    text) over the keyword-derived category, since the latter collapses most companies into one
    or two generic buckets (see LLM_TAG_TO_ACTIVITY_CATEGORY docstring in config.py for the
    confirmed before/after counts). Falls back to the keyword category for companies not yet
    LLM-classified, with one extra split (energy utilities) that a bare keyword match can
    already do accurately without needing the LLM at all.
    """
    if llm_product_tags:
        tags = {t.strip() for t in llm_product_tags.split(",") if t.strip()}
        for tag in LLM_TAG_PRIORITY:
            if tag in tags:
                return LLM_TAG_TO_ACTIVITY_CATEGORY[tag]
    kws = {k.strip() for k in (keywords_matched or "").split(",")}
    if ENERGY_UTILITY_KEYWORD in kws and stored_category in ("Elektrotechnika / energetyka ogólna", ""):
        return ENERGY_UTILITY_CATEGORY
    return stored_category


def is_relevant_tender(*texts: str) -> tuple:
    """High threshold for 🔴 tenders: require at least one keyword match."""
    matched = match_keywords(*texts)
    return (len(matched) > 0, matched)


def is_relevant_company(*texts: str) -> tuple:
    """Medium threshold for 🟡 companies/investments: branch hint match."""
    matched = match_branch(*texts)
    return (len(matched) > 0, matched)
