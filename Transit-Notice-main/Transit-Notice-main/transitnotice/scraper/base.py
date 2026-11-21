"""Adapter contract. One adapter per source page/feed; each knows only how to parse that source."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from services.normalize import RawNotice


class StructureError(Exception):
    """Page loaded but no longer looks like the source we expect (layout changed / error page)."""


@dataclass
class ParseResult:
    notices: List[RawNotice] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)   # per-record problems (record skipped)


class SourceAdapter(ABC):
    source_key: str = ""
    agency: str = ""
    page_url: str = ""

    @abstractmethod
    def parse(self, html: str) -> ParseResult:
        """Parse HTML into RawNotice records. Must NOT raise for one bad record - record an issue
        instead. Raise StructureError only when the whole page is not what we expect."""
