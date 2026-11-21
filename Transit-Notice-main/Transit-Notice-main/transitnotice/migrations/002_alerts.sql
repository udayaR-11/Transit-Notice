-- Subscribers keep only what is needed (data minimisation): a label, optional contact, and filters.
CREATE TABLE IF NOT EXISTS subscribers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    label         TEXT NOT NULL,
    contact       TEXT,                               -- optional; unused in demo delivery mode
    filter_route  TEXT,                               -- NULL = any route
    filter_area   TEXT,                               -- NULL = any area
    created_at    TEXT NOT NULL
);

-- One alert per (notice revision, subscriber, kind). The UNIQUE key guarantees de-duplication.
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id     TEXT NOT NULL REFERENCES notices(notice_id) ON DELETE CASCADE,
    revision_id   INTEGER NOT NULL,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('new','revised','withdrawn')),
    alert_status  TEXT NOT NULL CHECK (alert_status IN ('pending','sent','failed')),
    alerted_at    TEXT,
    message       TEXT NOT NULL,
    UNIQUE (notice_id, revision_id, subscriber_id, kind)
);
