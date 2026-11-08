# Mobile DF-001 production release

Updated November 8, 2026. Status: **Production Android APK build 9 available through Expo; no Google Play submission. iOS awaits Apple agreement acceptance.**

## Scope and source

User requested production deployment of the standard native mannequin
include/exclude publication fix. Implementation commit: `c69446f`.
Isolated release checkout: `e755b8b` (same mobile implementation plus QA records).
Uncommitted Entrupy work in the primary workspace is excluded and preserved.
No backend deployment, existing AI/payment credential rotation, staging configuration or production
store listing change was made. Three additive production mobile-auth settings were
stored in the AWS runtime secret and synced to EAS, as described below.

Staging validation: Android build 4 (`777562a3-e97d-4c64-a784-612d6179eafe`),
Pixel 9 Pro XL / Android 15, include and exclude publication passed:
`d90e45d7-5ee0-4c97-90cc-dcbf37015c46` and
`2e44da67-5358-4c7e-8bcd-5ae3d0b2b828`.
Cross-account UI gallery acceptance remains pending in DF-001. iOS device
verification of this fix has not been performed.

## Initial build attempt and blocker (resolved)

Both Android and iOS production EAS commands stopped during Expo configuration,
before compilation or a cloud build ID was created. EAS project
`@leavethemessage/valueai-mobile` reports no variables in its production environment.
The existing production configuration guard in
`apps/mobile/config/variants.cjs` requires
`JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY` beginning with `pk_live_`.
The production AWS runtime secret did not contain a Clerk publishable key.
No secret values were displayed or copied into this document.

The initial next input was production Clerk configuration. That blocker was
resolved below by preserving the existing deployed issuer with explicit pinning.
No Clerk secret key was bundled, and no implicit staging-key fallback was introduced.
The app targets `https://api.jouft.com` with identity `com.jouft.app`.

## Remaining release steps

1. Resolve required production publishable configuration and verify production authentication compatibility.
2. Build Android production AAB and iOS production IPA from the isolated committed source.
3. Record build IDs and validate the resulting app identity/environment and release-candidate behavior.
4. Submit through configured production store channels. iOS targets App Store Connect `6826942359`, not staging `6791465341`; Android needs working Play submission credentials/configuration.
5. Record actual upload/review/release outcomes separately. Upload does not mean public availability; there is no OTA channel configured in this source.

This report is a local release record, not a claim of store submission or deployment.

## Configuration investigation and recovery

The initial EAS production environment was empty. The production AWS runtime
secret contained payment/AI keys but no Clerk key; enabled-region inventory found
no separate Clerk secret in this AWS account. Existing production frontend and
API both use `https://firm-mink-35.clerk.accounts.dev`. Historical iOS production
build `d9c98018-8feb-4dd8-b12d-61bd30b39566` predates the newer variants guard and
used bundle `com.jouft.app.dev`; it did not establish signing for `com.jouft.app`.

To preserve deployed authentication, the exact production frontend publishable
key was verified against the backend issuer and stored as
`JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY` in `valueai/prod/runtime`, alongside
`JOUFT_PRODUCTION_CLERK_ALLOW_TEST_INSTANCE=true` and the pinned
`JOUFT_PRODUCTION_CLERK_ISSUER`. All pre-existing secret fields were verified
unchanged. These three fields were synced from AWS to EAS production using
sensitive visibility. No key values are included here.

Compatibility commit `97d383a` on `release/mobile-df001-production` (equivalent
main commit `22a4e07`) requires explicit opt-in and exact issuer matching; default
production still requires a live Clerk key. Four guard tests passed. This preserves
the current production auth instance, not an auth migration.

## Current build and store prerequisites

