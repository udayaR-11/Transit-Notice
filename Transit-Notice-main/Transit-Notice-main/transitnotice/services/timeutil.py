"""Time-zone policy (documented in docs/timezone.md).

* Sources publish local wall-clock times (default Asia/Kolkata).
* We parse them as source-local, convert to UTC, and STORE UTC ISO-8601 strings.
* We DISPLAY in the source time zone so passengers see the agency's local time.
* Date-only start  -> 00:00:00 local.  Date-only end -> 23:59:59 local (inclusive day).
* Every function that depends on "now" accepts it as a parameter so tests are reproducible.
"""
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

UTC = timezone.utc

_FORMATS = [
    ("%d %b %Y %H:%M", False),
    ("%d %B %Y %H:%M", False),
    ("%Y-%m-%d %H:%M", False),
    ("%Y-%m-%dT%H:%M", False),
    ("%d/%m/%Y %H:%M", False),
    ("%d-%m-%Y %H:%M", False),
    ("%d %b %Y", True),
    ("%d %B %Y", True),
    ("%Y-%m-%d", True),
    ("%d/%m/%Y", True),
    ("%d-%m-%Y", True),
]


def utcnow():
    return datetime.now(UTC)


def parse_local(text, tz, *, end_of_day=False):
    """Parse a source-local date/time string -> aware UTC datetime. Returns None if empty/unparseable."""
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    cleaned = re.sub(r"\b(IST|hrs|hours)\b", "", cleaned, flags=re.I).strip()
    if not cleaned or cleaned.lower() in {"-", "n/a", "na", "tbd", "until further notice", "ongoing"}:
        return None
    for fmt, date_only in _FORMATS:
        try:
            naive = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        if date_only and end_of_day:
            naive = naive.replace(hour=23, minute=59, second=59)
        return naive.replace(tzinfo=tz).astimezone(UTC)
    return None


def to_iso(dt):
    return dt.astimezone(UTC).isoformat() if dt else None


def from_iso(text):
    return datetime.fromisoformat(text) if text else None


def fmt_local(iso_text, tz, with_zone=True):
    """Format a stored UTC ISO string in the source time zone for display."""
    if not iso_text:
        return "-"
    dt = from_iso(iso_text).astimezone(tz)
    out = dt.strftime("%d %b %Y, %H:%M")
    return f"{out} {dt.tzname()}" if with_zone else out


def humanize_age(iso_text, now):
    if not iso_text:
        return "never"
    delta = now - from_iso(iso_text)
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"
