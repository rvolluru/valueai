# DF-010 — Missing disposable auth credentials raise KeyError

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

Registration and password recovery dereference their email environment variables before the missing-credential checks, producing Fail instead of the intended Blocked.

[Sanitized result and source sites](../evidence/DF-010/failure.json).
Private original video/JUnit remain in `output/android-all-2026-11-09/full-retest-artifacts/`.

## Candidate and acceptance

Validate approved environment references and availability before reading the disposable account. Never substitute the primary or secondary shared account.

Acceptance: Both missing-credential cases are explicitly Blocked on a device-host retest; neither becomes Pass and no auth mutation is attempted.

The candidate passed host checks; verified hardware results are recorded below. Original outcomes
remain preserved. This candidate changes the test harness only, not the app,
backend or production settings.

## Verified retest

Run `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. Both missing-credential cases now report Blocked rather than KeyError/Fail. Their actual business flows remain untested. This closes the automation defect only.
