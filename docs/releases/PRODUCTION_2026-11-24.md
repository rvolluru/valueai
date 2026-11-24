# Production release — November 24, 2026

Production web/API and worker release `73bf2f420abe5f287dee4cccc6e3715da3d2a03d`
completed successfully through [workflow 45506303091](https://github.com/rvolluru/valueai/actions/runs/45506303091).
Feature commit: `a8b024d`; migration lock-wait fix: `aa85273`.

- API revision 200 and worker revision 68 are steady at 2/2 tasks each.
- The production model smoke check passed. Public health returned HTTP 200.
- Existing environment values, model settings, secret references and IAM roles
  were preserved. Only `IMAGE_STAGING_ENABLED` and
  `IMAGE_STAGING_PHOTOROOM_ENABLED` changed to false. No staging deployment ran.
- Versioned migrations 0012–0015 provide invitation trials, listing allowances,
  unique profile usernames and waiting-list submission storage.
- Admin-managed trials include configurable duration, card/renewal behavior,
  eligibility and 1-to-unlimited listing allowances. Stripe checkout acceptance
  remains a separate live-provider/device QA step; automated provider tests passed.
- Home-page Join waiting list opens the information collection form. It supports
  multi-select clothing/shoe sizes, searchable mid/high-end brands plus custom
  brands, city/state Places autocomplete and required contact consent.
  Admins can review submissions and download all rows as CSV with UTC timestamps.
  Successful submissions queue notifications to admin@jouft.com. SES sending and
  production access are enabled; the jouft.com sender domain is verified. No
  synthetic production submission or live notification email was sent during verification.
- Published Closet cards open Edit Listing; the matches-count button opens Matches.
  Review Listing uses the mannequin switch and a single Publish action, revised
  summary/description styling and public usernames. Profile setup includes handles.
- All accessory categories support close-up mannequin previews with product-specific
  support and fidelity checks. Existing previews were not regenerated. Original-photo
  background staging and Photoroom are disabled; mannequin generation remains enabled.
- Shared Help updates, mobile keyboard handling and birthday picker are included.
- Verification: 374 selected API tests, 142 JavaScript tests, web build, mobile JSX,
  generated Help/analysis guide checks. After rollout-preservation changes, 20
  migration/database checks passed. An outdated workflow assertion was updated to
  verify preservation rather than overwriting assistant runtime settings.
- Live checks: https://jouft.com/request-access returned 200; options returned 93
  brands; city suggestions resolved Austin, TX; unauthenticated CSV export returned
  401; deployed JavaScript contains the new controls.

## Mobile delivery

- Android 1.0.0 build 12, EAS `96336f65-edd8-44aa-a29f-86482af510f3`: FINISHED.
  [Download APK](https://expo.dev/artifacts/eas/cBTlvEpkeKKO2zihYkRQwdGE9LMJG7k237MAzkUbQG0.apk).
  No Google Play submission was made.
- iOS 1.0.0 build 70, EAS `0975a0d4-39d6-4d86-a273-17338a54cbfb`: FINISHED.
  Targets existing `com.jouft.app.dev` / App Store Connect app 6791465341 on
  release branch `release/ios-existing-20261124` (`0943398`).
  [Submission 19990649-a469-4fcd-95f5-c49dc39e6940](https://expo.dev/accounts/leavethemessage/projects/valueai-mobile/submissions/19990649-a469-4fcd-95f5-c49dc39e6940)
  successfully uploaded to Apple. Apple processing/TestFlight availability and
  native device acceptance are not yet independently verified. No public App Store release.
- EAS production public auth configuration was synchronized from AWS Secrets Manager
  in us-east-1 without printing key values. Mobile builds include feature commit
  a8b024d; subsequent commits only adjust server migration waits and workflow tests.

## Migration recovery

The first deployment attempts stopped before application rollout because two
long-idle database sessions held profile-table read locks. The migration-only
connection now uses longer bounded lock/statement timeouts. API/worker tasks were
gracefully refreshed on their previous revisions. A targeted cleanup rechecked
and closed only the two idle sessions, each older than five minutes and holding
no write-level relation locks; active transactions and writers were excluded.
The next workflow migration passed, then application rollout and smoke checks passed.
No schema/data rollback or manual profile edits were needed.

[Sanitized service verification](PRODUCTION_2026-11-24_SERVICES.json).
This documentation follow-up records verified status after rollout; the deployed
image contains the earlier pre-verification guide. It will receive these status
annotations with the next image build.
