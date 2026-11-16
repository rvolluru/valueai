# DF-018 — Field helper relies on unsupported element-scoped ancestors

- Status: Closed
- Classification: Automation
- Severity: High
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Run: `d5797481-8c98-4e01-9a81-bc33d7262775`
- Device/build: Pixel 9 Pro XL / Android 15, staging Android 0.1.0 (4)

Registration stopped at its first Email input with NoSuchElementException: the helper asked a label element for its parent through element-scoped XPath. No sign-up submission or account creation occurred. Other workflow inputs shared this helper.

Candidate: resolve labels and their following EditText from the full hierarchy, retaining visible/enabled uniqueness checks, native hint aliases, bounded rendering waits and scrolling. No credential payload or auth screenshot is retained in public evidence. Acceptance: registration reaches all three correct inputs, mismatch validation, Clerk test-code verification and the new account's Security email; other profile inputs remain independently verified.

The first candidate exposed a UiAutomator2 XPath 2 engine ClassCastException on the following axis, before entering the first field. The server explicitly recommends `enforceXPath1=true`; the shared Android session now selects XPath 1 for these standard queries. That compatibility change also requires device verification. No account was created by either failed attempt.

## Verified scope

Run `848c71e9-8cf7-4bc3-9550-2ccd31c751c2` entered the registration fields, exercised mismatch validation, verified the Clerk code, and saved First Name/Last Name/Birthday/Email through the native UI. The new subject/profile were independently confirmed. Its later navigation/cleanup failure is separately tracked as DF-019; the registration case as a whole is not marked Pass. A fresh B login subsequently displayed the verified Security email in `b8242749-e6c6-443d-8eb6-4cd998bc9ae0` ([safe screenshot](../evidence/account-b-setup-2026-11-09/second-account-verified-identity.png)).
