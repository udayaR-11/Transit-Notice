"""Mandatory acceptance tests from the brief + robustness tests."""
from datetime import timedelta

from scraper.fetcher import FetchError
from services import queries
from services.ingest import refresh_source
from services.status import compute_status, freshness
from services.timeutil import to_iso
from tests.conftest import NOW, TZ, FakeFetcher, unavailable


def run(conn, adapter, source, now=NOW):
    return refresh_source(conn, adapter, FakeFetcher(source), TZ, now=now)


def states(conn, now=NOW, **kw):
    return {n["notice_id"].split(":")[1]: n["state"]
            for n in queries.search_notices(conn, tz=TZ, now=now, status="all", **kw)}


# ---- mandatory acceptance tests -------------------------------------------------------------
def test_AT1_expired_advisory_is_not_marked_active(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    assert states(conn)["TN-C3"] == "expired"
    active = queries.search_notices(conn, tz=TZ, now=NOW, status="active")
    assert "TN-C3" not in {n["notice_id"].split(":")[1] for n in active}
    # ...and a notice flips to expired purely because time passes (nothing stored to go stale)
    later = NOW + timedelta(days=10)
    assert states(conn, now=later)["TN-A1"] == "expired"


def test_AT2_route_filter_works_with_multiple_affected_routes(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    for route in ("45A", "45B", "45b", " 45 a "):
        found = queries.search_notices(conn, tz=TZ, now=NOW, route=route, status="all")
        assert [n["notice_id"] for n in found] == ["demo:TN-A1"], route
        assert found[0]["routes"] == ["45A", "45B"]
    assert queries.search_notices(conn, tz=TZ, now=NOW, route="999", status="all") == []


def test_AT3_extended_advisory_updates_existing_notice_history(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    later = NOW + timedelta(hours=1)
    s = run(conn, adapter, "sample_v2_extended.html", now=later)
    assert s.revised == 1 and s.new == 0
    row = conn.execute("SELECT * FROM notices WHERE notice_id='demo:TN-B2'").fetchone()
    assert row["revision_id"] == 2
    assert "Extended" in row["change_summary"]
    assert conn.execute("SELECT COUNT(*) c FROM notices WHERE notice_id='demo:TN-B2'").fetchone()["c"] == 1  # same row
    revs = conn.execute("SELECT revision_id, valid_to FROM notice_revisions WHERE notice_id='demo:TN-B2' "
                        "ORDER BY revision_id").fetchall()
    assert [r["revision_id"] for r in revs] == [1, 2]
    assert revs[0]["valid_to"] != revs[1]["valid_to"]           # old end date preserved in history


def test_AT5_stale_notice_shows_latest_known_verification(conn, adapter):
    run(conn, adapter, "sample_v1.html", now=NOW)
    later = NOW + timedelta(hours=3)
    run(conn, adapter, unavailable().source, now=later)          # source down
    notice = next(n for n in queries.search_notices(conn, tz=TZ, now=later, route="45A"))
    assert notice["last_confirmed_at"] == to_iso(NOW)            # still shows the last real verification
    assert notice["source_stale"] is True


def test_AT6_source_error_does_not_turn_old_data_into_live_data(conn, adapter):
    run(conn, adapter, "sample_v1.html", now=NOW)
    before = [tuple(r) for r in conn.execute("SELECT * FROM notices ORDER BY notice_id")]
    later = NOW + timedelta(minutes=20)
    s = run(conn, adapter, unavailable().source, now=later)
    assert s.outcome == "failed"
    after = [tuple(r) for r in conn.execute("SELECT * FROM notices ORDER BY notice_id")]
    assert before == after                                         # nothing touched, nothing withdrawn
    src = conn.execute("SELECT * FROM sources").fetchone()
    assert src["last_success_at"] == to_iso(NOW)                   # success time NOT advanced by the failure
    assert src["consecutive_failures"] == 1 and "refused" in src["last_error"]
    f = freshness(src, later, 15)
    assert f["state"] == "stale" and f["last_error"]
    # recovery clears the failure state
    run(conn, adapter, "sample_v1.html", now=later + timedelta(minutes=15))
    assert freshness(conn.execute("SELECT * FROM sources").fetchone(), later + timedelta(minutes=15), 45)["state"] == "live"


# ---- idempotency / change detection ----------------------------------------------------------
def test_repeat_run_is_idempotent(conn, adapter):
    first = run(conn, adapter, "sample_v1.html")
    second = run(conn, adapter, "sample_v1.html", now=NOW + timedelta(minutes=15))
    assert (first.new, first.revised) == (4, 0)
    assert (second.new, second.revised, second.unchanged, second.withdrawn) == (0, 0, 4, 0)
    assert conn.execute("SELECT COUNT(*) c FROM notices").fetchone()["c"] == 4
    assert conn.execute("SELECT COUNT(*) c FROM notice_revisions").fetchone()["c"] == 4
    assert conn.execute("SELECT last_confirmed_at FROM notices LIMIT 1").fetchone()[0] == to_iso(NOW + timedelta(minutes=15))


def test_notice_removed_before_end_is_withdrawn_but_kept(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    s = run(conn, adapter, "sample_v2_extended.html", now=NOW + timedelta(hours=1))
    assert s.withdrawn == 1                                        # TN-D4 (upcoming) vanished
    assert states(conn)["TN-D4"] == "withdrawn"
    assert conn.execute("SELECT COUNT(*) c FROM notices").fetchone()["c"] == 4   # still archived
    # expired TN-C3 is still listed, A1 unchanged
    assert states(conn)["TN-C3"] == "expired"


def test_reappearing_notice_is_reinstated(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    run(conn, adapter, "sample_v2_extended.html", now=NOW + timedelta(hours=1))
    s = run(conn, adapter, "sample_v1.html", now=NOW + timedelta(hours=2))
    assert states(conn)["TN-D4"] == "upcoming"
    assert s.revised >= 1


def test_no_end_date_is_open_ended_and_active(conn, adapter):
    s = run(conn, adapter, "no_end_date.html")
    assert s.outcome == "success"
    n = next(x for x in queries.search_notices(conn, tz=TZ, now=NOW, route="21"))
    assert n["valid_to"] is None and n["open_ended"] and n["state"] == "active"
    # ten years later it is STILL active (we never invent an end date)
    assert compute_status(n["valid_from"], None, "published", NOW + timedelta(days=3650)) == "active"


def test_end_date_added_later_is_a_revision(conn, adapter, tmp_path):
    run(conn, adapter, "no_end_date.html")
    html = (__import__("pathlib").Path("fixtures/no_end_date.html").read_text())
    html = html.replace('<span class="valid-to"></span>', '<span class="valid-to">27 Oct 2026</span>')
    run(conn, adapter, html, now=NOW + timedelta(hours=1))
    row = conn.execute("SELECT * FROM notices WHERE notice_id='demo:TN-E5'").fetchone()
    assert row["revision_id"] == 2 and "End date set" in row["change_summary"]


# ---- bad input / unavailable source ---------------------------------------------------------
def test_missing_fields_skipped_but_good_records_saved(conn, adapter):
    s = run(conn, adapter, "missing_fields.html")
    assert s.outcome == "partial" and s.skipped == 5 and s.new == 1
    assert conn.execute("SELECT notice_id FROM notices").fetchall()[0][0] == "demo:TN-A1"


def test_duplicate_records_on_page_are_stored_once(conn, adapter):
    s = run(conn, adapter, "duplicates.html")
    assert s.new == 2 and s.skipped == 1
    assert conn.execute("SELECT COUNT(*) c FROM notices").fetchone()["c"] == 2


def test_malformed_html_does_not_crash_and_good_record_survives(conn, adapter):
    s = run(conn, adapter, "malformed.html")
    assert s.outcome in ("success", "partial")
    ids = {r[0] for r in conn.execute("SELECT notice_id FROM notices")}
    assert "demo:TN-A1" in ids


def test_changed_layout_is_a_failure_not_an_empty_board(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    s = run(conn, adapter, "layout_changed.html", now=NOW + timedelta(hours=1))
    assert s.outcome == "failed" and "advisories" in s.error
    assert conn.execute("SELECT COUNT(*) c FROM notices WHERE status='withdrawn'").fetchone()["c"] == 0


def test_error_page_is_a_failure_not_mass_withdrawal(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    s = run(conn, adapter, "error_page.html", now=NOW + timedelta(hours=1))
    assert s.outcome == "failed"
    assert conn.execute("SELECT COUNT(*) c FROM notices WHERE status='withdrawn'").fetchone()["c"] == 0


def test_never_checked_source_is_not_live(conn):
    assert freshness(None, NOW, 45)["state"] == "unknown"


# ---- filters ---------------------------------------------------------------------------------
def test_date_station_area_and_text_filters(conn, adapter):
    run(conn, adapter, "sample_v1.html")
    ids = lambda **kw: {n["notice_id"].split(":")[1] for n in queries.search_notices(conn, tz=TZ, now=NOW, status="all", **kw)}
    assert ids(date="2026-10-27") == {"TN-A1"}                  # outage already ended on the 26th
    assert ids(date="2026-10-12") == {"TN-C3"}
    assert ids(date="2026-10-26") == {"TN-A1", "TN-B2"}
    assert ids(station="silk") == {"TN-A1"}
    assert ids(area="north") == {"TN-D4"}
    assert ids(q="shuttle") == {"TN-B2"}
    assert ids(date="not-a-date") == {"TN-A1", "TN-B2", "TN-C3", "TN-D4"}   # bad input ignored, no crash
