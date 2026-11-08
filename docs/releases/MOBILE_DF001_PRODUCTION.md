# Mobile DF-001 production release

Updated November 8, 2026. Status: **Blocked before build; not deployed**.

## Scope and source

User requested production deployment of the standard native mannequin
include/exclude publication fix. Implementation commit: `c69446f`.
Isolated release checkout: `e755b8b` (same mobile implementation plus QA records).
Uncommitted Entrupy work in the primary workspace is excluded and preserved.
No backend, AWS credential/model configuration, staging environment or production
store listing was changed by this release attempt.

Staging validation: Android build 4 (`777562a3-e97d-4c64-a784-612d6179eafe`),
Pixel 9 Pro XL / Android 15, include and exclude publication passed:
`d90e45d7-5ee0-4c97-90cc-dcbf37015c46` and
`2e44da67-5358-4c7e-8bcd-5ae3d0b2b828`.
Cross-account UI gallery acceptance remains pending in DF-001. iOS device
verification of this fix has not been performed.

## Build attempt and blocker

Both Android and iOS production EAS commands stopped during Expo configuration,
before compilation or a cloud build ID was created. EAS project
`@leavethemessage/valueai-mobile` reports no variables in its production environment.
The existing production configuration guard in
`apps/mobile/config/variants.cjs` requires
`JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY` beginning with `pk_live_`.
The production AWS runtime secret did not contain a Clerk publishable key.
No secret values were displayed or copied into this document.

Required next input: configure the correct public production Clerk key in the EAS
production environment. Do not use a Clerk secret key or the staging/test key.
The app targets `https://api.jouft.com` with identity `com.jouft.app`.

## Remaining release steps

1. Resolve required production publishable configuration and verify production authentication compatibility.
2. Build Android production AAB and iOS production IPA from the isolated committed source.
3. Record build IDs and validate the resulting app identity/environment and release-candidate behavior.
4. Submit through configured production store channels. iOS targets App Store Connect `6826942359`, not staging `6791465341`; Android needs working Play submission credentials/configuration.
5. Record actual upload/review/release outcomes separately. Upload does not mean public availability; there is no OTA channel configured in this source.

This report is a local release record, not a claim of store submission or deployment.
