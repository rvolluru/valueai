# DF-020 — Nested card/image labels are mistaken for two listings

- Status: Closed
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Run: `b8242749-e6c6-443d-8eb6-4cd998bc9ae0`
- Device/build: Pixel 9 Pro XL / Android 15, staging Android 0.1.0 (4)

Marketplace search finds the uniquely seeded fixture, but `open_listing` rejects its accessibility target count before clicking. The app's marketplace card exposes both its outer pressable and nested image with the same View details label. The fixture setup pins unique IDs/titles; duplicate accessibility nodes do not establish duplicate listings.

Candidate: group identical/contained card rectangles and select the nested image for one card. Continue rejecting distinct same-title cards. Three host tests cover nested targets, duplicate query results and genuinely separate cards. Hardware gallery retest is required. No app/backend changes or publication-policy changes.

[Single visible fixture card at failure](../evidence/DF-020/single-card-before-fix.png) and [original case outcomes](../evidence/DF-020/before-fix-results.json).

## Verified retest

All three affected gallery cases passed in `44210bd2-be1b-4889-8af8-0b298794d6b9`, same staging build 4 / Pixel 9 Pro XL / Android 15. [Retest outcomes](../evidence/account-b-setup-2026-11-09/cross-r2-results.json). The separate-card ambiguity host test remains enforced.
