# DF-008 — Pricing guard expects API wording despite native preflight rejection

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

The case times out waiting for "manual pricing review". The exact native build rejects zero-value publication earlier with "manual review before publishing" and does not call the publication API.

[Sanitized result and source sites](../evidence/DF-008/failure.json).
Private original video/JUnit remain in `output/android-all-2026-11-09/full-retest-artifacts/`.

## Candidate and acceptance

Recognize both documented messages, then refresh the closet and reopen the still-reviewable draft. Do not weaken the no-publication assertion.

Acceptance: Original pricing test passes; the designated zero-value listing remains Review with pending pricing review.

The candidate passed host checks; verified hardware results are recorded below. Original outcomes
remain preserved. This candidate changes the test harness only, not the app,
backend or production settings.

## Verified retest

Run `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. The affected device check passed. This closes the automation defect only.
