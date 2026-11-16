# Android business workflow tests

Implemented November 9, 2026; **awaiting Device Farm execution**. All 21 former
recipe slots now have native business-flow implementations in
`tests/test_android_workflows.py`. The manifest supplies entity IDs, titles,
expected values and environment-variable references, not executable steps.
A collected test or passing host check is not a device acceptance result.

## Cases and restoration

| Workflow | Native actions and independent acceptance checks | Data / cleanup |
| --- | --- | --- |
| registration · QA-008 | Reject mismatched passwords; when invite-only, reject designated uninvited address; register allowed address, verify code, check signed-in security email | New separate disposable Clerk test email; sign out; retain created test account intentionally |
| password_recovery · QA-005 | Request reset, set a different password, sign out and sign in using it | Separate disposable test email; reset original password and verify original login even after failure |
| profile_save_restore · QA-050 | Change first name and toggle style, save, sign in again, check UI name and persisted name/style | Snapshot and restore complete profile; choose a name different from baseline |
| style_matching · QA-040 | Add an initially unselected size; assert eligible target appears, ineligible and own items do not; open target and check Request Trade; restore and verify target removed | Known source/eligible/ineligible size/category/value pair; restore profile |
| edit_save_restore · QA-036 | Edit title, description, condition and size through wizard; save, reopen, assert persisted fields and unchanged listing ID | Existing controlled listing; restore original fields through the same UI |
| delete_disposable · QA-038 | Cancel deletion and prove item remains; confirm deletion; check owner API, B marketplace/API and an unrelated sentinel | Exact disposable listing ID/title, distinct sentinel, account B; deletion intentionally retained |
| like_restore · QA-041 | Toggle heart, relaunch, verify changed heart and saved client state | Matched public target; restore liked IDs; social sharing remains separate manual coverage |
| trade_send · QA-042 | A requests B item; B chooses exact A exchange item and confirms proposal; A sees correct proposal; assert one new request and participant/item IDs | Distinct active eligible pair, complete profiles, B; decline only newly created request during cleanup |
| trade_decline · QA-043 | A declines proposed exchange; assert both accounts declined, B closed detail, no label creation control | Unique proposed disposable offer, A requester/B target owner; declined state retained |
| trade_accept · QA-044 | A selects receive address, checks exact items and shipping amount in consent, accepts; verify both accepted and B detail | Unique proposed offer and expected charge; accepted sandbox trade retained, never force-reset |
| trade_stale_action · QA-045 | Open proposed offer in A UI; B independent API session declines; A retries stale action/double click; rejected acceptance cannot change declined state or create labels; refresh closed detail | Separate proposed offer, B observer; declined state retained; not a provider-ledger reconciliation test |
| shipping_address_save_restore · QA-046 | Save incomplete address and prove it is not persisted/selectable; add complete address, relaunch, set default, check persisted default/postal code | Synthetic address; restore original profile/addresses; current app silently filters incomplete entries rather than displaying field validation |
| shipping_quote_label · QA-047 | Check accepted offer, request exact expected quote/currency, create label, verify trade IDs/HTTPS carrier host, open document, relaunch and verify shipment IDs stable | Accepted sandbox trade; test labels retained; no real shipments or automatic label refund |
| payment_add_default_remove · QA-048 | Open native Stripe PaymentSheet, use fixed provider test card, save, set default, reload, remove and verify removal | Sandbox only; delete only new payment methods and restore original default |
| subscription_change_cancel · QA-049 | Select specified paid plan/monthly price, inspect authorization, activate, reload, cancel through confirmation and verify canceling/canceled status | Disposable free-plan account with seeded test payment method; cancel on failure; retain period-end cancellation record |
| push_delivery · QA-053 | Enable push, background A; B likes exact A listing; prove one new activity, find OS notification, tap and verify Marketplace destination | A like alerts enabled; valid push build/services, B observer; remove only test notification history, relaunch, restore OS permission |
| photo_permission_recovery · QA-017 | Revoke photo access, deny prompt, assert useful app error; grant access, reopen picker and select fixture photos | Android-version-appropriate requested permission; restore original permission and remove only injected fixture files; discard unsaved draft |
| camera_capture · QA-016 | Capture and cancel, assert no attachment; capture again, use photo, verify attachment | APK with managed camera controls; restore camera permission; discard unsaved form; framing/quality remains human QA |
| offline_recovery · QA-059 | Load known listing, disable Wi-Fi/data, refresh and assert network error, restore and refresh; compare persisted listing ID/details/status | Existing own listing; restore each radio to original state in finally, including failure paths |
| background_analysis · QA-060 | Shared real photo/create UI; immediately background while same job pending/running, poll server, resume, check same job succeeds, complete normal analysis/mannequin assertions and exactly one new listing | Complete one-item photos; exclusive account; remove new private test draft after completion/failure |
| assistant_listing · QA-058 | New chat, supported question/response, cancel attempted listing before saving, retry with photos/facts, assert no creation until explicit confirmation, analyze private draft and open resulting Review listing | Conversation/listing agent enabled; complete item photos; expected response fragments distinct from sent messages; delete created private draft; retain disposable chat history |

