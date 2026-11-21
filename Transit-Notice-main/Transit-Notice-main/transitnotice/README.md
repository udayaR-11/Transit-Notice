# TransitNotice - Public Transport Service Update Tracker (WEB-07)

Monitors **official, publicly available** transport advisories, extracts affected routes and effective
windows, tracks revisions/withdrawals, and shows passengers what is active **with an honest freshness label**.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # then edit TN_ADMIN_TOKEN
python scripts/seed_demo_source.py                      # creates data/demo_source.html (fake authority page)
python app.py                                           # http://127.0.0.1:5000
```
The app serves its own demo authority page at `/demo-source/advisories`, so the whole pipeline
(robots check -> fetch -> parse -> store -> alert) runs offline. The scheduler refreshes every
`TN_REFRESH_MINUTES`; you can also use **Admin -> Refresh now** or `python -m scripts.refresh_once`.

## Run the tests
```bash
python -m pytest -q          # 55 tests
```

## Practise the mentor's live challenges (CP-5 / CP-6)
```bash
python scripts/mentor_challenge.py extend-outage   # outage +24h  -> revision 2, "Extended from ... to ..." + one alert
python scripts/mentor_challenge.py no-end-date     # advisory with no end date -> open-ended, stays active
python scripts/mentor_challenge.py withdraw        # notice removed from page -> withdrawn (kept in archive)
python scripts/mentor_challenge.py break-layout    # page layout changes -> refresh FAILS, old data untouched
python scripts/mentor_challenge.py reset
```
After each one: Admin -> Refresh now, then look at the dashboard, `/notice/<id>` history and `logs/alerts.log`.

## Using a REAL transport authority source
1. Complete `docs/source_approval.md` (permissions, robots.txt, terms, fields, schedule, risks, API/RSS alternative). Get mentor approval at CP-1.
2. Copy `scraper/adapters/demo.py` -> `scraper/adapters/<agency>.py`; change only the CSS selectors in `parse()`.
3. Register it in `scraper/registry.py`, set `TN_SOURCES=<key>` and a polite `TN_USER_AGENT` with your contact.
4. Save 2-3 real pages into `fixtures/` and write parsing tests like `tests/test_ingest.py`.
Prefer an official **API / RSS / open-data feed** over scraping HTML whenever one exists.

## Project map
| Path | Purpose |
|---|---|
| `scraper/fetcher.py` | robots.txt check, per-host rate limit, timeout, retry + exponential backoff, retry ceiling |
| `scraper/adapters/` | one adapter per source; `parse()` never dies on a single bad record |
| `services/normalize.py` | clean fields, routes -> `45A`, type mapping, content hash, stable `notice_id` |
| `services/ingest.py` | idempotent upsert, revisions, change summary, withdrawal, failure handling (one DB transaction) |
| `services/status.py` | status is **computed** from the time window; freshness/stale logic |
| `services/alerts.py` | de-duplicated alerts (DB UNIQUE key), delivery log, retry of failed deliveries |
| `services/refresh.py` | refresh orchestration + background scheduler (single-run lock) |
| `migrations/` | ordered SQL migrations applied by `db.py` |
| `tests/`, `fixtures/` | acceptance tests + malformed/missing/duplicate/unavailable fixtures |

## Design decisions (good viva answers)
* **Time zone:** see `docs/timezone.md`. Store UTC, parse source-local, display source-local.
* **Status is derived, not stored** - an expired advisory can never remain "active" because a job did not run.
* **A failed refresh changes nothing** except `sources.last_error` / `consecutive_failures`; `last_success_at` is not advanced, so the UI says *"could not confirm these updates are current"* and tags notices *"Unverified since last check"*.
* **Missing end date = open-ended** (`valid_to IS NULL`), shown as "no end date announced", never guessed.
* **Withdrawn vs expired:** missing from the page *before* its end date = withdrawn (kept); past its end date = expired (archive).
* **Layout change protection:** if the expected container is missing the run fails instead of treating an empty parse as "everything withdrawn".
* **Idempotency:** `notice_id` is stable (source ref, or a hash that excludes the end date); `content_hash` decides new vs unchanged vs revised.
* **One alert per revision:** `UNIQUE(notice_id, revision_id, subscriber_id, kind)` in the database.
* **Security:** admin token (constant-time compare), secrets only in env, Jinja auto-escaping, only `http(s)` links rendered from scraped URLs, parameterised SQL everywhere.
* **Limitations (state these in the report):** scheduled polling is not real-time; notices appear only after the authority publishes them; parsers break when pages change; alerts are demo-logged unless a delivery channel is added.
