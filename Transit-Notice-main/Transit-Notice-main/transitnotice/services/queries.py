"""Read side: search/filter notices and build dashboard data."""
from datetime import datetime, time, timedelta

from services.status import ACTIVE, UPCOMING, compute_status, freshness
from services.timeutil import UTC, from_iso, to_iso

DEFAULT_STATUSES = {ACTIVE, UPCOMING}


def _day_bounds(date_str, tz):
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    start = datetime.combine(d, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(d, time.max.replace(microsecond=0), tzinfo=tz).astimezone(UTC)
    return to_iso(start), to_iso(end)


def search_notices(conn, *, tz, now, q="", route="", station="", area="", date="", status="current"):
    """status: current (active+upcoming) | active | upcoming | expired | withdrawn | all"""
    where, params = ["1=1"], []
    if q:
        where.append("(n.title LIKE ? OR n.summary LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if route:
        where.append("EXISTS (SELECT 1 FROM notice_routes r WHERE r.notice_id=n.notice_id AND r.route_id=?)")
        params.append(route.strip().upper().replace(" ", ""))
    if station:
        where.append("EXISTS (SELECT 1 FROM notice_stations s WHERE s.notice_id=n.notice_id AND s.station LIKE ?)")
        params.append(f"%{station}%")
    if area:
        where.append("n.area LIKE ?")
        params.append(f"%{area}%")
    if date:
        try:
            start, end = _day_bounds(date, tz)
        except ValueError:
            start = end = None
        if start:
            where.append("n.valid_from <= ? AND (n.valid_to IS NULL OR n.valid_to >= ?)")
            params += [end, start]

    rows = conn.execute(
        f"SELECT n.* FROM notices n WHERE {' AND '.join(where)} ORDER BY n.valid_from DESC", params).fetchall()

    src = {r["source_key"]: r for r in conn.execute("SELECT * FROM sources")}
    stale_after = _stale_minutes()
    out = []
    for row in rows:
        d = dict(row)
        d["state"] = compute_status(d["valid_from"], d["valid_to"], d["status"], now)
        if status == "current" and d["state"] not in DEFAULT_STATUSES:
            continue
        if status not in ("current", "all") and d["state"] != status:
            continue
        d["routes"] = sorted(r["route_id"] for r in conn.execute(
            "SELECT route_id FROM notice_routes WHERE notice_id=?", (d["notice_id"],)))
        d["stations"] = sorted(r["station"] for r in conn.execute(
            "SELECT station FROM notice_stations WHERE notice_id=?", (d["notice_id"],)))
        d["open_ended"] = d["valid_to"] is None
        d["source_stale"] = freshness(src.get(d["source_key"]), now, stale_after)["stale"]
        d["relative"], d["progress"] = relative_info(d, now)
        out.append(d)
    # active first, then upcoming, then the rest
    order = {ACTIVE: 0, UPCOMING: 1}
    out.sort(key=lambda d: (order.get(d["state"], 2), d["valid_from"]), reverse=False)
    return out


def _stale_minutes():
    from config import config
    return config.STALE_AFTER_MINUTES


def source_freshness(conn, now):
    stale_after = _stale_minutes()
    return [
        {"source": dict(r), **freshness(r, now, stale_after)}
        for r in conn.execute("SELECT * FROM sources ORDER BY source_key")
    ]


def type_counts(notices):
    counts = {}
    for n in notices:
        if n["state"] == ACTIVE:
            counts[n["type"]] = counts.get(n["type"], 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def revisions(conn, notice_id):
    return conn.execute(
        "SELECT * FROM notice_revisions WHERE notice_id=? ORDER BY revision_id DESC", (notice_id,)).fetchall()


def _span(seconds):
    s = int(abs(seconds))
    if s < 3600:
        m = max(1, s // 60)
        return f"{m} min"
    if s < 86400:
        h = s // 3600
        return f"{h} hour{'s' if h != 1 else ''}"
    d = s // 86400
    return f"{d} day{'s' if d != 1 else ''}"


def relative_info(n, now):
    """Human text ('Ends in 3 days') and elapsed-percent for the progress bar."""
    vf, vt = from_iso(n["valid_from"]), from_iso(n["valid_to"]) if n["valid_to"] else None
    state = n["state"]
    if state == "withdrawn":
        return "Withdrawn by the authority", 100
    if state == "upcoming":
        return f"Starts in {_span((vf - now).total_seconds())}", 0
    if state == "expired":
        return f"Ended {_span((now - vt).total_seconds())} ago", 100
    if vt is None:
        return "Ongoing, no end date announced", None
    total = max((vt - vf).total_seconds(), 1)
    pct = int(min(max((now - vf).total_seconds() / total, 0), 1) * 100)
    return f"Ends in {_span((vt - now).total_seconds())}", pct


def timeline(notices, now, tz, days=14, max_rows=10):
    """Gantt-style rows for active/upcoming notices over the next `days` days (source time zone)."""
    local_now = now.astimezone(tz)
    start = datetime.combine(local_now.date(), time.min, tzinfo=tz).astimezone(UTC)
    end = start + timedelta(days=days)
    span = (end - start).total_seconds()
    pct = lambda dt: min(max((dt - start).total_seconds() / span * 100, 0), 100)
    rows = []
    for n in notices:
        if n["state"] not in ("active", "upcoming"):
            continue
        vf = from_iso(n["valid_from"])
        vt = from_iso(n["valid_to"]) if n["valid_to"] else None
        if vf >= end or (vt is not None and vt < start):
            continue
        left = pct(vf)
        right = 100 if vt is None or vt >= end else pct(vt)
        rows.append({"notice_id": n["notice_id"], "routes": n["routes"], "title": n["title"], "state": n["state"],
                     "type": n["type"], "left": round(left, 2), "width": round(max(right - left, 1.5), 2),
                     "open_ended": vt is None, "runs_on": vt is None or vt >= end})
        if len(rows) >= max_rows:
            break
    ticks = []
    for i in range(days):
        day = (start + timedelta(days=i)).astimezone(tz)
        ticks.append({"label": day.strftime("%d"), "dow": day.strftime("%a"), "left": round(i / days * 100, 2),
                      "weekend": day.weekday() >= 5})
    return {"rows": rows, "ticks": ticks, "now_left": round(pct(now), 2), "days": days,
            "from_label": start.astimezone(tz).strftime("%d %b"),
            "to_label": (end - timedelta(seconds=1)).astimezone(tz).strftime("%d %b")}


def overview(notices):
    """Counts for the stat tiles, from an UNFILTERED list."""
    c = {"active": 0, "upcoming": 0, "expired": 0, "withdrawn": 0}
    for n in notices:
        c[n["state"]] += 1
    c["current"] = c["active"] + c["upcoming"]
    c["all"] = len(notices)
    c["open_ended"] = sum(1 for n in notices if n["state"] == "active" and n["open_ended"])
    c["routes"] = len({r for n in notices if n["state"] == "active" for r in n["routes"]})
    return c
