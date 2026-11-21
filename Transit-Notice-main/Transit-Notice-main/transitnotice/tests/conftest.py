import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TN_ENABLE_SCHEDULER", "0")
os.environ.setdefault("TN_ADMIN_TOKEN", "test-token")

from config import config  # noqa: E402
from db import open_db  # noqa: E402
from scraper.adapters.demo import DemoAdapter  # noqa: E402
from scraper.fetcher import FetchError  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
NOW = datetime(2026, 10, 25, 6, 30, tzinfo=timezone.utc)      # = 12:00 IST on 25 Oct 2026
TZ = config.source_tz


class FakeFetcher:
    """Returns fixture HTML (or raises) instead of touching the network."""

    def __init__(self, source):
        self.source = source

    def get(self, url):
        if isinstance(self.source, Exception):
            raise self.source
        if isinstance(self.source, str) and self.source.endswith(".html"):
            return (FIXTURES / self.source).read_text(encoding="utf-8")
        return self.source


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


@pytest.fixture
def adapter():
    return DemoAdapter(base_url="http://demo.example")


@pytest.fixture
def now():
    return NOW


def unavailable():
    return FakeFetcher(FetchError("giving up: connection refused"))
