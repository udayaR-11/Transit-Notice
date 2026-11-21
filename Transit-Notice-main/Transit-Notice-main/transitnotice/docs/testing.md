# Test plan (maps to brief section 11)
| Mandatory acceptance test | Test |
|---|---|
| Expired advisory is not marked active | `test_AT1_expired_advisory_is_not_marked_active` |
| Route ID filtering works with multiple affected routes | `test_AT2_route_filter_works_with_multiple_affected_routes` |
| Extended advisory updates existing notice history | `test_AT3_extended_advisory_updates_existing_notice_history` |
| Time-zone handling documented and reproducible | `docs/timezone.md`, `tests/test_normalize.py` |
| Stale notice shows latest known verification | `test_AT5_stale_notice_shows_latest_known_verification` |
| Source error does not turn old data into live data | `test_AT6_source_error_does_not_turn_old_data_into_live_data` |

Extra: malformed HTML, missing fields, duplicates, layout change, error page, no end date, withdrawal/reinstatement,
idempotent re-runs, alert de-duplication and retry, retry/backoff/robots/rate-limit, XSS/unsafe-link escaping, admin auth.
Run: `python -m pytest -v` and attach the output + dashboard screenshots to the report (section 12 "Testing").
