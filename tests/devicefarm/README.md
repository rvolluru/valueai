# Android and iOS create-listing UI test

Updated November 3, 2026: the local test now waits up to 15 minutes after creation
for an identified title, positive valuation, populated description and review
actions, then pages through the gallery to verify a mannequin image with the AI
disclosure and no image-unavailable error. It saves analysis and mannequin
screenshots plus `listing-analysis-checks.json`. This extension has not yet been
verified on a Device Farm device; the passing run below covers creation only.
The extended package is `output/create-listing-analysis-appium.zip`; its validated
upload is recorded in `output/devicefarm-analysis-test-upload.json`. Schedule it
with a 25-minute job timeout.

Use the dedicated account with a single test/device at a time: the test tracks
the newest closet card and assumes no concurrent listing creation for that user.
The listing stays unpublished and the preview stays pending review.

Updated November 2, 2026 (November 3 UTC). The dedicated Clerk identity
`leavethemessage+clerk_test@gmail.com` now exists and Device Farm sign-in works.
Its staging profile was seeded with synthetic onboarding data and the free plan;
no payment method was added. Staging and production share a Clerk issuer, but
only the staging database was seeded. The original account is unchanged.

Latest run `c0782ebf-d80b-42e3-b199-0b61487eab8f` **PASSED** on the pinned
Google Pixel 9 Pro XL / Android 15 configuration. The full UI test signed in,
selected the three local fixture images, passed required coverage, set category /
condition / size, created a listing, and verified an additional card in My Closet.
The earlier failures below explain the selector and device-pool constraints.

Run `de0bf313-d89a-4b03-8fe6-cbfcd492fc54` selected all three fixture photos,
passed photo coverage, entered Clothes / Like New / S, and saved a real staging
listing. A staging database read verified listing
`a2ab455d-7b6a-4c51-a709-dd8ffb0d147f`, subsequently titled “Elena Eyelet Shorts”
and in Review after analysis. That run reported FAILED because the transient
success notice became stale during a React Native re-render. The assertion now
checks My Closet and an increased listing-card count, and node lookup retries
stale elements. Heading/action label collisions prefer clickable controls.

A subsequent run (`e1c7d8cc-3f4a-4328-b165-b3769cc79dfa`) hit an empty
Documents picker on another device before submission. The dedicated pool
`jouft-create-listing-android15` pins the Google Pixel 9 Pro XL / Android 15 device
configuration that completed creation. General `jouft-android` pool selection is
unchanged. Other picker/device configurations remain unverified.

The test handles Clerk's reserved `424242` email code only for a `+clerk_test`
address and an explicitly selected staging target. Global authentication settings
are unchanged. To refresh the dedicated secret, export its password and run:

```bash
python3 scripts/set_device_farm_password.py --email leavethemessage+clerk_test@gmail.com
```

