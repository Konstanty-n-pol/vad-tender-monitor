"""Normalized record schema shared by all source modules."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Record:
    title: str
    url: str
    source: str          # e.g. "simap", "zefix", "ted"
    country: str          # "DE" | "CH" | "PL"
    category: str          # "tender" | "company" | "news"
    date_found: str        # ISO date, when this pipeline run first saw it
    buyer: Optional[str] = None       # zamawiajacy / procOffice / contracting authority
    deadline: Optional[str] = None     # ISO date, tender submission deadline
    value_estimate: Optional[str] = None
    keywords_matched: list = field(default_factory=list)
    reason: str = ""       # 1-line "why this matched" for the digest
    commodity_tier: str = ""    # "Tier 1" | "Tier 2" | "Tier 1 + Tier 2" | "" — see filters.classify_commodity_tier
    website: Optional[str] = None  # company's own site, if known. Zefix/LINDAS has no such field —
                                     # this is only ever populated by a one-off manual enrichment
                                     # pass, never by the automated weekly fetch. See storage.py.

    def dedup_key(self) -> str:
        return self.url or f"{self.source}:{self.title}"
