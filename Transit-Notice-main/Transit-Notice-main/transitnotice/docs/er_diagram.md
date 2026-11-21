# Database ER diagram (paste into https://mermaid.live to export as an image for the report)

```mermaid
erDiagram
    sources ||--o{ notices : publishes
    sources ||--o{ refresh_logs : "is refreshed by"
    notices ||--|{ notice_routes : affects
    notices ||--o{ notice_stations : "affects stops"
    notices ||--|{ notice_revisions : "has history"
    notices ||--o{ alerts : triggers
    subscribers ||--o{ alerts : receives

    sources { text source_key PK
              text agency
              text page_url
              text last_attempt_at
              text last_success_at
              text last_error
              int consecutive_failures }
    notices { text notice_id PK
              text source_key FK
              text agency
              text area
              text source_url
              text type
              text summary
              text published_at
              text valid_from
              text valid_to "NULL = open-ended"
              text status "published|withdrawn"
              text observed_at
              text last_confirmed_at
              text content_hash
              int revision_id
              text change_summary }
    notice_routes { text notice_id PK
                    text route_id PK }
    notice_revisions { text notice_id PK
                       int revision_id PK
                       text content_hash
                       text valid_to
                       text change_summary }
    subscribers { int id PK
                  text label
                  text filter_route
                  text filter_area }
    alerts { int id PK
             text notice_id FK
             int revision_id
             int subscriber_id FK
             text kind
             text alert_status
             text alerted_at }
    refresh_logs { int id PK
                   text source_key
                   text outcome
                   int new_count
                   int revised_count
                   text error }
```
Required fields from the brief map to: `notice_id, agency, route_id (notice_routes), area, source_url, type, summary,
published_at, valid_from, valid_to, status, observed_at, last_confirmed_at, content_hash, revision_id,
change_summary, subscriber_filter (subscribers.filter_*), alert_status, alerted_at (alerts)`.