Do not use the fixed test code on the original account or enable test mode in a
live Clerk instance. See [Clerk test emails](https://clerk.com/docs/guides/development/testing/test-emails-and-phones).
No application behavior was changed; these changes affect only the test harness
and dedicated staging test data.

## Configured remote host

Configured and verified November 1, 2026: `jouft-mobile` uses execution role
`arn:aws:iam::537595754494:role/jouft-devicefarm-tests`. Its only resource permission
is `secretsmanager:GetSecretValue` on the dedicated `jouft/devicefarm/staging-login`
secret in Oregon. The role trusts the Device Farm service. The owner populated
the secret, and its current version was verified without reading its value.

From the terminal where the password is already exported, run:

```bash
python3 scripts/set_device_farm_password.py --email leavethemessage+clerk_test@gmail.com
```

The helper sends credentials through stdin to Secrets Manager; the password is
absent from CLI arguments and output. `run_remote.py` reads the secret into memory
using the execution role, then passes it to pytest through its environment.
The host spec uses Appium 3, Node 22 and Python 3.11 on Amazon Linux 2. Appium uses
warning-level logs to avoid normal HTTP request logging; pytest tracebacks are
disabled to reduce credential exposure. Test artifacts and device recordings
remain accessible to account users with Device Farm permissions.

The package includes `IMG_0740.jpg`–`IMG_0742.jpg` copied from Downloads, showing
the test clothing item and its size S label. The remote runner selects Clothes / S.
Uploaded package and custom spec identifiers are recorded locally in
`output/devicefarm-uploads.json`. The custom spec source is
`tests/devicefarm/android-test-spec.yml`. Package upload validation alone does
not verify the UI flow or execution-role access during a real test.

The test signs in, opens Create, seeds 1–6 JPG fixture photos into the Android
gallery, selects them through the system picker, waits for complete photo
coverage, enters category/condition/size, and submits Create Listing. It asserts
the My Closet screen and an increased saved listing-card count. It saves a success screenshot
or failure screenshot/UI hierarchy (excluding a detected password screen).

This creates a real saved listing, waits for backend analysis and a visible mannequin
preview, and fails if either is missing or times out. It does not publish, approve
the generated image, or automatically delete the listing.
Review and remove test listings from the dedicated staging closet after runs.
Run on a clean Android device with only the fixture photos in its gallery.
The picker thumbnail selector targets the Android system photo picker and still
requires physical-device validation. Missing coverage fails the test; it does not
click Continue Anyway. MFA is unsupported; the only automated email verification is Clerk’s reserved
test-address code.

## Inputs

Use the staging APK (`com.jouft.app.dev`) configured for `https://staging.jouft.com`.
Verify the APK's environment before running; the package name alone does not prove
backend isolation. Provide through the test host environment:

- `JOUFT_TEST_TARGET=staging` (explicit acknowledgement of the target).
- `JOUFT_TEST_EMAIL`: dedicated staging account; the owner selected
  `leavethemessage+clerk_test@gmail.com` for automation (the originally selected
  account remains unchanged).
- `JOUFT_TEST_PASSWORD`: supply securely at runtime, never in Git or the ZIP.
- `JOUFT_TEST_PHOTOS`: absolute host path to a directory containing 1–6 `.jpg`
  images of a single clothing item (front, back and relevant labels/details),
  with sufficient required coverage.
- Optional `JOUFT_TEST_CATEGORY` / `JOUFT_TEST_SIZE`: default `Clothes` / `M`.
- Optional `JOUFT_TEST_ANALYSIS_TIMEOUT`: analysis/mannequin wait in seconds;
  default `900`, allowed `60`–`1800`. Allow additional time for login and creation
  in the Device Farm job timeout (25 minutes for the default).
- Optional `APPIUM_SERVER_URL`: defaults to `http://127.0.0.1:4723/wd/hub`.
  Match it to the server base path in the AWS test spec.

Device Farm supplies `DEVICEFARM_APP_PATH`, `DEVICEFARM_DEVICE_UDID`, and
`DEVICEFARM_LOG_DIR`. Locally, install the testing APK first and start Appium with
the UiAutomator2 driver, `/wd/hub` base path, and a connected clean Android device.

```bash
python3 -m venv /tmp/jouft-appium
/tmp/jouft-appium/bin/pip install -r tests/devicefarm/requirements.txt
# Export the inputs above, then:
/tmp/jouft-appium/bin/python -m pytest tests/devicefarm/tests/test_create_listing.py -v
```

## Device Farm packaging

Use an Appium Python custom environment and AWS's current default Android test
spec as the starting point. Keep its Appium installation/server startup and device
capabilities. Install these requirements and run `python -m pytest tests -v`.
Supply credentials securely on the test host and point `JOUFT_TEST_PHOTOS` at your
fixture directory in the extracted package. The configured `run_remote.py` handles
these inputs for the uploaded package. Never put credentials in the package,
checked-in YAML, or test command line. Device Farm recording may capture entered
account details, so use only the dedicated staging account.

Example package construction (from the repository root):

```bash
mkdir -p output/devicefarm-package/tests output/devicefarm-package/fixtures
cp tests/devicefarm/requirements.txt output/devicefarm-package/
cp tests/devicefarm/run_remote.py output/devicefarm-package/
cp tests/devicefarm/tests/test_*.py output/devicefarm-package/tests/
# Copy the approved JPG item photos into output/devicefarm-package/fixtures/.
python3 -m pip download --only-binary=:all: \
  -r tests/devicefarm/requirements.txt -d output/devicefarm-package/wheelhouse
(cd output/devicefarm-package && zip -r ../create-listing-appium.zip requirements.txt run_remote.py tests fixtures wheelhouse)
```

Upload `output/create-listing-appium.zip` as an `APPIUM_PYTHON_TEST_PACKAGE`,
upload the configured custom spec as `APPIUM_PYTHON_TEST_SPEC`, and schedule an
`APPIUM_PYTHON` run against `jouft-android` and the staging APK. Use the pinned `jouft-create-listing-android15` pool and a 25-minute
job timeout. The uploaded package and spec are prepared; the remaining
credentials have been populated. See the execution status at the top of this file;
the latest pinned Android run passed end to end.

References: [AWS Appium integration](https://docs.aws.amazon.com/devicefarm/latest/developerguide/test-types-appium-integrate.html),
[custom test environments](https://docs.aws.amazon.com/devicefarm/latest/developerguide/custom-test-environment-test-spec.html).

## iOS Device Farm run

Updated November 4, 2026. The original navigation failure is fixed and verified on
real iPhone 16 / iOS 18.0 and iPhone 14 / iOS 17.6.1 devices. Full iOS end-to-end
coverage is **not passing**: both native photo pickers displayed “Unable to Load
Photos” before fixture selection. On iOS 17.6.1, two Try Again attempts also failed.
No iOS listing was created; analysis and mannequin assertions were not reached.

Latest complete-flow attempt: `933d5353-92ea-4a02-a0f5-d599946691c8` (FAILED).
A follow-up diagnostic run `f808ff1a-448c-428e-afdd-7435b8ae5adf` could not launch
the Photos app to inspect its library. The cause of the picker failure remains
unconfirmed. Evidence and a machine-readable summary are in
`output/devicefarm-ios-diagnostics-2026-11-04/`.

The same test supports `JOUFT_TEST_PLATFORM=iOS`, XCUITest and the staging bundle
`com.jouft.app.dev`. `ios-test-spec.yml` selects macOS Sequoia, Appium 3 and a
matching Device Farm pre-signed WebDriverAgent. The pools
`jouft-create-listing-ios18` and `jouft-create-listing-ios17` pin the devices above.
Use a single device/test at a time for the dedicated account, with a 25-minute
job timeout.

The harness handles restored iOS sessions by signing out before authenticating
the dedicated account. Grouped React Native controls are tapped using bounds
from the current accessibility snapshot; `ios-navigation.json` records tab
lookup counts, bounds and destination checks. Known system permissions are
accepted explicitly. The app's Photo library option is selected through the
native alert API, without automatic acceptance of arbitrary alerts.

Fixture setup opens short-lived signed image URLs in Safari, explicitly selects
Safari as the active automation app and uses Share → Save Image. The fixture
objects remain private in the staging uploads bucket. The ZIP includes
`ios-fixture-urls.json`; regenerate its signed URLs before they expire. Account
credentials remain in the dedicated Secrets Manager secret and are loaded by
`run_remote.py`. The picker reports a clear failure after two retries if its
native “Unable to Load Photos” screen appears.

The isolated staging Device Farm IPA is EAS build
`1039c501-aafe-4136-b32f-c348daf6ed6c` (build 65). The saved staging provisioning
profile lacks the push entitlement, so this isolated build removes it after
native project generation. The production and staging source configuration is
unchanged. Earlier builds `31e186c1-0f3d-48cf-9a2a-452ee3853526` and
`a67ab98a-ce44-4aa4-a497-9f6568e4bd8c` failed signing before that adjustment.

Validated uploads are recorded in `output/devicefarm-ios-uploads.json`;
`output/create-listing-ios-appium.zip` is the local package. Upload validation
and successful navigation do not establish completion of the listing flow.

## Android Review and Publish test

Implemented locally November 6, 2026; **not yet run or uploaded to Device Farm**.
`tests/test_review_publish.py` reuses the creation/analysis/mannequin flow with a
fresh draft, then opens the closet's accessible `Review and publish listing` CTA,
checks the title, clicks Publish, refreshes through server-backed navigation and
reopens the same newest item. The persisted `Marketplace Matches` view and absent
Publish action distinguish an Active listing from a review draft. This does not
verify marketplace visibility from a second account.

Use `android-review-publish-test-spec.yml` instead of the create-only spec; it sets
`JOUFT_TEST_SCENARIO=review_publish`. Include both test files in the ZIP. The runner
selects exactly one scenario; default `create` retains its unpublished behavior.
Locally select `tests/devicefarm/tests/test_review_publish.py` explicitly. Running
pytest on the entire tests directory runs both scenarios and publishes a listing.

Only Android with explicit staging target and testing package is supported. Verify
the APK points to staging before scheduling; package identity is not backend proof.
Use the pinned Android 15 pool, 25-minute timeout, fixture photos and existing
Secrets Manager credential setup. Run one test/device at a time for this account.
The test requires analysis, positive value, description and visible mannequin
before reviewing. Required manual-review/image decisions are not bypassed: if
Publish cannot complete, the test fails and retains UI evidence for diagnosis.
It does not add approval controls or change application publication policy.

Success saves `review-publish-success.png` and `review-publish-checks.json`, in
addition to creation/analysis/image evidence. The earlier
`listing-analysis-checks.json` describes the pre-publication checkpoint; the
review-publish file describes the final state. Failures use the existing
`create-listing-failure` artifacts and report the failing stage. The newly
published staging listing is left for inspection; remove it manually after review.

## Review and publish an existing Android listing

Implemented locally November 6, 2026; **not uploaded or device-verified**.
Select scenario `review_publish_existing` with
`android-review-publish-existing-test-spec.yml`. By default, the test scrolls up to 30 times to find the first actionable
`Review and publish listing` card, then records its title and locks subsequent
review/publication to that title. Analyzing cards labeled Pending Review are not
eligible. No eligible card means failure, not creation of another listing.
Optionally set `JOUFT_TEST_LISTING_TITLE` to an exact, unique draft title for a
targeted run; export that non-secret value in the custom spec before the runner. Never supply a password in the spec. Include all three
`test_*.py` files and the updated runner in the package.

The test signs in, searches My Closet, requires one enabled exact-title result,
opens it and checks completed analysis, positive valuation, description and
Edit/Publish actions. It inspects the gallery for a load error, reopens the same
item, publishes, refreshes from the server and verifies its Active-only
Marketplace Matches view. It does not create a listing, import fixture images,
request a rerun or approve pending mannequin images. It does not certify every
photo or public visibility from a second account. Backend-required review or
image decisions remain enforced and can cause a failure.

Use a unique title across the account's closet, avoid concurrent edits and run
one device at a time. An already Active, missing, ambiguous or analyzing explicitly selected target
fails instead of selecting another item. Successful publication mutates the
existing staging listing; repeat execution automatically selects another eligible draft when no title is specified.
No automatic deletion or unpublishing occurs. Artifacts:
`existing-listing-review.png`, `existing-listing-publish-success.png` and
`existing-listing-publish-checks.json`; existing failure artifacts include stage.
The original `create` scenario remains the runner default. Invoking pytest on
the whole directory includes publication scenarios; select a specific file.

### Android existing-listing run — November 6, 2026

Uploaded and executed on the pinned Google Pixel 9 Pro XL / Android 15 pool.
Run `9967c117-fcbe-4dca-94f7-63528c23dcfc` failed at the review assertion after
selecting **Free People Eyelet Scalloped Shorts**. The UI showed `$0` and
“We couldn't determine this item's value. It needs manual review before
publishing. You do not need to set a value.” No Publish click was reached.
This verifies sign-in, automatic review-card selection and opening the correct
existing item, but **does not verify successful publication**. Resolve pricing
review on a test draft before expecting a successful publish run.

Earlier attempts `f358591e-e0ff-467d-a2c7-cac0c423bcb9` and
`ddcd6b33-54a3-4d22-b718-6072914b15ee` failed before publication on Android
card-identification and tab-navigation selectors respectively. The harness now
pairs review overlays with image links by snapshot bounds and taps Android tab
bounds from the current snapshot. No application behavior was changed.

Latest metadata: `output/devicefarm-android-existing-run.json`; validated package
and spec: `output/devicefarm-android-existing-uploads.json`; selected-title JSON,
JUnit report and failure screenshot/hierarchy:
`output/devicefarm-android-existing-artifacts/`. The extended fresh-create and
successful-publication paths remain unverified.

### Android targeted rerun — November 7, 2026

Run `914b08a8-54e9-40d9-8057-c17e64ee2bcc` targeted
**Free People Eyelet Scalloped Shorts** after its fresh analysis returned $28 and
cleared pricing review. Review assertions passed and the test clicked Publish,
but the application displayed: “Choose whether to include the mannequin image
in Review and Publish”. The test timed out waiting for My Closet; publication
was blocked by the pending image decision. This is not a successful publish run.
Evidence: `output/devicefarm-android-shorts-nov07-artifacts/`, including review and
failure screenshots and JUnit report. The test currently does not make an image
inclusion decision, as documented above. Do not bypass the backend decision guard
to obtain a passing result.

### Explicit mannequin decision — November 7, 2026

Local update, not yet device-verified: both publication scenarios now require a
visible image-decision control before submitting publication. Set optional
`JOUFT_TEST_MANNEQUIN_CHOICE=include|exclude` (default `exclude`, original photos
only). The harness supports direct Publish with/without mannequin buttons, or
Include mannequin image / Use original photos only followed by confirmation.
It searches down the review screen before failing; it does not approve via API.
`mannequin-publication-decision.json` records requested choice, detected control,
whether the click was submitted, and missing-control errors. A screenshot records
the decision when available; final Active-state assertions still verify success.

The current standard native Listing Details screen in `apps/mobile/App.js` has
only plain Publish. The separate listing-agent component has radio choices, but
this test does not switch workflows. Therefore the standard screen needs an app
UI change/build before this case can pass with a pending mannequin decision.
This test-only update does not change the app or deploy a new APK. Earlier notes
saying the test does not make an image decision describe the previous version.

The missing standard Android image-decision controls are tracked as an **open
High-severity application bug**, not an expected unsupported feature:
[Android mannequin review controls missing](../../docs/qa/bugs/ANDROID_MANNEQUIN_REVIEW_CONTROLS.md).
The test's missing-choice step and the application's missing standard-flow controls
are separate defects. Updating the harness alone does not fix the application.

## Failure triage and bug lifecycle

Follow the [Device Farm defect workflow](../../docs/qa/DEVICE_FARM_DEFECT_WORKFLOW.md)
for every failed automated run or remote-access test. Preserve original evidence,
classify the cause, link a tracked issue, assign ownership, and close only with
identified-build retest evidence. Use the [defect register](../../docs/qa/DEFECT_REGISTER.md)
and defect/retest templates there; the GitHub Device Farm issue form captures the
same required fields. This procedure does not automatically file external issues
or authorize deployment.

## DF-001 fixed APK retests — November 7, 2026

Staging APK version code 4, EAS `777562a3-e97d-4c64-a784-612d6179eafe`,
commit `c69446f`, passed both existing-listing publication scenarios on the pinned
Pixel 9 Pro XL / Android 15 configuration:

- Exclude mannequin: `2e44da67-5358-4c7e-8bcd-5ae3d0b2b828` — PASSED.
- Include mannequin: `d90e45d7-5ee0-4c97-90cc-dcbf37015c46` — PASSED.

Both explicitly selected the matching publication action and verified Active
state after direct Closet Refresh. Earlier notes about missing standard controls
apply to the old APK, not this fixed build. The original failure is preserved.
A separate harness refresh defect DF-002 was fixed and verified by these runs.
See [DF-001 retest record](../../docs/qa/bugs/DF-001_RETEST.md) for fixture resets,
API verification and remaining cross-account UI acceptance. No production rollout.
