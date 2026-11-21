"""Derived status + freshness. Status is ALWAYS computed from the announced window, never stored,
so an expired advisory cannot stay 'active' because nobody updated a column."""
from services.timeutil import from_iso

ACTIVE, UPCOMING, EXPIRED, WITHDRAWN = "active", "upcoming", "expired", "withdrawn"


def compute_status(valid_from, valid_to, stored_status, now):
    if stored_status == "withdrawn":
        return WITHDRAWN
    if from_iso(valid_from) > now:
        return UPCOMING
    if valid_to is not None and from_iso(valid_to) < now:
        return EXPIRED
    return ACTIVE  # includes open-ended notices (valid_to is NULL)


def is_stale(last_success_at, now, stale_after_minutes):
    if not last_success_at:
        return True
    return (now - from_iso(last_success_at)).total_seconds() > stale_after_minutes * 60


def freshness(source_row, now, stale_after_minutes):
    """Describe how trustworthy 'now' is for a source. Used by UI + tests."""
    if source_row is None:
        return {"state": "unknown", "stale": True, "last_success_at": None, "last_error": None}
    failing = (source_row["consecutive_failures"] or 0) > 0
    stale = is_stale(source_row["last_success_at"], now, stale_after_minutes) or failing
    return {
        "state": "stale" if stale else "live",
        "stale": stale,
        "last_success_at": source_row["last_success_at"],
        "last_attempt_at": source_row["last_attempt_at"],
        "last_error": source_row["last_error"] if failing else None,
    }
