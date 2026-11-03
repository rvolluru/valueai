# Jouft Device Farm

Provisioned and verified November 1, 2026 in AWS account `537595754494`, region
`us-west-2`, using profile `rajesh_volluru`.

## Resources

- Mobile project: `jouft-mobile`
  (`arn:aws:devicefarm:us-west-2:537595754494:project:dfc7f940-6cb8-4ea1-b01f-e887db6da2f7`).
- Automated device pools: `jouft-android` and `jouft-ios`. Each dynamically selects
  at most one device of its platform per run. These pools do not reserve devices
  or guarantee a particular model or OS version.
- Default mobile job timeout: 15 minutes per device job (not a total spend cap).
- Desktop Selenium project: `jouft-desktop`
  (`arn:aws:devicefarm:us-west-2:537595754494:testgrid-project:5c84a245-190c-4ae3-8292-78b19a459e4b`).

These resources are managed separately from the application's Terraform state.
No device subscriptions, private devices, sessions, test runs, app uploads,
mobile builds, or CI test suites were created by this setup.

To create missing resources or print the existing resource identifiers:

```bash
python3 scripts/setup_device_farm.py --profile rajesh_volluru
```

The script reuses resources by name. It does not reconcile modifications to
existing resources or start testing.

## Manual mobile testing

1. Open the [Device Farm console](https://us-west-2.console.aws.amazon.com/devicefarm/home?region=us-west-2).
2. Under Mobile Device Testing, open `jouft-mobile`, select Remote access and
   create a session on an available Android or iOS device. Automated device pools
   are separate from remote device selection.
3. Use Install app to upload an Android APK or physical-device iOS IPA.
4. Test using staging (`https://staging.jouft.com`) and dedicated test accounts.
5. Stop the session when finished; review its recording and logs.

The existing mobile staging Android profile produces an APK. From `apps/mobile`,
`npm run eas:build:android:staging` starts a separate EAS cloud build when needed.
iOS requires a physical-device IPA; the development simulator build cannot run
on Device Farm. Use a developer-provided installable IPA, not an encrypted app
downloaded from the App Store. See [mobile build configuration](../apps/mobile/README.md).

Public Device Farm devices re-sign apps. iOS entitlements such as push, associated
domains and Apple Pay are removed, so those capabilities need separate validation.
Android integrations tied to the signing certificate may also behave differently.
See [AWS app behavior](https://docs.aws.amazon.com/devicefarm/latest/developerguide/apps.html).

## Automated testing and cost

Mobile Appium testing requires an app upload and a compatible test package before
scheduling a run against a pool. Desktop testing requires a Selenium suite and a
temporary TestGrid URL generated for `jouft-desktop`; AWS supports Chrome, Firefox
and Edge on Windows. An Android [create-listing Appium test](../tests/devicefarm/README.md)
has been uploaded with fixture photos and a custom Appium test-host specification.
The mobile project has an execution role that can read only its dedicated staging
login secret. The owner must populate that secret using
`python3 scripts/set_device_farm_password.py` from the terminal with the exported
password. The secret was populated and three listing-test runs executed November 1;
all failed at welcome/login navigation before listing creation. A fourth run on
November 2 (`0c35ed75-9125-4726-9600-63ed7c1be600`, Pixel 9 Pro XL) verified the
accessibility-selector fix and submitted credentials, but Clerk required an emailed
additional sign-in code. Remote host setup and credential retrieval worked.
Unattended staging authentication is blocked by email verification; listing creation
remains unverified. A fifth run (`573abd3b-bd6e-4757-ac1a-83c0e4b5c643`)
used the new test-alias credentials but failed during authentication. The Clerk
dashboard showed no matching alias user; creation of that automation account is
still pending. No listing was created. Desktop test suites are
not configured yet.

Mobile pay-as-you-go testing and remote access are currently $0.17 per device
minute after any remaining one-time trial allowance. No remaining free allowance
was assumed or verified. Desktop usage has separate pricing. Check
[AWS pricing](https://aws.amazon.com/device-farm/pricing/) before starting runs.
