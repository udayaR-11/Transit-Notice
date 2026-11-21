-- Core schema. All timestamps are stored as UTC ISO-8601 strings (e.g. 2026-10-28T00:30:00+00:00).
CREATE TABLE IF NOT EXISTS sources (
    source_key           TEXT PRIMARY KEY,
    agency               TEXT NOT NULL,
    page_url             TEXT NOT NULL,
    last_attempt_at      TEXT,
    last_success_at      TEXT,
    last_error           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notices (
    notice_id      TEXT PRIMARY KEY,                 -- "<source_key>:<external ref>"
    source_key     TEXT NOT NULL REFERENCES sources(source_key),
    agency         TEXT NOT NULL,
    area           TEXT,
    source_url     TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN
                     ('DIVERSION','SUSPENSION','DELAY','SCHEDULE_CHANGE','STOP_CLOSURE','OTHER')),
    title          TEXT NOT NULL,
    summary        TEXT NOT NULL,
    published_at   TEXT,
    valid_from     TEXT NOT NULL,
    valid_to       TEXT,                              -- NULL = open-ended (no end date announced)
    status         TEXT NOT NULL DEFAULT 'published'
                     CHECK (status IN ('published','withdrawn')),
    observed_at    TEXT NOT NULL,                     -- first time we saw it
    last_confirmed_at TEXT NOT NULL,                  -- last successful refresh that still listed it
    content_hash   TEXT NOT NULL,
    revision_id    INTEGER NOT NULL DEFAULT 1,
    change_summary TEXT
);

CREATE TABLE IF NOT EXISTS notice_routes (
    notice_id TEXT NOT NULL REFERENCES notices(notice_id) ON DELETE CASCADE,
    route_id  TEXT NOT NULL,
    PRIMARY KEY (notice_id, route_id)
);

CREATE TABLE IF NOT EXISTS notice_stations (
    notice_id TEXT NOT NULL REFERENCES notices(notice_id) ON DELETE CASCADE,
    station   TEXT NOT NULL,
    PRIMARY KEY (notice_id, station)
);

-- Every observed version of a notice (change history).
CREATE TABLE IF NOT EXISTS notice_revisions (
    notice_id      TEXT NOT NULL REFERENCES notices(notice_id) ON DELETE CASCADE,
    revision_id    INTEGER NOT NULL,
    content_hash   TEXT NOT NULL,
    type           TEXT NOT NULL,
    summary        TEXT NOT NULL,
    valid_from     TEXT NOT NULL,
    valid_to       TEXT,
    routes         TEXT NOT NULL,                     -- comma separated snapshot
    observed_at    TEXT NOT NULL,
    change_summary TEXT,
    PRIMARY KEY (notice_id, revision_id)
);

CREATE INDEX IF NOT EXISTS idx_notices_window ON notices(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_routes_route ON notice_routes(route_id);

CREATE TABLE IF NOT EXISTS refresh_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key  TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    outcome     TEXT NOT NULL CHECK (outcome IN ('success','partial','failed')),
    items_found INTEGER NOT NULL DEFAULT 0,
    new_count       INTEGER NOT NULL DEFAULT 0,
    revised_count   INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    withdrawn_count INTEGER NOT NULL DEFAULT 0,
    skipped_count   INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
