# Source approval document (CP-1)  - fill in before scraping any real site

| Item | Your entry |
|---|---|
| Agency / authority name | |
| Advisory page URL(s) | |
| Official API / RSS / open-data feed available? | (If yes, use it instead of scraping HTML.) |
| robots.txt URL and relevant rules | |
| Terms of use reviewed (link, date, what they allow) | |
| Login / CAPTCHA / paywall? | Must be **No**. If yes, choose another source. |
| Personal data on the page? | Must be **No**. Collect only route/notice data (data minimisation). |
| Fields extracted | route, area, stations, type, summary, published, valid from/to, source URL |
| Refresh schedule | e.g. every 15 min; backoff on errors; min 2 s between requests |
| User-Agent + contact | |
| Risks | page layout change, rate limiting, ambiguous dates, missing end date, source downtime |
| Mitigation | adapter tests with saved fixtures, fail-safe refresh, freshness labels, structure check |
| Fallback if scraping is not permitted | ask the authority for permission / use feed / use bundled demo source |
| Mentor approval (name, date) | |

## Personas (required by the brief)
1. **Daily commuter (e.g. Priya, college student):** needs to know before leaving home whether her route is diverted today; wants a filter by route and a clear active/expired status.
2. **Occasional traveller / elderly passenger (e.g. Mr. Kumar):** travels on specific days; needs the date filter, plain language and a link to the official notice.
Optional: **Transport-desk volunteer** who monitors many routes and wants the change history.

## Usefulness and limits of scheduled public-source monitoring
* Useful: one searchable place, history of changes, de-duplicated alerts, honest "last verified" time.
* Limits: polling delay (up to one interval), depends on what the authority publishes, not real-time vehicle data, parsers can break when pages change, we cannot confirm a notice is still true beyond the last check.
