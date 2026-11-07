# DF-001 staging retest

- Owner/tester: Codex.
- Date: November 7, 2026.
- Original failure: Device Farm `914b08a8-54e9-40d9-8057-c17e64ee2bcc`, Android build 3.
- Candidate commit: `c69446ffe8c2acf733ceca9db6cbb0dc2730aa4c`.
- Candidate build: EAS `777562a3-e97d-4c64-a784-612d6179eafe`, Android version code 4, staging.
- Target: Pixel 9 Pro XL / Android 15, original device-pool configuration.
- Scenario: Existing-listing review/publication, explicit original-photos-only decision.
- Listing: `db3ede13-0844-42bb-a559-b041eccb53f6`, Free People Eyelet Scalloped Shorts, $28.
- Status: Android include/exclude workflows passed; final cross-account gallery acceptance pending.

Local checks: five mannequin/media tests passed; native App JSX parsed; Python
harness compiled; canonical analysis guide built and checked; diff whitespace check passed.

Remaining acceptance: original-only publication persists, include branch on a
separate draft, and public gallery visibility from a second account. No production
deployment is authorized or claimed by this retest. The defect remains open.

Original failure evidence remains in `output/devicefarm-android-shorts-nov07-artifacts/`.
Candidate metadata and new-run evidence use `output/df001-*` to retain original results.

## Device results

| Choice | Run | Result |
| --- | --- | --- |
| Original photos only | `2e44da67-5358-4c7e-8bcd-5ae3d0b2b828` | PASSED |
| Include mannequin | `d90e45d7-5ee0-4c97-90cc-dcbf37015c46` | PASSED |

Both runs used staging build 4 on Pixel 9 Pro XL / Android 15, detected the
explicit control, clicked it, refreshed Closet and verified persisted Active state.
[Retained decision/publication evidence](../evidence/DF-001/) excludes raw logs
and credentials. Five pricing-review regression tests also passed locally.

Scope adjustment: the same dedicated staging fixture was reset to Review between
branches rather than using two separately created listings. Reset changed only
its status; prior server verification confirmed Active with both image decisions
excluded. No original test result was edited. The include run leaves the listing
Active with the include decision; production was untouched.

Earlier new-build run `08c722f7-2e63-4637-924b-d38a0918e58b` failed only after
successful publication because of the separate harness refresh bug DF-002, now
fixed and closed with the two passing retests. Its evidence is preserved separately.

Second-account UI gallery verification has not been performed. DF-001 remains
open for that final acceptance check; the mobile workflow fix is staging-device
verified, not production deployed.

Read-only non-owner marketplace API verification passed: listing Active, both
synthetic assets saved as include, and both visible in the public listing media.
[Sanitized API evidence](../evidence/DF-001/non-owner-api-verification.json).
This is API-level verification, not a second-account UI check.
