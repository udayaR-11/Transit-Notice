from datetime import timedelta

import pytest

from tests.conftest import TZ
from services.normalize import NormalizeError, RawNotice, normalize, normalize_type, normalize_route, split_list
from services.timeutil import parse_local, to_iso, fmt_local


def raw(**kw):
    base = dict(ref="R1", title="Route 1 diverted", text="Diverted via X", routes_raw="1",
                valid_from_raw="24 Oct 2026 06:00", valid_to_raw="28 Oct 2026 22:00", type_raw="Diversion")
    base.update(kw)
    return RawNotice(**base)


def n(**kw):
    return normalize(raw(**kw), source_key="demo", agency="A", page_url="http://x/p", tz=TZ)


def test_timezone_is_documented_and_reproducible():
    # 06:00 IST == 00:30 UTC (IST is UTC+05:30, no DST). Stored UTC, displayed back in source tz.
    dt = parse_local("28 Oct 2026 06:00", TZ)
    assert to_iso(dt) == "2026-10-28T00:30:00+00:00"
    assert fmt_local(to_iso(dt), TZ) == "28 Oct 2026, 06:00 IST"


def test_date_only_end_is_inclusive_end_of_day():
    assert to_iso(parse_local("28 Oct 2026", TZ, end_of_day=True)) == "2026-10-28T18:29:59+00:00"
    assert to_iso(parse_local("28 Oct 2026", TZ)) == "2026-10-27T18:30:00+00:00"


@pytest.mark.parametrize("text", ["", "   ", "TBD", "until further notice", "n/a", "garbage", None])
def test_unparseable_or_empty_dates_return_none(text):
    assert parse_local(text, TZ) is None


def test_multiple_routes_split_and_normalised():
    assert n(routes_raw="45a, Route 45B and 45A").routes == ["45A", "45B"]
    assert normalize_route(" route 21 k ") == "21K"
    assert split_list("A; B / C & D") == ["A", "B", "C", "D"]


def test_missing_end_date_is_open_ended_not_error():
    assert n(valid_to_raw="").valid_to is None


@pytest.mark.parametrize("kw,msg", [
    (dict(routes_raw=""), "route"), (dict(valid_from_raw=""), "start"), (dict(title=""), "title"),
    (dict(valid_from_raw="soon"), "start"), (dict(valid_from_raw="28 Oct 2026", valid_to_raw="24 Oct 2026"), "before"),
])
def test_invalid_records_rejected(kw, msg):
    with pytest.raises(NormalizeError, match=msg):
        n(**kw)


def test_type_label_wins_over_text_keywords():
    assert normalize_type("Delay", "Route 3 diverted", "via the bypass") == "DELAY"
    assert normalize_type("", "Metro outage tonight", "") == "SUSPENSION"
    assert normalize_type("", "Hello", "world") == "OTHER"


def test_content_hash_changes_when_end_date_changes_but_id_stays():
    a, b = n(ref=None, valid_to_raw="28 Oct 2026"), n(ref=None, valid_to_raw="30 Oct 2026")
    assert a.notice_id == b.notice_id          # extension keeps identity
    assert a.content_hash != b.content_hash    # ...but is detected as a change
