"""Configuration. All secrets/tunables come from environment variables, never from code."""
import os
from zoneinfo import ZoneInfo


def _load_dotenv(path=".env"):
    """Tiny .env loader so no extra dependency is needed."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


class Config:
    DB_PATH = os.environ.get("TN_DB_PATH", "data/transitnotice.db")
    ADMIN_TOKEN = os.environ.get("TN_ADMIN_TOKEN", "")
    SOURCE_TZ_NAME = os.environ.get("TN_SOURCE_TZ", "Asia/Kolkata")
    REFRESH_MINUTES = int(os.environ.get("TN_REFRESH_MINUTES", "15"))
    STALE_AFTER_MINUTES = int(os.environ.get("TN_STALE_AFTER_MINUTES", "45"))
    USER_AGENT = os.environ.get(
        "TN_USER_AGENT", "TransitNoticeBot/1.0 (student project; contact: not-set)"
    )
    DELIVERY_MODE = os.environ.get("TN_DELIVERY_MODE", "demo")  # demo = log only
    ENABLE_SCHEDULER = os.environ.get("TN_ENABLE_SCHEDULER", "1") == "1"
    SOURCES = [s.strip() for s in os.environ.get("TN_SOURCES", "demo").split(",") if s.strip()]
    DEMO_BASE_URL = os.environ.get("TN_DEMO_BASE_URL", "http://127.0.0.1:5000")

    # HTTP politeness / resilience
    HTTP_TIMEOUT = 10          # seconds
    HTTP_MAX_RETRIES = 3       # retry ceiling
    HTTP_BACKOFF_BASE = 1.5    # seconds, doubled every retry
    MIN_REQUEST_GAP = 2.0      # seconds between requests to the same host

    @property
    def source_tz(self):
        return ZoneInfo(self.SOURCE_TZ_NAME)


config = Config()
