# DF-012 — Creation success assumes visible card count grows

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

Fresh creation returns to the closet but the test times out waiting for the visible accessibility card count to increase. The screenshot still has two cards: the new first draft and the prior first card. Off-screen cards are pruned by the UI. Server mutation inspection is required before another creation.

[Sanitized result and source sites](../evidence/DF-012/failure.json).
Private original video/JUnit remain in `output/android-all-2026-11-09/full-retest-artifacts/`.

## Candidate and acceptance

Accept a newly inserted first card as well as a growing visible count, but reject an unchanged viewport. Inspect and clean only an identified disposable draft before retrying; retain the original failed outcome.

Acceptance: A new, identified draft completes analysis and mannequin generation and is published on a complete fresh retest; existing fixtures remain intact.

The candidate passed host checks; verified hardware results are recorded below. Original outcomes
remain preserved. This candidate changes the test harness only, not the app,
backend or production settings.

## Verified retest

Same staging build 4 and Pixel 9 Pro XL / Android 15, run `6e980389-92c4-412d-be20-738b773a352e`. Fresh creation passed the new-card assertion and reached the analysis detail screen in run 6e980389-92c4-412d-be20-738b773a352e. Its later modal-navigation failure is separately tracked as DF-016; the full business flow is not yet a pass.
