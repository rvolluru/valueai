# Android Device Farm suite

Prepared November 7, 2026. This suite extends the existing create/analyze/mannequin
and publish tests. **New broad cases are implemented but not yet device-verified.**
Collection/ZIP validation is not evidence that the app passes. The already passing
DF-001 publication runs remain documented separately.

## Groups

| Scenario | Purpose | Prerequisites |
| --- | --- | --- |
| `android_smoke` | Navigation, empty search recovery, profile sections, activity screen, session restore, sign-out, empty creation, assistant open/close, inbox filters, invalid login | Dedicated staging login; latest staging APK; no fixture mutations beyond invalid login attempt |
| `android_regression` | All 31 native UI checks, including known-title/brand/category search, review/edit navigation, gallery, pricing block and second-account checks | Reviewed manifest with seeded listings; second account for isolation/gallery |
| `android_workflows` | 21 registered workflow slots executed through reviewed UI recipes | Per-workflow steps, assertions and cleanup; sandbox verification for transactions |
| `android_full` | Both groups plus fresh create → analysis → mannequin → decision → publish | All above plus 1–6 complete JPG views of one clothing item |

The workflow slots are **not completed business-flow implementations until reviewed
recipes are supplied and device-verified**. Missing recipes report Blocked. Camera,
network changes, OS permissions, payment-provider sheets and mailbox verification
may need new driver actions or manual execution; unsupported actions fail validation.
No billing, shipping, external social posting or bulk email actions are scheduled
by default. Tests do not establish model-image visual fidelity without human review.

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
Manager login. If supplied, `JOUFT_TEST_SECOND_SECRET` names a separate Oregon secret
containing B's `email` and `password`; the execution role needs narrowly scoped
GetSecretValue access to that secret. Do not reuse A as B or put either password in
a manifest/ZIP. Secrets/IAM for B have not been provisioned by this suite change.
Missing second credentials are Blocked. Verify B can see seeded public matches;
matching preferences and size rules still apply.

Recipe example (navigation-only illustration; replace with actual reviewed
business steps, final persistence assertions and restoration before enabling a slot):

```json
{
  "reviewed_by": "Reviewer name",
  "fixture_ids": ["Controlled staging entity ID"],
  "steps": [{"action": "tab", "label": "Profile", "expect": "SETTINGS"}],
  "verify": [{"action": "wait", "label": "SETTINGS"}],
  "cleanup": [{"action": "tab", "label": "Closet", "expect": "My Closet"}]
}
```

Put recipes under `workflows.<registered_name>`. Actions: tab, tap (optional
scroll), input (accessible field label and value or environment-variable name),
wait, absent, search, open_listing, back, relaunch, sign_out, and switch_account
(with account A or B). Recipe strings are not a
substitute for a proper OS/provider driver; those need extension
before corresponding end-to-end claims. Financial recipes additionally need
`sandbox_environment=staging-test-mode`, `sandbox_verified_by`, and host variable
`JOUFT_TEST_SANDBOX_CONFIRMED=1`. The reviewer must verify actual provider test mode;
a flag alone does not detect billing configuration. Never place a real card in recipes.
Recipe cleanup runs after authentication even on failure; make it safe and specific.

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
The second staging account and actual sandbox configuration remain unconfirmed.
