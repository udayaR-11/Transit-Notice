# Final report skeleton (brief section 12)
1. Cover page: title, student/team IDs, mentor, academic year
2. Abstract & context: problem (passengers lack one clear place for diversions), stakeholders, success criteria (see README)
3. Source selection: permission/robots/terms review, URLs, crawl policy (`docs/source_approval.md`)
4. SRS: use cases, functional/non-functional requirements, architecture (README project map), ER diagram (`docs/er_diagram.md`)
5. Implementation: collection logic (fetcher+adapter), normalisation, scheduling, change detection (`services/`)
6. Testing: test cases, sample inputs (`fixtures/`), expected vs actual, screenshots (`docs/testing.md`)
7. Evaluation: collection quality, precision of alerts, refresh time (see `refresh_logs`), limitations
8. Deployment: setup steps, sanitised `.env.example`, monitoring via Admin -> refresh log
9. Ethics & conclusion: privacy (no personal data), compliance (robots/terms/rate limits), known gaps, future work (push/email/SMS channel, GTFS-realtime feed, multi-agency)
10. Appendix: source-attributed screenshots, sample records, Git commit evidence
