# DF-013 — Photo recovery assumes an undeclared full-library permission on Android 15

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

The APK does not declare READ_MEDIA_IMAGES. Installed Expo ImagePicker native code requests an empty permission array on API 33+, using the scoped system picker. The original test correctly reported Blocked rather than passing an unsupported permission denial.

[Sanitized result and source sites](../evidence/DF-013/failure.json).
Private original video/JUnit remain in `output/android-all-2026-11-09/full-retest-artifacts/`.

## Candidate and acceptance

On API 33+ with no requested library permission, test opening/cancelling the scoped picker, prove zero attachments, then reopen/select fixture photos. Preserve the runtime revoke/deny/grant branch for applicable builds. Record which branch executed.

Acceptance: Scoped picker refusal/retry passes with attachment and cleanup evidence. Do not claim a full-library permission denial was exercised on this APK.

The candidate passed host checks; hardware verification is recorded below. Original outcomes
remain preserved. This candidate changes the test harness only, not the app,
backend or production settings.

The first focused retest failed earlier in Create-tab navigation. Separately, fresh creation showed the Compose picker with three photos, but no legacy `icon_thumbnail` resource IDs. The selector now supports system-picker `Photo taken on …` accessibility descriptions as well as legacy resource IDs. This candidate requires another device retest.

The second focused run exposed a separate helper error before photo selection: after cancelling the picker, Create is already open as a modal without the footer. The navigation helper now recognizes its current destination instead of waiting for a hidden Create tab. Another focused device check is required.

## Verified retest

Run `fda90d39-831c-4786-8edd-fece9ec0b51c`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. The scoped-picker cancellation/retry branch passed with four cleanup operations and zero cleanup failures. This APK does not request full-library permission; a full-library deny/grant scenario was not exercised.
