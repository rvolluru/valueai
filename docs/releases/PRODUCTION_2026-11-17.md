# Production release — November 17, 2026

Release `55e275f74d6568a71640ca057378e30d46e6190b` deployed successfully through
[workflow 44138546290](https://github.com/rvolluru/valueai/actions/runs/44138546290).

- API revision 199 and analysis-worker revision 67 are steady, each with 2/2 tasks.
  Existing environment values and Secrets Manager references are unchanged.
  Health returned `status=ok`; the workflow's post-deploy model smoke check passed.
- Front-aligned mannequin generation now requires explicit front-view validation
  before saving a candidate. Existing production previews were not regenerated.
- Production web includes Help, condition definitions, topic search reset,
  same-window Support navigation, app background/panel colors and the trademark logo.
  Listing Report Issue controls are hidden; support email remains available.
- This release also includes the previously committed Cettire pricing-source expansion.
- Validation: 176 API tests and 143 Node tests passed. Web production build,
  mobile JSX compilation, generated help and analysis guide checks passed.
- Android 1.0.0 (11), EAS `bdb204e3-533d-45df-a1f1-ced97c1d0eba`: FINISHED.
  [Download APK](https://expo.dev/artifacts/eas/-8ZP1OoXE2mGjeGUrAOLqmrBiBaMg4uUP6ognaE9aTA.apk?download=1&release=20261117).
  No Google Play submission.
- iOS 1.0.0 (69), EAS `a82f0bae-b4c2-4f99-833b-99929e119e88`: FINISHED,
  preserving `com.jouft.app.dev` and App Store Connect app `6791465341` on
  release branch `release/ios-existing-20261117` (`6ac1da9`).
  TestFlight submission `0840b95f-b05b-4c26-89e0-03a59edcc9c1` failed with Apple's
  server error. A read-only App Store Connect build lookup also returned HTTP 500.
  Delivery to TestFlight is not verified; check whether Apple received build 69
  before retrying. No public App Store submission was made.

[Service verification](PRODUCTION_2026-11-17_SERVICES.json).
Native device acceptance remains pending; successful builds are not device-test evidence.
The deployed image embeds the pre-verification guide. This documentation follow-up
records verified status for inclusion in the next image.
