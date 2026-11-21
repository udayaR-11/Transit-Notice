from datetime import timedelta

from services import alerts
from services.ingest import refresh_source
from services.timeutil import to_iso
from tests.conftest import NOW, TZ, FakeFetcher


def refresh(conn, adapter, source, now=NOW):
    s = refresh_source(conn, adapter, FakeFetcher(source), TZ, now=now)
    sent = []
    created, delivered = alerts.process_events(conn, s.events, TZ, now=now, sender=lambda sub, msg: sent.append((sub["label"], msg)))
    return s, sent


def add_sub(conn, label, route=None, area=None):
    conn.execute("INSERT INTO subscribers(label, filter_route, filter_area, created_at) VALUES (?,?,?,?)",
                 (label, route, area, to_iso(NOW)))
    conn.commit()


def test_single_alert_per_new_notice_and_no_repeat_on_rerun(conn, adapter):
    add_sub(conn, "commuter", route="45B")
    _, sent1 = refresh(conn, adapter, "sample_v1.html")
    assert len(sent1) == 1 and "45A, 45B" in sent1[0][1]
    _, sent2 = refresh(conn, adapter, "sample_v1.html", now=NOW + timedelta(minutes=15))
    assert sent2 == []                                              # nothing changed -> nothing sent


def test_extension_triggers_exactly_one_revised_alert(conn, adapter):
    add_sub(conn, "metro rider", route="GL")
    refresh(conn, adapter, "sample_v1.html")
    _, sent = refresh(conn, adapter, "sample_v2_extended.html", now=NOW + timedelta(hours=1))
    assert len(sent) == 1 and sent[0][1].startswith("[UPDATED]") and "Extended" in sent[0][1]
    _, again = refresh(conn, adapter, "sample_v2_extended.html", now=NOW + timedelta(hours=2))
    assert again == []


def test_withdrawal_alert_and_filter_matching(conn, adapter):
    add_sub(conn, "north", area="North Ring")
    add_sub(conn, "other route", route="999")
    refresh(conn, adapter, "sample_v1.html")
    _, sent = refresh(conn, adapter, "sample_v2_extended.html", now=NOW + timedelta(hours=1))
    assert [m for _, m in sent if m.startswith("[WITHDRAWN]")] and all(label == "north" for label, _ in sent)


def test_no_alert_for_already_expired_notice(conn, adapter):
    add_sub(conn, "old stop", route="7")
    _, sent = refresh(conn, adapter, "sample_v1.html")
    assert sent == []


def test_database_blocks_duplicate_alert_rows(conn, adapter):
    add_sub(conn, "x", route="45A")
    s, _ = refresh(conn, adapter, "sample_v1.html")
    assert alerts.queue_alerts(conn, s.events, TZ, now=NOW) == 0     # forced re-queue creates nothing


def test_failed_delivery_is_logged_and_retried_without_duplicates(conn, adapter):
    add_sub(conn, "flaky", route="45A")
    s = refresh_source(conn, adapter, FakeFetcher("sample_v1.html"), TZ, now=NOW)
    def boom(sub, msg): raise RuntimeError("smtp down")
    alerts.process_events(conn, s.events, TZ, now=NOW, sender=boom)
    assert conn.execute("SELECT alert_status FROM alerts").fetchone()[0] == "failed"
    got = []
    alerts.deliver_pending(conn, now=NOW, sender=lambda sub, msg: got.append(msg))
    assert len(got) == 1 and conn.execute("SELECT alert_status FROM alerts").fetchone()[0] == "sent"
    assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 1
