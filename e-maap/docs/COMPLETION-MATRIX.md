# Twelve-capability traceability

“Source implemented” describes code, not a passed deployable-prototype acceptance gate. Tests below have passed on the isolated API test database; PostgreSQL and phone validation remain open.

| Capability | Screen/source | API | Database and control | Acceptance proof / remaining gate |
|---|---|---|---|---|
| I1 Assigned inspection | mobile App, Inspection | assignments/me; download; cases/{id} | assignments, cases; assigned-Inspector RBAC | Role-negative API tests; physical phone gate open |
| I2 Adaptive evidence | mobile Capture, store | evidence-plan; capture-profile; evidence; content | evidence_items, evidence_plan_items; stable ID/hash, private preservation | T1/T5/T6 API/domain; native capture gate open |
| I3 Quality/coverage | mobile quality, Capture; backend quality/domain | upload; coverage-confirmations | quality_json, coverage state, audit | T1/T2/T11/T14 domain; empirical device calibration open |
| I4 Grounded extraction | compliance ocr/domain/service; mobile Inspection | analysis; analysis status; compliance-map | candidates, declarations, versioned rule_results | T3/T4/T12–14/T16 domain; real Paddle gate open |
| I5 Compliance Map | mobile Inspection; web EvidenceWorkbench | compliance-map | source IDs, geometry, OCR alternatives, review flags | Inspector API path and TS/bundle checks; VUI/device gate open |
| I6 Verification/report | mobile Inspection; verification/reports modules | declaration review; finding verification; reports | separate audit review/events; report guard; actual PDF/DOCX | T5–7, integration through report download passed |
| G1 Explainable queue | web Overview/Cases/CaseOperations | government/dashboard; cases; priority | cases.priority_reasons retains computation and override | API reads and role-negative priority override/audit regression passed |
| G2 Context/repository/listing | CopilotPanel, RepositoryPage, ListingReview | copilot; brief approval; repository; reports | persisted draft/approval audit; SQL filters; source-labelled upload | T9/T10/T15/T17 and report retrieval API passed |
| G3 Verified patterns | PatternsPage/PatternPage | patterns; detail; decision | finding verification and field identity gate; pattern members | T8 exclusions; pattern approval integration passed |
| G4 Coordinated action | CasePage/FollowupPanel; mobile assignment workspace | systemic-case; assign; followups | separate officer approvals; guarded follow-up sequence; audit | T10 and ASSIGNED→IN_PROGRESS→COMPLETED API/domain passed |
| C1 Citizen scan | mobile App/Capture/Citizen | citizen session/scans/analysis/result; scoped upload | owned session, public-safe result snapshot | Preliminary scan API passed; native camera gate open |
| C2 Complaint/tracking | mobile Citizen/Tracking | complaints; status | confirmed product/shop snapshot, private tracking token | Citizen submission/tracking API passed |

## Approved addendum mapping

1. Citizen access: dedicated `/citizen/scans/{id}/analysis`, `/citizen/analysis/{id}`, `/citizen/scans/{id}/result`; allowlisted snapshot; role and ownership tests.
2. Profile/manual coverage: assigned Inspector endpoints, `ProductSnapshot`, `EvidencePlanItem`, audit events; no Other auto-completeness.
3. Priority override: Government PATCH, original computed factors retained in JSON plus override/audit.
4. Brief approval: persisted audit snapshots store content, source references, creator/editor, DRAFT/APPROVED/REJECTED and approval identity/time/reason; assignment rejects an unapproved referenced brief.
5. Follow-up: minimal ASSIGNED/IN_PROGRESS/COMPLETED enum, role/previous-state guards and audit.
6. Declaration review: source-linked audit snapshots separate from potential-finding verification events. Correction can rerun deterministic checks but never silently accepts a finding.

Original SRS identifiers remain primary. The API OpenAPI export and PostgreSQL DDL accompany this matrix; no additional product capability has been introduced.
