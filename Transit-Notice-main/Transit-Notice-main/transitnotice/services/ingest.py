"""Refresh one source: fetch -> parse -> normalise -> idempotent upsert -> change detection.

Guarantees
* Idempotent: running the same page twice changes nothing but last_confirmed_at.
* A failed fetch/parse NEVER touches stored notices (old data is never promoted to 'live';
  the UI shows the last successful verification time instead).
* Every content change creates a numbered revision, so extensions/edits keep their history.
* A notice that disappears before its end date is marked withdrawn (kept for the archive).
"""
import logging
from dataclasses import dataclass, field

from scraper.base import StructureError
from scraper.fetcher import FetchError
from services.normalize import NormalizeError, normalize
from services.timeutil import fmt_local, from_iso, to_iso, utcnow

log = logging.getLogger("transitnotice.ingest")


@dataclass
class RefreshSummary:
    source_key: str
    outcome: str = "failed"
    items_found: int = 0
    new: int = 0
    revised: int = 0
    unchanged: int = 0
    withdrawn: int = 0
    skipped: int = 0
    error: str = ""
    issues: list = field(default_factory=list)
    events: list = field(default_factory=list)   # (notice_id, revision_id, kind)


def _describe_change(old, new, tz):
    parts = []
    if old["valid_to"] != new.valid_to:
        if old["valid_to"] is None:
            parts.append(f"End date set: {fmt_local(new.valid_to, tz)}")
        elif new.valid_to is None:
            parts.append("End date removed (open-ended)")
        elif from_iso(new.valid_to) > from_iso(old["valid_to"]):
            parts.append(f"Extended from {fmt_local(old['valid_to'], tz)} to {fmt_local(new.valid_to, tz)}")
        else:
            parts.append(f"Shortened from {fmt_local(old['valid_to'], tz)} to {fmt_local(new.valid_to, tz)}")
    if old["valid_from"] != new.valid_from:
        parts.append(f"Start changed to {fmt_local(new.valid_from, tz)}")
    if old["type"] != new.type:
        parts.append(f"Type changed {old['type']} -> {new.type}")
    if old["_routes"] != sorted(new.routes):
        added = sorted(set(new.routes) - set(old["_routes"]))
        removed = sorted(set(old["_routes"]) - set(new.routes))
        if added:
            parts.append("Routes added: " + ", ".join(added))
        if removed:
            parts.append("Routes removed: " + ", ".join(removed))
    if old["summary"] != new.summary:
        parts.append("Notice text updated")
    if old["area"] != new.area or old["_stations"] != sorted(new.stations):
        parts.append("Area/stations updated")
    return "; ".join(parts) or "Content updated"


def _load_routes(conn, notice_id):
    return sorted(r["route_id"] for r in conn.execute(
        "SELECT route_id FROM notice_routes WHERE notice_id=?", (notice_id,)))


def _load_stations(conn, notice_id):
    return sorted(r["station"] for r in conn.execute(
        "SELECT station FROM notice_stations WHERE notice_id=?", (notice_id,)))


def _replace_children(conn, n):
    conn.execute("DELETE FROM notice_routes WHERE notice_id=?", (n.notice_id,))
    conn.execute("DELETE FROM notice_stations WHERE notice_id=?", (n.notice_id,))
    conn.executemany("INSERT INTO notice_routes(notice_id, route_id) VALUES (?,?)",
                     [(n.notice_id, r) for r in n.routes])
    conn.executemany("INSERT OR IGNORE INTO notice_stations(notice_id, station) VALUES (?,?)",
                     [(n.notice_id, s) for s in n.stations])


def _write_revision(conn, n, revision_id, observed_iso, change_summary):
    conn.execute(
        """INSERT INTO notice_revisions(notice_id, revision_id, content_hash, type, summary, valid_from,
           valid_to, routes, observed_at, change_summary) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (n.notice_id, revision_id, n.content_hash, n.type, n.summary, n.valid_from, n.valid_to,
         ",".join(sorted(n.routes)), observed_iso, change_summary))


def _ensure_source(conn, adapter):
    conn.execute(
        "INSERT OR IGNORE INTO sources(source_key, agency, page_url) VALUES (?,?,?)",
        (adapter.source_key, adapter.agency, adapter.page_url))
    conn.commit()


def _record_failure(conn, adapter, summary, started_iso, now_iso, error):
    summary.outcome, summary.error = "failed", error
    conn.execute(
        """UPDATE sources SET last_attempt_at=?, last_error=?, consecutive_failures=consecutive_failures+1
           WHERE source_key=?""", (now_iso, error, adapter.source_key))
    _log_run(conn, summary, started_iso, now_iso)
    conn.commit()
    log.error("refresh failed for %s: %s", adapter.source_key, error)
    return summary


def _log_run(conn, s, started_iso, finished_iso):
    conn.execute(
        """INSERT INTO refresh_logs(source_key, started_at, finished_at, outcome, items_found, new_count,
           revised_count, unchanged_count, withdrawn_count, skipped_count, error)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (s.source_key, started_iso, finished_iso, s.outcome, s.items_found, s.new, s.revised,
         s.unchanged, s.withdrawn, s.skipped, s.error or ("; ".join(s.issues[:5]) or None)))


