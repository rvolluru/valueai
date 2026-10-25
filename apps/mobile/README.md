# Jouft Mobile (Expo)

This is a React Native + Expo scaffold for the Jouft listing flow.

## Included

- 3-step listing wizard
  - Step 1: upload photos + GPT photo analysis
  - Step 2: user item details + pricing analysis on Next
  - Step 3: review + publish button
- Calls existing backend endpoint: `POST /v1/analyze`
- Publishes listings to backend endpoint: `POST /v1/listings`
- Auto-fills title/description from GPT `item_profile`
- Uses AI valuation estimate for trade matching
- Supports both auth modes in-app:
  - `API Key` (`x-api-key`)
  - `Bearer` token (`Authorization: Bearer ...`) for Clerk-backed auth

## Shared API Client Scaffold

- Shared package: `packages/app-client`
- Mobile wrapper module: `apps/mobile/src/lib/apiClient.js`
- Goal: migrate all direct `fetch` calls in `App.js` into shared client methods for parity with web and mobile web.

## Run

```bash
cd apps/mobile
npm install
npm run start
```

Then open in Expo Go or simulator.

## Backend URL

Default is set in `app.json`:

- `expo.extra.apiBaseUrl = http://127.0.0.1:8000`

Use the right URL for your runtime:

- iOS simulator: `http://127.0.0.1:8000` usually works
- Android emulator: use `http://10.0.2.2:8000`
- Physical device: use your machine LAN IP, e.g. `http://192.168.x.x:8000`

You can also edit the API Base URL in the app UI.

## Build environments and app variants

Implemented October 25, 2026; not yet cloud-built or distributed in this configuration.

Environment setup verified October 25: EAS preview now has the staging API origin
(`https://staging.jouft.com`) and matching test Clerk publishable key. AWS staging
has a separate RDS database and upload bucket; its existing task has no Stripe or
Shippo keys configured. Staging backend source `ec13811` was deployed October 25:
migrations, API/worker stability and health checks passed; the assistant endpoint
returns 200 with staging authentication and requires authentication otherwise.
No mobile build was distributed by this backend rollout.
Production EAS configuration and a new production App Store record remain pending.

| Profile | App | iOS bundle / Android package / URL scheme | API | EAS environment |
| --- | --- | --- | --- | --- |
| development | Jouft Testing | com.jouft.app.dev | Local, configurable | development |
| staging | Jouft Testing | com.jouft.app.dev | Required staging origin | preview |
| production | JOUFT | com.jouft.app | https://api.jouft.com | production |

Development and staging intentionally replace one another on a device. Testing and
production coexist. The old Android testing APK used `com.jouft.app`: its next
testing release uses `.dev`. Existing iOS testing retains its identifier.

`app.config.js` is authoritative. Cloud archives exclude native directories so EAS
generates the chosen identity from config. Existing tracked native files are kept
as a development reference; `npm run ios` / `npm run android` regenerates development
configuration before running, without `--clean`. Do not run raw `expo run` to build
a different variant from stale native files. Review any resulting native diffs.

### Configure before building

Copy `.env.example` to `.env.local` for local development and provide your test
Clerk publishable key. Release profiles disable dotenv loading and omit local env
files from archives. Configure the following public values in EAS:

- **preview environment:** `JOUFT_STAGING_API_URL` and
  `JOUFT_STAGING_CLERK_PUBLISHABLE_KEY` (`pk_test_…`).
- **production environment:** `JOUFT_PRODUCTION_CLERK_PUBLISHABLE_KEY` (`pk_live_…`).

Use plain-text or sensitive visibility, not secret visibility: dynamic config must
read these publishable values locally during build resolution. They are bundled
in the app; never supply Clerk secret keys here. Missing configuration fails closed.
The npm release commands use `eas env:exec preview 'COMMAND'` or
`eas env:exec production 'COMMAND'` so public environment values are available
before dynamic config is evaluated. Local dotenv loading is disabled first.
For custom commands use that positional syntax (not `--environment`).
Staging rejects Jouft production hosts, localhost, insecure origins and live Clerk
keys. Production rejects test Clerk keys and conflicting public API/key overrides.

This does NOT provision a staging backend. It must use a separate database, image
storage, queues and test-mode payment credentials; a different hostname alone is
not proof of data isolation. Configure Clerk OAuth redirects, push credentials and
Apple Pay capabilities for each identity before physical-device release testing.

### Build and distribute

From `apps/mobile`, with EAS CLI authenticated:

```bash
npm run eas:build:ios:development
npm run eas:build:android:development
npm run eas:build:ios:staging
npm run eas:build:android:staging
npm run eas:submit:ios:staging
npm run eas:build:ios:production
npm run eas:build:android:production
```

Development iOS builds target the simulator; development Android includes the dev
client. Staging iOS uses TestFlight; staging Android is an installable APK.
Production Android produces a store AAB. No OTA updates are configured.

The existing App Store Connect record `6791465341` is staging/testing ONLY.
Create a NEW production record with bundle ID `com.jouft.app`, then set its numeric
ID in `eas.json` → `submit.production.ios.ascAppId`. Until then,
`npm run eas:submit:ios` deliberately refuses submission. Do not reuse the testing
record or assume the new identifier is registered. Production app version is
`1.0.0`; align the new store version accordingly. Build counters remain remote.

Test production release candidates via TestFlight on the production record, then
explicitly submit for App Review. Build/upload does not publish to the App Store.
Existing App Store compliance findings still apply; this separation does not fix
account deletion, Apple login, subscription billing or moderation.

Expo reference: https://docs.expo.dev/build-reference/variants/
