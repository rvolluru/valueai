# DF-007 — Empty-photo validation uses an unsupported Appium locator name

- Status: Closed
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Case: `test_create_without_photos`
- Environment/build: staging Android 0.1.0 (4), EAS `777562a3-e97d-4c64-a784-612d6179eafe`
- Device: Pixel 9 Pro XL / Android 15
- Failing run: `20592dbb-482d-4570-953e-157b90ec3eb5`
- Mutation outcome: none; no photos or listing were submitted

After reaching Add Photos and verifying `0/6`, the test raises
`InvalidSelectorException` while locating Continue. It supplied
`android uiautomator`; Appium's supported strategy is `-android uiautomator`.

[Sanitized failure source site](../evidence/DF-007/failure.json).
Candidate: use `AppiumBy.ANDROID_UIAUTOMATOR`, preserving the disabled-button and
no-navigation assertions. A focused host check executes the test against a driver
contract double and verifies the supported strategy is sent.

Acceptance: on the same native build/device, the original test verifies Continue
is unavailable/does not advance with zero photos and finishes Pass. No app rebuild
or publication occurs in this case. Verified hardware results are recorded below.

## Verified retest

Run `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. The affected device check passed. This closes the automation defect only.
