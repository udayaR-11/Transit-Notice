"""Turn raw scraped fields into the clean notice schema."""
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from services.timeutil import parse_local, to_iso

TYPE_RULES = [  # first match wins
    ("STOP_CLOSURE", ("stop closed", "stop closure", "stop shifted", "stops closed", "station closed")),
    ("SUSPENSION", ("suspend", "outage", "no service", "cancel", "discontinu", "not operate", "halt")),
    ("DIVERSION", ("divert", "diversion", "re-rout", "reroute", "via ")),
    ("DELAY", ("delay", "late running", "slow", "congestion")),
    ("SCHEDULE_CHANGE", ("schedule", "timing", "frequency", "revised service", "first bus", "last bus")),
]


@dataclass
class RawNotice:
    """What an adapter extracts from a page, before cleaning."""
    ref: Optional[str]
    title: str
    text: str
    routes_raw: str
    area: str = ""
    stations_raw: str = ""
    type_raw: str = ""
    published_raw: str = ""
    valid_from_raw: str = ""
    valid_to_raw: str = ""
    source_url: str = ""


@dataclass
class Notice:
    notice_id: str
    source_key: str
    agency: str
    area: str
    source_url: str
    type: str
    title: str
    summary: str
    published_at: Optional[str]
    valid_from: str
    valid_to: Optional[str]
    routes: list = field(default_factory=list)
    stations: list = field(default_factory=list)
    content_hash: str = ""


class NormalizeError(ValueError):
    """Raised for a record that cannot be used (missing required fields)."""


def normalize_type(type_raw, title="", text=""):
    """The source's own type label wins; title/text keywords are only a fallback."""
    for blob in (f"{type_raw}".lower(), f"{title} {text}".lower()):
        if not blob.strip():
            continue
        for canonical, keywords in TYPE_RULES:
            if any(k in blob for k in keywords):
                return canonical
    return "OTHER"


def split_list(raw):
    items = re.split(r"[,;/\n]+|\band\b|&", raw or "", flags=re.I)
    seen, out = set(), []
    for item in items:
        value = re.sub(r"\s+", " ", item).strip()
        if value and value.upper() not in seen:
            seen.add(value.upper())
            out.append(value)
    return out


def normalize_route(route):
    """'route 45a' -> '45A'."""
    value = re.sub(r"(?i)^routes?\s*", "", route.strip())
    return re.sub(r"\s+", "", value).upper()


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def compute_hash(n):
    """Fingerprint of what matters to a passenger. Any change => new revision."""
    canonical = json.dumps(
        {
            "type": n.type,
            "summary": n.summary,
            "routes": sorted(n.routes),
            "stations": sorted(n.stations),
            "area": n.area,
            "valid_from": n.valid_from,
            "valid_to": n.valid_to,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize(raw, *, source_key, agency, page_url, tz):
    title = clean_text(raw.title)
    summary = clean_text(raw.text) or title
    routes = [normalize_route(r) for r in split_list(raw.routes_raw)]
    routes = [r for r in dict.fromkeys(routes) if r]
    if not title:
        raise NormalizeError("missing title")
    if not routes:
        raise NormalizeError("missing route(s)")

    valid_from = parse_local(raw.valid_from_raw, tz)
    if valid_from is None:
        raise NormalizeError(f"missing/unparseable start date: {raw.valid_from_raw!r}")
    valid_to = parse_local(raw.valid_to_raw, tz, end_of_day=True)  # None => open-ended
    if valid_to is not None and valid_to < valid_from:
        raise NormalizeError("end date is before start date")
    published = parse_local(raw.published_raw, tz)

    area = clean_text(raw.area)
    stations = split_list(raw.stations_raw)
    if raw.ref:
        notice_id = f"{source_key}:{clean_text(raw.ref)}"
    else:  # no stable id on page: derive one that survives extensions (end date NOT included)
        basis = "|".join([agency, ",".join(sorted(routes)), clean_text(raw.type_raw or title).lower(),
                          to_iso(valid_from) or ""])
        notice_id = f"{source_key}:h-{hashlib.sha1(basis.encode()).hexdigest()[:12]}"

    n = Notice(
        notice_id=notice_id, source_key=source_key, agency=agency, area=area,
        source_url=raw.source_url or page_url,
        type=normalize_type(raw.type_raw, title, summary),
        title=title, summary=summary,
        published_at=to_iso(published), valid_from=to_iso(valid_from), valid_to=to_iso(valid_to),
        routes=routes, stations=stations,
    )
    n.content_hash = compute_hash(n)
    return n