## Configure data and credentials

Copy `android-fixtures.example.json` outside tracked files. Populate only the cases
you intend to run. Fields left null are prerequisites, not hidden defaults:

- `environment=staging`, `api_origin=https://staging.jouft.com`, `reviewed_by`,
  `verified_build` (exact EAS build ID), and `apk_sha256` of that APK.
- `exclusive_accounts=true`: reserve A/B for the run; no concurrent user edits,
  creation or other Device Farm jobs. Use unique titles and a separate offer for
  each terminal trade case. Accepted/declined/deleted fixtures are single-use.
- `accounts.A.subject` / `accounts.B.subject`: actual Clerk IDs for the two
  dedicated accounts. Observer identity must match both the manifest subject and
  the account email used for native login before any device mutation.
- Non-null per-case fixture values. Sample address and plan values are examples;
  verify eligibility, actual displayed prices/charges and carrier host before use.
  For style matching, seed a category-enabled source/target pair with the newly
  selected size as the only reason the eligible target becomes visible.
- `sandbox.verified_by`, `sandbox.verified_build`, `stripe_mode=test`,
  `shippo_mode=test`, plus host `JOUFT_TEST_SANDBOX_CONFIRMED=1` for financial cases.
  Verify the actual running backend/provider configuration. Missing keys do not
  establish sandbox mode. Each financial case additionally checks a returned
  Stripe setup publishable key is `pk_test_` before native financial actions.
  Shippo mode still requires the deployment operator's runtime verification.

The `.dev` app identity **does not prove staging**: the current testing TestFlight
app can use production. Every workflow checks the actual host APK SHA-256 and
embedded `assets/app.config` environment, package and backend origin. Production
APKs are rejected before an Appium session is opened. The observer also refuses
other API origins and HTTP redirects.

The existing primary Oregon secret supplies A email/password; optional
Broad native runs and workflows requiring B default to
`jouft/devicefarm/staging-login-b`; `JOUFT_TEST_SECOND_SECRET` overrides it;
`JOUFT_TEST_SECOND_SECRET_REGION` defaults to `us-east-1`. Use a separate
`+clerk_test` staging identity for B to use the built-in `424242` verification
helper without an inbox bridge. A login secret may also
contain `api_token` or `clerk_session_id`, loaded only into subprocess memory.

For long workflows, use independent renewable **Clerk test-instance** observer
sessions: `JOUFT_TEST_CLERK_SESSION_A`, `JOUFT_TEST_CLERK_SESSION_B`, and
`JOUFT_TEST_CLERK_SECRET` (`sk_test_` only). Sessions must belong to the explicitly
pinned fixture subjects; the helper validates ownership/status, caches short-lived
JWTs, and renews through Clerk's [session-token endpoint](https://clerk.com/docs/reference/backend-api).
The observer sessions must be separate from UI sessions because UI tests sign out.
Do not put the secret/session IDs into the fixture manifest, ZIP, YAML, or chat.
This code neither creates privileged credentials nor expands the execution role.

Alternatively, host environment variables `JOUFT_TEST_API_TOKEN_A/B` accept
already issued, unexpired session JWTs for short checks. These need a signed email claim, or the test-instance secret for an independent verified-email lookup; editable profile email is not accepted as identity proof. A static token cannot
support a long analysis run after it expires; missing/expired credentials block.

Optional `JOUFT_TEST_WORKFLOW_SECRET` names an Oregon Secrets Manager JSON object
with allowlisted environment-variable keys for renewable observer auth and
`JOUFT_TEST_REGISTRATION_EMAIL/PASSWORD`,
`JOUFT_TEST_RECOVERY_EMAIL/PASSWORD/NEW_PASSWORD`. Keep credentials out of checked-in
files; the existing Device Farm role needs explicit access to that named secret.
Environment names in fixture `*_env` fields must match this documented allowlist.
Registration/recovery must use separate disposable `+clerk_test` addresses and the
staging test-instance code `424242`; these do not test real mailbox delivery.
For invite-only registration additionally set `denied_email_env` and
`denied_message` to test rejection before verification. A real mailbox integration
and real invite-delivery tests remain separate QA work.