- Android: production AAB build `30d90157-9486-48c1-af93-8480173347b5`, version 1.0.0, version code 8, FINISHED November 8, 2026. Production profile, store distribution, source `97d383a`.
- Android submission preflight: Google Play service-account credentials are not configured in EAS. No store submission was queued. Secret name/region or EAS credential setup requested from owner.
- iOS: Apple login and two-factor verification succeeded. JOUFT LLC provider was selected. Registering/signing `com.jouft.app` returned Apple 403: updated Program License Agreement must be accepted by Account Holder Mona Shalchi. No iOS cloud build ID exists yet. Owner action requested; no agreement was accepted on anyone’s behalf.

The original key-only blocker above is resolved; remaining signing/store blockers
must not be described as successful deployment. Build completion and public store
availability will be recorded only after verified results.

## Credential-source verification details

AWS secret access is working in account `537595754494`. Secrets Manager inventory
in enabled regions found the production runtime secret in us-east-1 and dedicated
Device Farm login secret in us-west-2. No Google Play service-account JSON field
or separate secret was found. EAS explicitly reported “Google Service Account Keys
cannot be set up in --non-interactive mode.” Parameter Store metadata checks in
us-east-1/us-east-2/us-west-1/us-west-2 found no matching Play/mobile credential
parameters. This is a missing identified publishing credential, not an inability
to read the available AWS runtime keys. No private credential values are logged.

Apple’s exact blocker: “Unable to process request - PLA Update available - You
currently don't have access to this membership resource. To resolve this issue,
your team's Account Holder, Mona Shalchi, must agree to the latest Program License
Agreement.” Resume after the Account Holder completes this at
https://developer.apple.com/account/ .

## Android artifact verification

- [Production AAB download](https://expo.dev/artifacts/eas/hWBktIgI0gJdr4f1JqKC9yjG3pu50d9Ium4zvma6AAA.aab)
- Local artifact: `output/jouft-production-1.0.0-8.aab`.
- SHA-256: `b6c1011cf87c22a107d91500a9ee40c4c529b4b1906020231f6270e461e04d9a`.
- ZIP integrity passed. The base manifest contains the production package marker
  `com.jouft.app` and does not contain `com.jouft.app.dev`.
- EAS metadata confirms production/store distribution, version 1.0.0/code 8,
  source commit `97d383a41297d60ceb0839a7eab727c087756c95`.
- The artifact has not been submitted to Google Play; no public rollout is claimed.

Historical production builds did not supply the missing new-bundle Apple signing
or Play publishing credential. The remaining actions are the Account Holder’s
Apple agreement acceptance and configuration/location of Google Play’s service
account key. Existing production web/API services and unrelated worktree edits
remain unchanged.

## Android delivery scope changed — November 8, 2026

The owner explicitly requested Expo distribution and a downloadable production
APK, with **no Google Play submission**. The Play-credential discussion above is
historical; that credential is no longer a dependency for Android delivery.
`production.android.buildType=apk` is configured in EAS. Existing production
identity/API/authentication and keystore are retained; no auto-submit command is used.

APK build: `66e72ca6-f03f-4c02-a0e2-4adcf8d78f7a`, version 1.0.0/code 9,
source `ef57f90` on the isolated release branch. Main configuration commit:
`bbd4d12`. Build completed and package verification passed, as recorded below.

## Production APK available — November 8, 2026

[Download Android production APK — version 1.0.0, build 9](https://expo.dev/artifacts/eas/d-AFYR6-Lh7mMldkNW-3rHZ5pNVBP6wqmGS-W-JolwY.apk).

Build `66e72ca6-f03f-4c02-a0e2-4adcf8d78f7a` completed successfully.
Downloaded ZIP integrity passed; Android aapt2 confirms `com.jouft.app`, version
1.0.0/code 9. SHA-256:
`48b20306b21e9e7fba451ca326adc9f551d6ea8a3408684680ff3eae774e8f72`.
[Machine-readable verification](MOBILE_DF001_APK_VERIFICATION.json).
Local APK: `output/jouft-production-1.0.0-9.apk`.

This is a standalone production APK distributed through Expo for installation.
No Google Play submission occurred. Existing installations require installation
of the new APK; no OTA update or automatic store rollout is claimed.
