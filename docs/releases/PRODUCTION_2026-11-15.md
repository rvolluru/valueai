# Production release — November 15, 2026

Status: validated locally; production deployment pending verification.

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

Deployment/build IDs and verified results will be recorded after completion.
