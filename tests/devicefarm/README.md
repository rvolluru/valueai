# Android create-listing UI test

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

This creates a real saved listing and triggers backend AI analysis. It does not
publish, wait for pricing/mannequin completion, or automatically delete the listing.
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
- Optional `APPIUM_SERVER_URL`: defaults to `http://127.0.0.1:4723/wd/hub`.
  Match it to the server base path in the AWS test spec.

Device Farm supplies `DEVICEFARM_APP_PATH`, `DEVICEFARM_DEVICE_UDID`, and
`DEVICEFARM_LOG_DIR`. Locally, install the testing APK first and start Appium with
the UiAutomator2 driver, `/wd/hub` base path, and a connected clean Android device.

```bash
python3 -m venv /tmp/jouft-appium
/tmp/jouft-appium/bin/pip install -r tests/devicefarm/requirements.txt
# Export the inputs above, then:
/tmp/jouft-appium/bin/python -m pytest tests/devicefarm/tests -v
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
cp tests/devicefarm/tests/test_create_listing.py output/devicefarm-package/tests/
# Copy the approved JPG item photos into output/devicefarm-package/fixtures/.
python3 -m pip download --only-binary=:all: \
  -r tests/devicefarm/requirements.txt -d output/devicefarm-package/wheelhouse
(cd output/devicefarm-package && zip -r ../create-listing-appium.zip requirements.txt run_remote.py tests fixtures wheelhouse)
```

Upload `output/create-listing-appium.zip` as an `APPIUM_PYTHON_TEST_PACKAGE`,
upload the configured custom spec as `APPIUM_PYTHON_TEST_SPEC`, and schedule an
`APPIUM_PYTHON` run against `jouft-android` and the staging APK. Use the pinned `jouft-create-listing-android15` pool and a 10-minute
job timeout. The uploaded package and spec are prepared; the remaining
credentials have been populated. See the execution status at the top of this file;
the latest pinned Android run passed end to end.

References: [AWS Appium integration](https://docs.aws.amazon.com/devicefarm/latest/developerguide/test-types-appium-integrate.html),
[custom test environments](https://docs.aws.amazon.com/devicefarm/latest/developerguide/custom-test-environment-test-spec.html).
