# Android Device Farm suite

Updated November 9, 2026. This suite extends the existing create/analyze/mannequin
and publish tests. **New broad cases are implemented but not yet device-verified.**
Collection/ZIP validation is not evidence that the app passes. The already passing
DF-001 publication runs remain documented separately.

## Groups

| Scenario | Purpose | Prerequisites |
| --- | --- | --- |
| `android_smoke` | Navigation, empty search recovery, profile sections, activity screen, session restore, sign-out, empty creation, assistant open/close, inbox filters, invalid login | Dedicated staging login; latest staging APK; no fixture mutations beyond invalid login attempt |
| `android_regression` | All 31 native UI checks, including known-title/brand/category search, review/edit navigation, gallery, pricing block and second-account checks | Reviewed manifest with seeded listings; second account for isolation/gallery |
| `android_workflows` | 21 implemented native business workflows | Reviewed fixture data, observer sessions, disposable accounts and sandbox verification |
| `android_full` | Both groups plus fresh create → analysis → mannequin → decision → publish | All above plus 1–6 complete JPG views of one clothing item |

All 21 formerly recipe-driven slots now have concrete test implementations,
including persistence assertions and restoration/retained-fixture rules. See
[workflow cases and setup](ANDROID_WORKFLOWS.md). They are **not yet verified on
Device Farm**. Missing prerequisites report Blocked; collection does not mean pass.
Financial cases require actual provider test-mode verification. Human visual,
accessibility, real email-delivery and social-sharing checks remain separate.

## Coverage and ownership

[Android coverage matrix](../../docs/qa/ANDROID_AUTOMATION_COVERAGE.md) maps all 64
manual cases, distinguishes partial automation and manual/other-platform checks,
and identifies gaps. Continue manual QA where automation is partial or unavailable.
This is a coverage inventory, not a claim of entire-app certification.

## Fixture manifest

Copy `android-fixtures.example.json` outside tracked files to `android-fixtures.json`.
Set `environment=staging`, exact `verified_build` and `reviewed_by`. Optional listing
entries use these schemas (supply actual unique titles owned by controlled users):

```json
{
  "closet_listing": {"title": "Known own listing", "brand": "Known brand", "category": "Clothes"},
  "marketplace_listing": {"title": "Known eligible OTHER-account listing", "minimum_images": 2},
  "review_listing": {"title": "Known ready unpublished draft"},
  "pricing_review_listing": {"title": "Known zero-value manual-review draft"},
  "private_listing": {"title": "Known own unpublished private draft"},
  "published_include": {"title": "Known own active included-preview listing", "image_count": 4},
  "published_exclude": {"title": "Known own active originals-only listing", "image_count": 3}
}
```

Titles must be unique across visible search pages; run one device per dedicated
account at a time. Use distinct drafts for mutation scenarios where possible.
Record fixture IDs and preserve state before retries. A is the existing Secrets
Manager login. Broad Android runs now default account B to
`jouft/devicefarm/staging-login-b`; `JOUFT_TEST_SECOND_SECRET` can override that secret
containing B's `email` and `password`. `JOUFT_TEST_SECOND_SECRET_REGION` defaults
to `us-east-1` (set `us-west-2` for an existing Oregon secret); the execution role needs narrowly scoped
GetSecretValue access to that secret. Do not reuse A as B or put either password in
a manifest/ZIP. Account B and its exact-secret IAM read permission were provisioned November 9,
2026. See the [setup/verification record](../../docs/qa/DEVICE_FARM_ACCOUNT_B_SETUP_2026-11-09.md).
Missing second credentials are not a passing cross-account check. Verify B can see seeded public matches;
matching preferences and size rules still apply.

Workflow fixtures now contain data, not action recipes. The example manifest
contains all 21 case schemas. Populate the selected cases and use the exact APK
SHA-256, staging origin and build ID. The tests reject an embedded production
configuration even if its package is `com.jouft.app.dev`. Configure renewable
observer sessions or short-lived observer JWTs as described in
[ANDROID_WORKFLOWS.md](ANDROID_WORKFLOWS.md). Credentials stay in host memory and
must never appear in the manifest/ZIP. All 21 business actions are implemented;
external account/provider setup is still required for a complete hardware run.

## Package and upload

From repository root, using an environment containing requirements.txt dependencies:

```bash
python3 scripts/package_devicefarm_android.py --scenario android_smoke --upload
# A configured full package requires an approved manifest and real complete photos:
python3 scripts/package_devicefarm_android.py --scenario android_full \
  --manifest /absolute/path/android-fixtures.json \
  --fixture-dir /absolute/path/approved-item-photos --upload
```

The helper packages all Python test/helpers (including conftest), optional fixtures,
and a custom spec, then optionally validates AWS uploads. It never schedules a run.
Metadata is in `output/android-suite/metadata.json`; use separate --output folders
to retain each package. Upload validation does not verify the installed APK points
to staging: verify its configuration independently. Use the pinned Android 15 pool
first, then expand to another Android OS/device after resolving selector failures.

Suggested initial timeout: smoke 45 minutes, regression 90 minutes, full 150 minutes.
Each native case signs in independently for isolation, so broad runs can consume
substantial device minutes. Establish measured timings before routine scheduling.
Select one scenario per run; the creation and publication tests mutate staging.
Do not execute broad scenarios against production. The old `create` runner default
is retained; the broad custom spec defaults to `android_smoke`.

## Results and release use

`android-case-results.json` records each selected case as Pass, Fail, Blocked or
Not Run. Missing prerequisites never count as Pass; broad scenarios return nonzero
if any case is Blocked/Not Run. JUnit still marks prerequisites as skipped, so use
the JSON and process exit status when assessing completeness. Per-case screenshots
are captured only on authenticated screens without password fields. Workflow
screenshots are captured before cleanup. Raw Appium logs are removed by the broad
spec's post_test phase; sanitize device logs/video before sharing.

Run the defect workflow for every actual failure. Do not close DF-001 just because
the cross-account cases collect: both second-account gallery branches must execute.
All manual visual, accessibility, push and server-scheduled-email acceptance still
requires explicit evidence. No automatic nightly schedule or production deployment
is installed by this change.

## Setup validation record

November 7, 2026: 52 broad cases collected locally; six host-side guardrail and
packaging tests passed. A missing-recipe run produced 21 Blocked results, exit 2,
and no Appium device sessions. AWS validated the smoke ZIP and custom spec;
local metadata: `output/android-suite-smoke/metadata.json`. Upload validation
covers format only; no new broad Device Farm run has been scheduled.
The second staging account and actual sandbox configuration were unconfirmed at that check.

## Staging provider check — November 7, 2026

A runtime settings check on `valueai-staging-api:22` found Stripe secret and
publishable keys and the Shippo API token **missing**, not test-mode credentials.
No explicit transaction key injection was present in that task definition.
Flat-rate quote configuration does not establish sandbox label/payment support.
See [DF-003](../../docs/qa/bugs/DF-003_STAGING_TRANSACTION_CONFIGURATION.md) and its
sanitized evidence. Transaction workflows remain Blocked; do not set
`JOUFT_TEST_SANDBOX_CONFIRMED=1` until actual test-mode configuration is verified.

The user selected `rajesh_mid@yahoo.co.in` for account B. Credentials have not been
provisioned by this check. Keep the password in a separate Secrets Manager secret;
if this real email needs verification, fixed Clerk test OTP automation does not
apply. Cross-account tests remain prerequisite-dependent.


## Workflow implementation validation — November 9, 2026

All 21 recipes were replaced with concrete cases. Host checks cover APK backend
pinning, account/token guards, sandbox refusal, packaging, radio/permission
restoration, cleanup failure handling, native payment refusal on a live key,
and an independent-session stale trade race. See the workflow guide for current
execution prerequisites. No new hardware run or broad acceptance pass is claimed.


## First broad device execution — November 9, 2026

The full 53-case run is now being executed on the pinned Pixel 9 Pro XL. See the
[current execution report](../../docs/qa/ANDROID_DEVICE_FARM_RUN_2026-11-09.md)
for the original setup failure, fixes, retest and unresolved prerequisites. The
report supersedes earlier "not yet scheduled" status statements; implementation
and host-check records remain historical evidence, not hardware pass claims.

For automated email verification, provision B as a distinct staging Clerk test
identity, for example `rajesh_mid+clerk_test@yahoo.co.in`. With Clerk Test mode
enabled, the existing helper uses `424242` without an inbox bridge. The untagged
`rajesh_mid@yahoo.co.in` remains a different identity and cannot use that fixed
code. Pin fixture ownership to the test identity; do not rename existing users
or enable Test mode on the production instance. Device Farm runs in Oregon but
can read an authorized Secrets Manager secret in another region.