def refresh_source(conn, adapter, fetcher, tz, now=None):
    now = now or utcnow()
    now_iso = to_iso(now)
    started_iso = now_iso
    summary = RefreshSummary(source_key=adapter.source_key)
    _ensure_source(conn, adapter)

    # 1) fetch + parse -- any failure leaves stored data untouched
    try:
        html = fetcher.get(adapter.page_url)
        parsed = adapter.parse(html)
    except (FetchError, StructureError) as exc:
        return _record_failure(conn, adapter, summary, started_iso, now_iso, f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # unexpected parser bug: still must not corrupt data
        return _record_failure(conn, adapter, summary, started_iso, now_iso, f"Unexpected {type(exc).__name__}: {exc}")

    if not parsed.notices and parsed.issues:
        return _record_failure(conn, adapter, summary, started_iso, now_iso,
                               "page parsed but every record was unusable: " + "; ".join(parsed.issues[:3]))

    summary.issues.extend(parsed.issues)
    summary.skipped += len(parsed.issues)
    summary.items_found = len(parsed.notices)

    # 2) normalise
    seen_ids, clean = set(), {}
    for raw in parsed.notices:
        try:
            n = normalize(raw, source_key=adapter.source_key, agency=adapter.agency,
                          page_url=adapter.page_url, tz=tz)
        except NormalizeError as exc:
            summary.skipped += 1
            summary.issues.append(f"{raw.ref or raw.title[:30]!r}: {exc}")
            if raw.ref:   # still listed on the page -> must not be treated as withdrawn
                seen_ids.add(f"{adapter.source_key}:{raw.ref.strip()}")
            continue
        seen_ids.add(n.notice_id)
        if n.notice_id in clean:
            summary.skipped += 1
            summary.issues.append(f"{n.notice_id}: duplicate on page (kept first)")
            continue
        clean[n.notice_id] = n

    # 3) upsert + change detection in ONE transaction
    try:
        with conn:
            for n in clean.values():
                row = conn.execute("SELECT * FROM notices WHERE notice_id=?", (n.notice_id,)).fetchone()
                if row is None:
                    conn.execute(
                        """INSERT INTO notices(notice_id, source_key, agency, area, source_url, type, title, summary,
                           published_at, valid_from, valid_to, status, observed_at, last_confirmed_at,
                           content_hash, revision_id, change_summary)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?, 'published', ?,?,?,1,'First seen')""",
                        (n.notice_id, n.source_key, n.agency, n.area, n.source_url, n.type, n.title, n.summary,
                         n.published_at, n.valid_from, n.valid_to, now_iso, now_iso, n.content_hash))
                    _replace_children(conn, n)
                    _write_revision(conn, n, 1, now_iso, "First seen")
                    summary.new += 1
                    summary.events.append((n.notice_id, 1, "new"))
                elif row["content_hash"] == n.content_hash and row["status"] == "published":
                    conn.execute("UPDATE notices SET last_confirmed_at=? WHERE notice_id=?", (now_iso, n.notice_id))
                    summary.unchanged += 1
                else:
                    old = dict(row)
                    old["_routes"], old["_stations"] = _load_routes(conn, n.notice_id), _load_stations(conn, n.notice_id)
                    if row["status"] == "withdrawn" and row["content_hash"] == n.content_hash:
                        change = "Reinstated: notice reappeared on source page"
                    else:
                        change = _describe_change(old, n, tz)
                    rev = row["revision_id"] + 1
                    conn.execute(
                        """UPDATE notices SET area=?, source_url=?, type=?, title=?, summary=?, published_at=?,
                           valid_from=?, valid_to=?, status='published', last_confirmed_at=?, content_hash=?,
                           revision_id=?, change_summary=? WHERE notice_id=?""",
                        (n.area, n.source_url, n.type, n.title, n.summary, n.published_at, n.valid_from,
                         n.valid_to, now_iso, n.content_hash, rev, change, n.notice_id))
                    _replace_children(conn, n)
                    _write_revision(conn, n, rev, now_iso, change)
                    summary.revised += 1
                    summary.events.append((n.notice_id, rev, "revised"))

            # withdrawn = was published, not on the page any more, and its window had not ended yet
            for row in conn.execute(
                "SELECT notice_id, revision_id, content_hash, type, summary, valid_from, valid_to FROM notices "
                "WHERE source_key=? AND status='published'", (adapter.source_key,)).fetchall():
                if row["notice_id"] in seen_ids:
                    continue
                if row["valid_to"] is not None and from_iso(row["valid_to"]) < now:
                    continue  # simply expired and dropped from the page: stays in the archive as expired
                rev = row["revision_id"] + 1
                change = f"Withdrawn: removed from source page (seen missing {fmt_local(now_iso, tz)})"
                conn.execute("UPDATE notices SET status='withdrawn', revision_id=?, change_summary=? WHERE notice_id=?",
                             (rev, change, row["notice_id"]))
                routes = _load_routes(conn, row["notice_id"])
                conn.execute(
                    """INSERT INTO notice_revisions(notice_id, revision_id, content_hash, type, summary, valid_from,
                       valid_to, routes, observed_at, change_summary) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (row["notice_id"], rev, row["content_hash"], row["type"], row["summary"], row["valid_from"],
                     row["valid_to"], ",".join(routes), now_iso, change))
                summary.withdrawn += 1
                summary.events.append((row["notice_id"], rev, "withdrawn"))

            summary.outcome = "partial" if summary.skipped else "success"
            conn.execute(
                """UPDATE sources SET last_attempt_at=?, last_success_at=?, last_error=NULL, consecutive_failures=0
                   WHERE source_key=?""", (now_iso, now_iso, adapter.source_key))
            _log_run(conn, summary, started_iso, now_iso)
    except Exception as exc:
        return _record_failure(conn, adapter, summary, started_iso, now_iso, f"DB error, rolled back: {exc}")

    log.info("refresh %s: %s new=%d revised=%d unchanged=%d withdrawn=%d skipped=%d", adapter.source_key,
             summary.outcome, summary.new, summary.revised, summary.unchanged, summary.withdrawn, summary.skipped)
    return summary
