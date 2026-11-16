# DF-006 — Unicode text selector cannot find notification-history button

- Status: Closed
- Classification: Automation (verified selector fix)
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Case: `test_notification_history`
- Environment/build: staging Android 0.1.0 (4), EAS `777562a3-e97d-4c64-a784-612d6179eafe`
- Device: Pixel 9 Pro XL / Android 15
- Failing run: `20592dbb-482d-4570-953e-157b90ec3eb5`
- Mutation outcome: none; this is a read-only activity-history check

The shared `tap` helper times out looking up `Notifications — View all activity`.
The button exists in the exact uploaded native source, immediately below the
Profile header. The UiAutomator query builder serialized the em dash as the
literal ASCII `\u2014` escape rather than emitting the actual label character.

[Sanitized failure source sites](../evidence/DF-006/failure.json).
Candidate: emit UTF-8 Unicode characters in text/regex/XPath selector literals,
retaining JSON escaping for quotes/backslashes. A focused host check verifies the
actual em dash reaches the UiAutomator query and selects the intended control.

Acceptance: the same test opens Notifications on the same native build/device.
Keep this candidate cause provisional until that hardware retest succeeds; a
source-level control match alone is not proof of visible runtime behavior.
No native app deployment is required for this harness change.

## Verified retest

Notification history passed on staging Android build 4 / Pixel 9 Pro XL / Android 15 in run `6e980389-92c4-412d-be20-738b773a352e`. The first focused run failed before reaching this lookup; that outcome remains retained. Profile navigation uses the documented DF-014 workaround, which does not close the application overlap defect.
