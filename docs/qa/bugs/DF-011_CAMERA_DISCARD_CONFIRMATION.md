# DF-011 — Camera test omits the captured-photo discard confirmation

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

The actual camera opens and captures photo 1. Cancel opens the implemented "Discard these photos?" native dialog; the test waits for Add Photos without responding.

[Sanitized result and source sites](../evidence/DF-011/failure.json).
Private original video/JUnit remain in `output/android-all-2026-11-09/full-retest-artifacts/`.

## Candidate and acceptance

Exercise Keep taking photos, confirm the capture remains, then cancel again and explicitly Discard before asserting an empty form.

Acceptance: Capture/cancel/keep/discard/retry/use all pass on the same camera build/device and cleanup succeeds.

The candidate passed host checks; verified hardware results are recorded below. Original outcomes
remain preserved. This candidate changes the test harness only, not the app,
backend or production settings.

## Verified retest

Run `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. The affected device check passed. This closes the automation defect only.
