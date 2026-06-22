# ValueAI Mobile (Expo)

This is a React Native + Expo scaffold for the ValueAI listing flow.

## Included

- 3-step listing wizard
  - Step 1: upload photos + GPT photo analysis
  - Step 2: user item details + pricing analysis on Next
  - Step 3: review + publish button
- Calls existing backend endpoint: `POST /v1/analyze`
- Publishes listings to backend endpoint: `POST /v1/listings`
- Auto-fills title/description from GPT `item_profile`
- Auto-fills target asking value from valuation estimate
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

## Share Builds With Testers (EAS)

Use these steps to share the app without requiring local dev setup on tester devices.

1. Install and login to EAS CLI:

```bash
npm install -g eas-cli
eas login
```

2. Link this app to your Expo project (first time only):

```bash
cd apps/mobile
eas init
```

3. Build internal testing artifacts:

```bash
npm run eas:build:ios:preview
npm run eas:build:android:preview
```

4. Share the generated install links/QR from Expo build output.

5. For app-store style testing:

```bash
npm run eas:build:ios:production
npm run eas:build:android:production
npm run eas:submit:ios
npm run eas:submit:android
```

Notes:

- iOS internal installs may require registering tester UDIDs unless using TestFlight.
- Android preview profile builds an APK for easiest direct install.
- `apps/mobile/eas.json` contains the build profiles.
