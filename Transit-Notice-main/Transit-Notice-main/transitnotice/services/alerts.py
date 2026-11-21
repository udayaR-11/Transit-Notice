"""Alerting with de-duplication and a delivery log.

De-duplication is enforced by the database: UNIQUE(notice_id, revision_id, subscriber_id, kind).
Re-running a refresh (or the whole alert step) can never send the same alert twice.
Delivery mode 'demo' (default) writes to logs/alerts.log instead of emailing anyone.
"""
import logging
from pathlib import Path

from config import config
from services.status import EXPIRED, compute_status
from services.timeutil import fmt_local, to_iso, utcnow

log = logging.getLogger("transitnotice.alerts")
ALERT_LOG = Path("logs/alerts.log")

KIND_LABEL = {"new": "NEW", "revised": "UPDATED", "withdrawn": "WITHDRAWN"}


def _matches(sub, routes, area):
    if sub["filter_route"] and sub["filter_route"].strip().upper() not in routes:
        return False
    if sub["filter_area"] and sub["filter_area"].strip().lower() != (area or "").strip().lower():
        return False
    return True


def _message(n, kind, tz):
    window = fmt_local(n["valid_from"], tz) + " to " + (fmt_local(n["valid_to"], tz) if n["valid_to"] else "further notice")
    routes = ", ".join(sorted(r["route_id"] for r in n["_routes"]))
    detail = n["change_summary"] if kind != "new" else n["title"]
    return f"[{KIND_LABEL[kind]}] Route {routes}: {detail}. Valid {window}. Source: {n['source_url']}"


def queue_alerts(conn, events, tz, now=None):
    """Create one pending alert per matching subscriber for each event. Returns number created."""
    now = now or utcnow()
    subs = conn.execute("SELECT * FROM subscribers").fetchall()
    created = 0
    for notice_id, revision_id, kind in events:
        row = conn.execute("SELECT * FROM notices WHERE notice_id=?", (notice_id,)).fetchone()
        if row is None:
            continue
        n = dict(row)
        n["_routes"] = conn.execute("SELECT route_id FROM notice_routes WHERE notice_id=?", (notice_id,)).fetchall()
        if kind != "withdrawn" and compute_status(n["valid_from"], n["valid_to"], n["status"], now) == EXPIRED:
            continue  # never alert on something already over
        routes = {r["route_id"] for r in n["_routes"]}
        msg = _message(n, kind, tz)
        for sub in subs:
            if not _matches(sub, routes, n["area"]):
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO alerts(notice_id, revision_id, subscriber_id, kind, alert_status, message)
                   VALUES (?,?,?,?, 'pending', ?)""", (notice_id, revision_id, sub["id"], kind, msg))
            created += cur.rowcount
    conn.commit()
    return created


def deliver_pending(conn, now=None, sender=None):
    """Deliver pending/failed alerts. `sender(sub_row, message)` may raise -> alert marked failed."""
    now = now or utcnow()
    sender = sender or _demo_sender
    sent = 0
    rows = conn.execute(
        """SELECT a.id, a.message, s.label, s.contact FROM alerts a JOIN subscribers s ON s.id=a.subscriber_id
           WHERE a.alert_status IN ('pending','failed') ORDER BY a.id""").fetchall()
    for r in rows:
        try:
            sender(r, r["message"])
            conn.execute("UPDATE alerts SET alert_status='sent', alerted_at=? WHERE id=?", (to_iso(now), r["id"]))
            sent += 1
        except Exception as exc:
            log.error("alert %s failed: %s", r["id"], exc)
            conn.execute("UPDATE alerts SET alert_status='failed' WHERE id=?", (r["id"],))
    conn.commit()
    return sent


def _demo_sender(sub, message):
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"DEMO-DELIVERY to '{sub['label']}': {message}\n")


def process_events(conn, events, tz, now=None, sender=None):
    created = queue_alerts(conn, events, tz, now)
    sent = deliver_pending(conn, now, sender)
    return created, sent
