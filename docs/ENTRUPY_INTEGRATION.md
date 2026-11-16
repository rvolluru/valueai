# Entrupy integration

Updated November 15, 2026. **Integration paused; production service deployment verified.**
The seller controls and SDK sign-out hook have been disconnected, the API router
is not registered (regardless of `ENTRUPY_ENABLED`), and Expo autolinking excludes
`jouft-entrupy` on both platforms. Entrupy-specific iOS permission and native build
settings have also been removed. No provider requests or SDK capture can be started
through the application in this source configuration. Production web/API and worker deployment `55ced44` was verified in workflow
`43805821295`. New Android APK build 10 and iOS build 68 exclude the integration;
iOS build 68 is verified available in internal TestFlight. Existing installed
apps require an update. See [release verification](releases/PRODUCTION_2026-11-15.md).

Source is retained for future work. The sections below describe the dormant
candidate, not currently available features. Re-enabling requires restoring the
UI/hooks, router registration, native autolinking and build configuration, then
performing vendor SDK builds and real-device QA. Setting `ENTRUPY_ENABLED=true`
alone does not re-enable it. Native bridge source has not been compiled against
the vendor binaries or exercised on a device.

## Partner onboarding

Obtain an Entrupy partner API token with SDK support. Register the iOS bundle IDs
and Android application IDs `com.jouft.app` and `com.jouft.app.dev` with Entrupy.
Confirm the brands, categories, capture workflows and any hardware requirements
available under the account. Jouft passes listing brand/category as metadata;
Entrupy presents its selection menu when these do not match a configured flow.

Set on the API server only:

```
ENTRUPY_ENABLED=true
ENTRUPY_API_TOKEN=<secret from partner onboarding>
ENTRUPY_ITEM_NAMESPACE=jouft-production
ENTRUPY_TIMEOUT_S=20
```

Use a different stable namespace for staging. Changing the namespace changes the
lookup identifier, so existing captures cannot be found under the new namespace.
Never put the partner token in Expo public variables or web build variables.

## Native builds

The Expo local module under `apps/mobile/modules/entrupy` wraps iOS EntrupySDK
2.3.6 and Android `com.entrupy:sdk:2.5.0`. Expo Go cannot load this module.
Autolinking discovers it through `expo.autolinking.nativeModulesDir`.

Regenerate native projects using the repository's native/EAS build scripts so
config plugins set iOS 15.8 and static frameworks. Existing checked-in iOS native
files have not been regenerated. CocoaPods resolves EntrupySDK; Android resolves
GitHub Packages. Supply `GITHUB_USER` and `GITHUB_TOKEN` (read:packages access to
Entrupy) as private build credentials, or `gpr.user`/`gpr.token` Gradle properties.
Do not commit these values. iOS forwards background URL session callbacks to
Entrupy through an Expo AppDelegate subscriber. Camera permissions are provided
by the existing camera plugin; photo additions permission supports certificates.

Build both platforms and test on real devices before enabling rollout. The
Android dependency cannot be verified without package access. Native source is
an integration candidate until both vendor SDK builds and device QA pass.

## API and seller flow

Both endpoints require a Clerk bearer token and listing ownership; API keys are
not accepted. Unauthorized listing references return 404 before calling Entrupy.

* `POST /v1/listings/{listing_id}/authentication/authorize`: accepts
  `sdk_authorization_request`, derives the vendor user ID from a hash of namespace
  and authenticated subject, signs via `/v2/integrations/authorize-user`, and returns
  `signed_authorization_request` plus `metadata` (brand, item_type, customer_item_id).
* `GET /v1/listings/{listing_id}/authentication`: retrieves the latest session via
  `/v2/lookup/authentications/{namespace:listing_id}` and requires a matching returned
  customer_item_id. Returns only result fields and a validated certificate link.
  Provider 404 is `not_submitted`; other upstream errors become a generic 502.
  Disabled/missing credentials returns 503. Both responses disable caching.

Seller closet listing details expose capture and result-check buttons. Every
capture begins with SDK cleanup and fresh authorization. Native capture handles
image collection and submission directly to Entrupy. Returning from capture does
not prove authenticity; sellers explicitly check the server result afterward.
A final `authentic` result without flags or required retakes enables a certificate
link restricted to HTTPS on cert.entrupy.com. Logout clears the SDK session.

Results are live reads, not persisted in listing analysis JSON. There are no
webhooks, scheduled polling, buyer badges, automatic publication blocks or changes
to valuation. Generic AI analysis remains independent of Entrupy authentication.
Re-capture can incur partner charges; use Entrupy support/result UI for disputes.

## Local verification

Pause verification — November 15, 2026: Expo autolinking discovery excludes
Entrupy for both Apple and Android while retaining the other native modules;
application JavaScript compiles with the Expo Babel preset. The 11 retained
backend tests and three analysis-guide tests pass, and the generated guide is
synchronized. These checks do not validate a native device build or deployment.

Historical candidate verification:

The 11 Entrupy backend tests and three guide tests pass. Eight mobile API tests
(including the Entrupy handoff) pass. Expo iOS JavaScript export and native module
discovery pass; these do not compile vendor SDK code. The existing production
submission guard test failed with a generic EAS CLI error instead of its expected
validation message. No deployment or app submission was performed.

## Verification before release

Run backend tests and mobile API tests, then build both native targets. On devices,
verify login, capture, cancellation, permission denial, background uploads, pending
and final results, retakes, logout/account switching, and certificate opening.
Confirm the account's actual not-found response and category fallback behavior.
Do not enable public authenticity claims without verifying capture-to-item binding
and an invalidation policy for listing edits and replacement items.

Sources: [Entrupy v2 API](https://developer.entrupy.com/api-reference/v2),
[iOS guide](https://developer.entrupy.com/docs/mobile-sdks/ios/overview),
[Android guide](https://developer.entrupy.com/docs/mobile-sdks/android/overview).
