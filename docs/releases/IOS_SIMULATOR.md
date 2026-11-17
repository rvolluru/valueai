# Standalone iOS Simulator build

Updated November 17, 2026. Build pending verification.

The `production-simulator` EAS profile inherits production API/auth configuration,
uses a Release build with bundled JavaScript, and sets `ios.simulator=true`.
It does not require Expo Go, a Metro development server, Apple signing, or a
TestFlight invitation. It does not increment the production build number and
cannot be submitted through the release wrapper. Entrupy remains disabled.

Create a build from `apps/mobile`:

```sh
npm run eas:build:ios:simulator -- --non-interactive --no-wait
```

The production public Clerk configuration must be present in the EAS production
environment (synchronized from AWS with `scripts/sync_mobile_production_env.py`).
No server secret is included in the app. This build connects to the real production
service; use your own account and expect listing/profile changes to persist there.

## Install on a Mac

Install Xcode and an iOS Simulator runtime. Start a simulator through
Xcode > Open Developer Tool > Simulator. Download and extract the shared `.tar.gz`
archive, then drag the extracted `.app` onto the running simulator.

Alternatively, install and launch the extracted app from Terminal:

```sh
xcrun simctl install booted /path/to/JOUFT.app
xcrun simctl launch booted com.jouft.app
```

The supported Mac architecture and download URL will be recorded after artifact
verification. This archive targets the simulator; use TestFlight for a physical
iPhone. Real-camera capture and other hardware-specific behavior require device QA.
