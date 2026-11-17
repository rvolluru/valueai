# Standalone iOS Simulator build

Updated November 17, 2026. Build finished and standalone launch verified.

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

## Download and verification

[Download simulator archive](https://expo.dev/artifacts/eas/9XskqMmEYU7wbcgwxcujMOtXhkqu4HxXeqfDqLX9kh0.tar.gz?download=1&release=20261117).

- EAS build: `5f92430a-a951-4a41-a40c-fa674934b779`, FINISHED; source `907e8271d09ef41d74b45385efea7aca2ce34d72`.
- App: JOUFT 1.0.0, simulator CFBundleVersion 1, `com.jouft.app`.
- Architectures: **arm64 and x86_64**, supporting Apple Silicon and Intel Macs.
- Minimum iOS runtime: 15.1; install and signed-out landing-screen launch verified on iPhone 17 Pro, iOS 26.3.1, Apple Silicon.
- Bundled JavaScript, simulator platform, production API and Clerk-key match to AWS were independently verified. Entrupy seller UI is absent. No Metro server or Expo Go was used.
- All 43 mobile/configuration host tests passed. Authenticated workflows, Intel runtime launch and device-only features were not exercised in this smoke check. No production listing/profile mutation was performed.
- Archive SHA-256: `3d4f1fb73e7e7713480c117e6484367b5c1a4db37996a789bb7f9786496c73ef`.

[Machine-readable verification](IOS_SIMULATOR_VERIFICATION.json) ·
[Actual launch screenshot](evidence/ios-simulator-20261117/launch.png).

This archive targets the simulator; use TestFlight for a physical iPhone.
Real-camera capture and other hardware-specific behavior require device QA.
