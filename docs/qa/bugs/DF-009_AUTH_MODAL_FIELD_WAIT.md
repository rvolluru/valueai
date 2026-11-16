# DF-009 — Negative sign-in tests read a partially rendered modal

- Status: Closed
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Native build: staging Android 0.1.0 (4), EAS `777562a3-e97d-4c64-a784-612d6179eafe`
- Device: Google Pixel 9 Pro XL / Android 15
- Original run: `20592dbb-482d-4570-953e-157b90ec3eb5`

## Observation and evidence

Invalid-sign-in and empty-required-field cases assert fewer than two EditTexts immediately after opening the animated modal. The malformed-identifier branch passed in the same run.

[Sanitized result and source sites](../evidence/DF-009/failure.json).
Private original video/JUnit remain in `output/android-all-2026-11-09/full-retest-artifacts/`.

## Candidate and acceptance

Wait for at least two enabled, visible credential inputs; use the same helper for standard login and negative tests. A host check exercises empty, partial and ready states.

Acceptance: Invalid, empty and malformed-identifier cases all run their validation assertions on the original device/build.

The candidate passed host checks; verified hardware results are recorded below. Original outcomes
remain preserved. This candidate changes the test harness only, not the app,
backend or production settings.

## Verified retest

Same staging build 4 and Pixel 9 Pro XL / Android 15, run `6e980389-92c4-412d-be20-738b773a352e`. Invalid-credentials and malformed-email checks passed, and the empty-email case reached validation with both editable fields. Its remaining wording mismatch is separately tracked as DF-015.
