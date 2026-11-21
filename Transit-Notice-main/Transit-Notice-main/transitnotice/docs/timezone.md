# Time-zone handling (acceptance test: "documented and reproducible")

| Step | Rule |
|---|---|
| Source | Authority pages show local wall-clock time. Configured by `TN_SOURCE_TZ` (default `Asia/Kolkata`, UTC+05:30, no DST). |
| Parse | `28 Oct 2026 06:00` is read **as source-local**, converted to UTC -> `2026-10-28T00:30:00+00:00`. |
| Date-only values | Start = `00:00:00` local. End = `23:59:59` local (the whole last day is covered). |
| Storage | Always UTC ISO-8601 strings, so SQL comparisons are correct. |
| Display | Converted back to source time zone and labelled (`28 Oct 2026, 06:00 IST`). |
| "Now" | Every function takes `now` as a parameter; tests pin it to `2026-10-25 06:30 UTC` (12:00 IST). |
| Service-date filter | A chosen date matches a notice when its window overlaps `[00:00, 23:59:59]` of that day in source time. |

Tests: `tests/test_normalize.py::test_timezone_is_documented_and_reproducible`, `::test_date_only_end_is_inclusive_end_of_day`.