## Package and execute

Use a fresh Android gallery and complete JPG views of **one** item for photo
recovery, assistant creation and background analysis. The picker fails rather
than selecting unrelated gallery content. Tests remove only their injected files.

```bash
# One native camera case, no photo fixture directory needed:
python3 scripts/package_devicefarm_android.py --scenario android_workflows \
  --workflow camera_capture --manifest /absolute/path/android-fixtures.json

# All 21 workflows:
python3 scripts/package_devicefarm_android.py --scenario android_workflows \
  --manifest /absolute/path/android-fixtures.json \
  --fixture-dir /absolute/path/one-item-photos
```

Add `--upload` to validate/upload the package/spec to AWS. This helper never
schedules a device run. Single-case selection is embedded as
`JOUFT_TEST_WORKFLOW_CASES`; omit it for all 21. The full scenario includes these
21 plus the 31 regression checks and a separate fresh publication test.

Set `DEVICEFARM_APP_PATH` to the exact verified staging APK (Device Farm supplies
it), and use the packaged spec plus existing remote runner. Results include QA
case IDs, screenshots only on non-sensitive authenticated screens, and a
per-workflow cleanup JSON record. Missing prerequisites are Blocked; a cleanup
failure is Fail, even if the primary assertions passed. The complete-suite gate
returns nonzero for Blocked/Not Run cases. Follow the defect workflow for actual
failures and attach a sanitized new-build retest before closing a defect.

## Validation status

Host guardrails, syntax, collection and packaging are checked separately from
hardware execution. No new all-21 Device Farm pass is claimed here. Account B
credentials, reviewed fixture IDs, sandbox provider verification, the expected
conversation-agent build and observer-session configuration must be established
before a complete hardware run. DF-003 remains open until actual sandbox setup
is verified. Human visual/accessibility checks, real email delivery, social
posting and provider ledger reconciliation remain outside these 21 workflows.


### Real-email account B verification

If B's native login requests email verification, set
`JOUFT_TEST_SECOND_OTP_SECRET` to a narrowly accessible Oregon secret, through host
environment or the workflow credential secret. An existing inbox bridge or QA
operator must update its JSON to `email`, `code` (six-digit string), `issued_at`
(Unix epoch seconds) for the newly requested code. The helper waits up to 120
seconds, validates the exact account and freshness, and never emits the code.
`JOUFT_TEST_OTP_SECRET` provides the same facility for a real-email primary account.
Missing/stale delivery is Blocked, not an application failure or a test-code
bypass. This change does not provision a Yahoo/Gmail mailbox integration or IAM
access to that secret. The real selected B address cannot use `424242`.


November 9 host validation: **34 host checks passed**, all **52** broad cases
collected (31 regression + 21 workflows), and a deliberately missing-manifest
run produced **21 Blocked / 0 Pass**, exit 2, with QA IDs and no Appium session.
[Sanitized validation record](../../docs/qa/evidence/android-workflows-host-validation.json).


## First broad device execution — November 9, 2026

The full 53-case run is now being executed on the pinned Pixel 9 Pro XL. See the
[current execution report](../../docs/qa/ANDROID_DEVICE_FARM_RUN_2026-11-09.md)
for the original setup failure, fixes, retest and unresolved prerequisites. The
report supersedes earlier "not yet scheduled" status statements; implementation
and host-check records remain historical evidence, not hardware pass claims.

### Provisioning a new dedicated account

An isolated `android_workflows --workflow registration` run may set
`JOUFT_TEST_REGISTRATION_SECRET` to an email/password login secret;
`JOUFT_TEST_REGISTRATION_SECRET_REGION` defaults to `us-east-1`. Do not configure
`JOUFT_TEST_SECOND_SECRET` in that bootstrap run: normal registration guards
reject mutation of existing shared accounts. The secret is mapped in memory to
the approved registration environment references. Optional `initial_profile`
contains only synthetic `first_name`, `last_name`, and `birthday` fields; it saves
the Account section through the UI so subsequent reviewed fixture seeding can
identify the new subject. Existing accounts are not reset or renamed.
