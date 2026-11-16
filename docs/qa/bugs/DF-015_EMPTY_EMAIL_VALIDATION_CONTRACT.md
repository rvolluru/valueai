# DF-015 — Empty-email validation message is missing from the test contract

- Status: Closed
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Run: `6e980389-92c4-412d-be20-738b773a352e`
- Device/build: Pixel 9 Pro XL / Android 15, staging Android 0.1.0 (4)

## Evidence

The empty-email case timed out even though the device displayed “You have to use email address.” Both input fields are blank and the user remains signed out. The existing assertion accepted other validation phrases but omitted this actual Clerk message.

[Blank-input validation screenshot](../evidence/DF-015/empty-email-validation.png).

Private video and JUnit are retained in `output/android-all-2026-11-09/focused-r4-artifacts/`.

## Candidate and acceptance

Accept the observed specific validation phrase in newly displayed text; keep requiring the signed-out state. Retest both empty and malformed identifiers.

This is a test-only repair; no app/backend or production configuration changes.

## Verified retest

Run `fda90d39-831c-4786-8edd-fece9ec0b51c`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. Both empty and malformed identifier cases passed. The observed empty-email validation message is accepted, and the test still asserts the user remains signed out.
