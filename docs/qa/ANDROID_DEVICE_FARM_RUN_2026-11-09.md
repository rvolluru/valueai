# Android full-suite execution — November 9, 2026

Status: **Execution completed; whole-application acceptance is blocked.**

Later follow-up: [account B setup and native cross-account verification](DEVICE_FARM_ACCOUNT_B_SETUP_2026-11-09.md). Counts below retain this earlier execution snapshot; new account/setup runs are reported separately.

The full 53-case Android suite was attempted on a real **Google Pixel 9 Pro XL / Android 15**, followed by focused retests of repaired automation. The latest result for each case is **29 Pass / 0 Fail / 24 Blocked / 0 Not Run**. These counts combine retained runs on the same APK and device model/OS; they are not a single clean full-suite run.

## Build and evidence

- Staging `com.jouft.app.dev`, **0.1.0 (4)**, EAS `777562a3-e97d-4c64-a784-612d6179eafe`.
- Native source: `c69446ffe8c2acf733ceca9db6cbb0dc2730aa4c`; embedded API origin verified as `https://staging.jouft.com`.
- 31 regression checks, 21 workflow scenarios, one fresh create/analyze/mannequin/review/publish check.
- Initial setup baseline `6aefd70d-2a5c-4fe7-a82d-ae7fc21ad8d2` stopped after repeated OTP field-selector errors. This stopped baseline is not counted as a completed suite.
- [Sanitized per-case results, archive digests and run history](evidence/android-full-run-2026-11-09.json). Raw device videos/JUnit/screenshots remain private under `output/android-all-2026-11-09/`.
- **52 focused host checks passed**. Host checks are separate from device acceptance.

| Execution | Run ID | Pass | Fail | Blocked | Not Run |
| --- | --- | --- | --- | --- | --- |
| Full suite | `20592dbb-482d-4570-953e-157b90ec3eb5` | 21 | 9 | 23 | 0 |
| Focused retest 1 | `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3` | 3 | 6 | 2 | 0 |
| Focused retest 2 | `6e980389-92c4-412d-be20-738b773a352e` | 7 | 3 | 0 | 0 |
| Focused retest 3 | `fda90d39-831c-4786-8edd-fece9ec0b51c` | 3 | 1 | 0 | 0 |
| Fresh-flow retest | `950346ce-ba47-4536-aba3-315af9719629` | 1 | 0 | 0 | 0 |

Use pytest case evidence rather than AWS phase counters. A complete-gate run remains unsuccessful when required cases are Blocked, even if all runnable cases pass.

## Findings and fixes

The [defect register](DEFECT_REGISTER.md) preserves classification, original evidence and retest status. Harness repairs cover OTP input selection, Unicode labels, empty-photo locator syntax, pricing-gate expectations, modal field readiness, missing-credential classification, camera discard confirmation, viewport-pruned listing cards, the scoped/Compose Android photo picker, and scrolling the actual mannequin disclosure into the gallery viewport. The APK preflight also retains pinned staging configuration/code checks across Device Farm processing.

**Application defect still open:** [DF-014 — assistant overlaps Profile](bugs/DF-014_ASSISTANT_OVERLAPS_PROFILE.md). The device video shows the launcher obscuring part of the Profile tab. Retests use its uncovered lower label to continue other checks. This is a diagnostic workaround; no product fix or deployment is claimed.

### Remaining case failures

No failed cases remain in the latest per-case results. This does not close the independently observed Profile overlap or the Blocked cases.

### Blocked prerequisites

- `test_search_known_title[marketplace]`: missing Android fixture marketplace_listing
- `test_marketplace_detail_gallery`: missing Android fixture marketplace_listing
- `test_second_account_private_isolation`: second dedicated staging account secret not configured
- `test_second_account_published_gallery[include]`: second dedicated staging account secret not configured
- `test_second_account_published_gallery[exclude]`: missing Android fixture published_exclude
- `test_controlled_workflow[registration]`: missing workflow environment reference email_env
- `test_controlled_workflow[password_recovery]`: missing workflow environment reference email_env
- `test_controlled_workflow[profile_save_restore]`: staging account A observer token is required
- `test_controlled_workflow[style_matching]`: missing workflow fixture field source_title
- `test_controlled_workflow[edit_save_restore]`: staging account A observer token is required
- `test_controlled_workflow[delete_disposable]`: missing workflow fixture field title
- `test_controlled_workflow[like_restore]`: missing workflow fixture field title
- `test_controlled_workflow[trade_send]`: missing workflow fixture field target_title
- `test_controlled_workflow[trade_decline]`: missing workflow fixture field offer_id
- `test_controlled_workflow[trade_accept]`: missing workflow fixture field offer_id
- `test_controlled_workflow[trade_stale_action]`: missing workflow fixture field offer_id
- `test_controlled_workflow[shipping_address_save_restore]`: staging account A observer token is required
- `test_controlled_workflow[shipping_quote_label]`: missing workflow fixture field offer_id
- `test_controlled_workflow[payment_add_default_remove]`: staging account A observer token is required
- `test_controlled_workflow[subscription_change_cancel]`: staging account A observer token is required
- `test_controlled_workflow[push_delivery]`: missing workflow fixture field listing_id
- `test_controlled_workflow[offline_recovery]`: staging account A observer token is required
- `test_controlled_workflow[background_analysis]`: staging account A observer token is required
- `test_controlled_workflow[assistant_listing]`: missing workflow fixture field answer_fragment

The missing prerequisites fall into account credentials/OTP, disposable accounts, observer authentication, reviewed listing/trade fixtures, and verified provider configuration. Account B is `rajesh_mid@yahoo.co.in`; its AWS login-secret name/region has been requested. Staging has no effective Stripe/Shippo credentials. Valid local sandbox keys were found but have not been deployed; absent credentials do not establish sandbox mode. See [DF-003](bugs/DF-003_STAGING_TRANSACTION_CONFIGURATION.md).

## Mutation and deployment notes

The full run, second focused run and third focused run each created a staging QA draft before a test-harness failure. Their analyses actually succeeded. Only those new failed-test drafts (`fde6f255-9b8f-4bba-9fda-256c11fa9b23`, `240c17ec-d846-4576-9af1-3ed8603a7718`, `d716a233-3056-4d46-9632-f9082c2fe0e1`) were deleted after checking ownership, status, terminal jobs and no active trades. Both original account listings were preserved. The final fresh-flow case passed with an explicit include choice and persisted Active behavior; its published staging QA listing is intentionally retained. Camera/photo temporary-file cleanup is recorded in workflow cleanup artifacts.

No app/backend deployment or production key/settings changes were performed. Unrelated worktree changes were preserved. Application-wide confidence also requires the [remaining manual/other-platform coverage](ANDROID_AUTOMATION_COVERAGE.md) and another Android device/OS configuration.

## Fresh-flow screenshots

- [Generated mannequin and disclosure](evidence/DF-017/listing-mannequin-success.png).
- [Persisted Active listing view](evidence/DF-017/review-publish-success.png).
- [Publication assertions](evidence/DF-017/review-publish-checks.json) and [explicit include decision](evidence/DF-017/mannequin-publication-decision.json).
