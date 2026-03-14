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
