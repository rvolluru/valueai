# Production release — November 15, 2026

Status: production web/API and analysis worker deployed and verified. Android APK
available. iOS build 68 verified available in internal TestFlight.

Includes profile age validation and phone clearing, web profile/onboarding and
navigation/footer improvements, archived closet filtering, the Android assistant
footer fix, and expanded Device Farm scenarios and defect evidence. Entrupy is
paused: no seller controls, SDK sign-out hook, registered API router, or native
SDK autolinking. Retained source does not enable it.

Validation: 789 Python tests, 94 mobile/shared-client Node tests and 43 web Node
tests passed; web production build, Expo Babel compile, native Entrupy exclusion
for both platforms, analysis-guide synchronization and docs-site checks passed.
Device Farm acceptance is separate: prior full-suite blockers and open defects
are documented in the QA register; these host checks do not close them.

Deployment scope: production web/API and analysis worker; standalone Android APK
through Expo, with no Google Play submission. iOS delivery retains the previously
requested existing `com.jouft.app.dev` TestFlight identity and production API/auth
configuration. No staging deployment or credentials rotation is requested.
Raw recordings, credentials and scratch outputs are excluded from release archives.

## Verified delivery

- Source commit: `55ced443ea9c990e12f33a4e2c135cf8b27e5f50` on `main`.
- [Production workflow](https://github.com/rvolluru/valueai/actions/runs/43805821295): success, including database migration and final OpenAI/assistant smoke check.
- API task definition `valueai-mvp-api:198` and analysis worker `valueai-mvp-analysis-worker:66`: both steady with 2/2 tasks. Both use release `prod-148-55ced443ea9c990e12f33a4e2c135cf8b27e5f50`.
- Existing ECS environment values and Secrets Manager references compare unchanged for both services. Production mobile public configuration was synchronized from AWS us-east-1 to EAS; the APK and IPA embed the matching production Clerk key and `https://api.jouft.com`. No staging changes were made.
- Public `/v1/health` returned HTTP 200 with `status=ok`; live schema has no Entrupy authentication routes. Served web JavaScript includes the new birthday validation and updated goal-selection guidance.
- Android 1.0.0 (10), EAS `69ce0f32-dc54-4664-88bc-10bff359c034`: finished. [Download APK](https://expo.dev/artifacts/eas/XxYILE9p8IO3VGSvwDobuUmleqpJHWJnk0QHGkqSrg8.apk?download=1&release=20261115). ZIP, package/version, signature, production config and absence of Entrupy seller UI verified. Signing certificate matches production build 9. No Play submission.
- iOS 1.0.0 (68), EAS `acd85a35-f54c-4b7f-8da5-1b4e2351e49b`: finished. Source branch `release/ios-existing-20261115`, commit `c4a57060f6e93a0136a7d72e302a2877a89748ee`, differs only in the existing TestFlight identity/name and submission target. IPA independently verifies `com.jouft.app.dev`, production API/auth, and production push entitlement.
- [iOS submission](https://expo.dev/accounts/leavethemessage/projects/valueai-mobile/submissions/e3897938-8031-4ee6-af83-fed82070bf94): EAS reports FINISHED, targeting App Store Connect `6791465341`. Apple build `61fe776e-e212-420b-91df-d0b8b2aa15ea` is VALID, unexpired, and `IN_BETA_TESTING` internally. Install Jouft Testing 1.0.0 (68) in TestFlight. No public App Store review submission or new testers.

Initial iOS build 67 failed because the old profile lacked Push Notifications.
Enabled that capability for the existing bundle and regenerated its App Store
profile as `2J2RW4KZCY`, retaining distribution certificate `9K7LP49W6U`. Build 68
then succeeded; its embedded profile includes `aps-environment=production`. The
initial submission was automatically canceled after the build failed.

[Service verification](PRODUCTION_2026-11-15_SERVICES.json),
[APK verification](PRODUCTION_2026-11-15_ANDROID.json),
[IPA verification](PRODUCTION_2026-11-15_IOS.json),
[TestFlight verification](PRODUCTION_2026-11-15_TESTFLIGHT.json).

DF-014 remains Ready for retest: delivery is not acceptance evidence for Android
gesture/three-button navigation or iOS touch behavior. Other QA blockers remain
in the defect register. These builds do not establish full Device Farm coverage.

The deployed image contains the pre-verification guide. This release record and
canonical guide status are updated after verification in a documentation follow-up
commit; the updated reader edition will be included in the next service image.
