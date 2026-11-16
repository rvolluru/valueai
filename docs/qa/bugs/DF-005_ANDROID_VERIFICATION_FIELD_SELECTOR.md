# DF-005 — Shared Android login counts the disabled email as an OTP field

- Status: Closed
- Classification: Automation
- Severity: High
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Scenario: `android_full`; regression navigation fixture setup
- Build: staging Android 0.1.0 (4), EAS `777562a3-e97d-4c64-a784-612d6179eafe`
- Device / OS: Google Pixel 9 Pro XL / Android 15
- Original run: `6aefd70d-2a5c-4fe7-a82d-ae7fc21ad8d2`
- Original disposition: stopped after repeated setup ERRORs, not a passing run
- Test identity: dedicated account A; no password/OTP retained in this report
- Mutation outcome: failed before the application test body; no publish/payment/label attempted

## Reproduction and evidence

Start a shared regression test, submit the primary credentials, and reach Clerk's
email-code challenge. The screen keeps a disabled email `EditText` above the
editable verification-code field. `AndroidUI.login` counted every `EditText`,
then asserted exactly one field. The native screen was left with an empty code.

[Sanitized video frame: disabled email plus empty code](../evidence/DF-005/verification-input-before-fix.png).
The frame shows no password or OTP. Original private video/logs remain under
`output/android-all-2026-11-09/baseline-artifacts/` and the original Device Farm run.
The four navigation setup cases all reported ERROR before the baseline was
stopped. This is an automation selector problem, not evidence that sign-in is
broken in the app.

## Candidate and acceptance

`AndroidUI.editable_fields` filters by enabled and displayed state. Login uses it
for both initial credentials and verification, matching the already established
create-listing flow's handling. A focused host regression supplies a disabled
email, active code input and hidden input, and verifies only the code is selected.
Safe exception type/source-site diagnostics were also added so subsequent failures
can be located without logging credential-bearing exception payloads.

Candidate package: `output/android-all-2026-11-09/package-r2/`.
Retest run: `20592dbb-482d-4570-953e-157b90ec3eb5` on the same device/build.

Acceptance requires native code entry, successful authenticated navigation and
all four original navigation checks passing. Relevant broad regressions must
also be reviewed. Hardware results are recorded below; no native rebuild or deployment
is required for this test-harness-only fix.

## Verified retest

Run `20592dbb-482d-4570-953e-157b90ec3eb5`, same staging Android build 4 and Pixel 9 Pro XL / Android 15. All four original navigation checks completed sign-in and passed. This closes the automation defect only.
