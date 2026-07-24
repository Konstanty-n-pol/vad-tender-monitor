"""Shared keyword-matching logic used by every source module.

Matching is substring-based (not whole-word) on purpose: German compounds glue words together
without spaces (Mittelspannungsschaltanlage) and Polish nouns inflect their endings
(rozdzielnica/rozdzielnicy/rozdzielnicami) — both are naturally handled by matching on a stem
substring rather than a whole word. Keywords in config.py are chosen/trimmed as stems for this
reason. Multi-word phrases (e.g. Polish "stacja transformatorowa") are stored as a tuple of
stems that must ALL appear somewhere in the text, since inflection can also change which exact
word form glues to which in a phrase.
"""
from config import ALL_KEYWORDS, BRANCH_HINTS, COMPANY_MATCH_TERMS


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


def is_relevant_tender(*texts: str) -> tuple:
    """High threshold for 🔴 tenders: require at least one keyword match."""
    matched = match_keywords(*texts)
    return (len(matched) > 0, matched)


def is_relevant_company(*texts: str) -> tuple:
    """Medium threshold for 🟡 companies/investments: branch hint match."""
    matched = match_branch(*texts)
    return (len(matched) > 0, matched)
