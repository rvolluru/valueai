# Android coverage against the manual QA plan

Updated November 9, 2026. All 64 cases are accounted for below. All 21 former
workflow slots now have concrete implementations, documented in
[the workflow guide](../../tests/devicefarm/ANDROID_WORKFLOWS.md). **The broad suite has been attempted on Pixel 9 Pro XL / Android 15;
whole-application acceptance is blocked.** See [the execution report](ANDROID_DEVICE_FARM_RUN_2026-11-09.md). Manual/other-platform gaps remain visible; do not
report the entire application as passing from implementation or smoke coverage.

See [suite setup](../../tests/devicefarm/ANDROID_SUITE.md) and
[defect workflow](DEVICE_FARM_DEFECT_WORKFLOW.md). Existing DF-001 publication
passes are tracked separately and do not validate the new broad suite.

| Case | Manual case | Android coverage | Implementation / remaining work |
| --- | --- | --- | --- |
| QA-001 | Launch and navigate | Native checks | test_navigation; each screen destination |
| QA-002 | Email/password sign-in | Native checks | Login prerequisite of each native case |
| QA-003 | Invalid credentials | Native checks | test_invalid_signin |
| QA-004 | Required sign-in fields | Native checks | test_required_signin_fields: empty and malformed identifiers |
| QA-005 | Password recovery | Implemented; test inbox | password_recovery; separate disposable Clerk test account, restores password; real mail delivery separate |
| QA-006 | Sign out and account isolation | Native + fixtures | test_signout; test_second_account_private_isolation |
| QA-007 | Session restoration | Native checks | test_resume_session |
| QA-008 | Registration and invite rules | Implemented; policy fixture | registration; password mismatch, configured invite rejection, allowed signup/verification; disposable account retained |
| QA-009 | Create clothing draft | Existing flow | test_create_listing / fresh test_review_publish; clothing fixture set |
| QA-010 | Create shoe draft | Configured existing flow | Set category Shoes and supply shoe photos; not exercised by full default Clothes setup |
| QA-011 | Handbag and accessory categories | Configured existing flow | Run separately with category-specific fixtures; handbag/accessory not exercised by full default |
| QA-012 | Photo count limits | Partial | test_create_without_photos covers zero only; 1–6/excess still manual |
| QA-013 | Photo coverage guidance | Partial | Existing creation requires complete coverage; insufficient-evidence guidance still manual |
| QA-014 | Category and condition validation | Partial | Existing create selects category/condition/size; invalid combinations manual |
| QA-015 | Back, cancel and repeated submit | Manual gap | Back/cancel/double-submit assertions not implemented |
| QA-016 | Camera capture | Passed on Android 15 | camera_capture; actual capture/cancel/use, discard and permission restoration |
| QA-017 | Denied photo permission | Scoped-picker branch passed on Android 15 | photo_permission_recovery; runtime revoke/deny/grant where supported; Android 13+ scoped picker cancel/retry when no library permission is declared; selection and cleanup |
| QA-018 | iOS photo picker regression | Other platform | iOS-specific; not an Android case |
| QA-019 | Remote input responsiveness | Partial | Login helper uses native inputs; remote interactive response requires manual evidence |
| QA-020 | Analysis completion | Existing flow | Create flow asserts title/value/description before timeout |
| QA-021 | Detailed analysis and original evidence | Partial | Existing analysis summary and gallery; full reasoning/evidence quality manual |
| QA-022 | Unknown item and manual review | Native + fixtures | test_pricing_review_blocks_publication; ambiguous-item creation still manual |
| QA-023 | Edits survive asynchronous work | Manual gap | Concurrent owner-edit retention case not implemented |
| QA-024 | Photo change does not reuse stale results | Manual gap | Changed-photo analysis invalidation not implemented |
| QA-025 | Refresh/retry behavior | Manual gap | Controlled analysis rerun and retry state not implemented |
| QA-026 | Clothing mannequin preview | Partial | Existing flow checks AI disclosure/image load; appearance review manual |
| QA-027 | Shoe mannequin framing regression | Manual visual | Footwear framing/fidelity cannot be certified by UI text assertions |
| QA-028 | Mannequin approve and exclude | Existing flow | Include/exclude scenarios run separately; two fixture decisions required |
| QA-029 | View/edit preview consistency | Partial | test_search_review_navigation; image-decision consistency comparison still manual |
| QA-030 | Late preview on published listing | Manual gap | Late-generation/publication timing orchestration required |
| QA-031 | Image cleanup and gallery integrity | Manual visual | Optional cleanup and original-product integrity require review |
| QA-032 | Search title, brand and category | Native + fixtures | Known title, brand and category search |
| QA-033 | Search navigation regression | Native + fixtures | test_search_review_navigation |
| QA-034 | Rapid and empty search | Partial | Empty-search recovery implemented; rapid-query race manual |
| QA-035 | Filters and pagination | Manual gap | Pagination beyond viewport; mobile closet lacks web status filters |
| QA-036 | Edit and persist | Implemented; device pending | edit_save_restore; UI edits plus API persistence and UI restoration |
| QA-037 | Publish draft | Existing flow | test_review_publish_existing / test_review_publish |
| QA-038 | Remove listing | Implemented; device pending | delete_disposable; cancel/confirm, owner/B absence and sentinel preservation |
| QA-039 | Browse, search and detail | Partial | test_search_known_title; test_marketplace_detail_gallery; pagination manual |
| QA-040 | Matches and preference eligibility | Implemented; fixtures | style_matching; saved size, eligible/ineligible/self exclusion, restore and verify removal |
| QA-041 | Like and share | Partial | like_restore; persisted heart toggle and restoration implemented; social share/privacy checks remain manual |
| QA-042 | Compose and send proposal | Implemented; sandbox/accounts | trade_send; A request, B exact proposal selection, A review, single request IDs; decline cleanup |
| QA-043 | Decline proposal | Implemented; accounts | trade_decline; both-side status and closed UI assertions |
| QA-044 | Accept proposal | Implemented; sandbox/accounts | trade_accept; expected consent/items/charge and both-side accepted state; retained sandbox trade |
| QA-045 | Duplicate/stale action | Implemented; sandbox/accounts | trade_stale_action; B independent API races A stale native action/double click; state/labels stable; ledger reconciliation separate |
| QA-046 | Address validation and persistence | Implemented; device pending | shipping_address_save_restore; incomplete omission, complete/default persistence, profile restoration |
| QA-047 | Quote and label | Implemented; sandbox | shipping_quote_label; quote/currency, label identity/host, document navigation and reload; test labels retained |
| QA-048 | Payment method lifecycle | Implemented; sandbox | payment_add_default_remove; native Stripe test card, default/reload/remove, restore methods/default |
| QA-049 | Subscription changes | Implemented; sandbox | subscription_change_cancel; expected plan/price authorization, reload, cancellation and failure cleanup |
| QA-050 | Account and style persistence | Implemented; device pending | profile_save_restore; name/style persistence after re-login and original profile restored |
| QA-051 | Security actions | Partial | Security section renders; security mutations remain manual/disposable account |
| QA-052 | Activity and push preferences | Partial | test_notification_history; preference save/read state requires manual evidence |
| QA-053 | Push permission and delivery | Partial | push_delivery; B event, OS notification delivery/tap and one activity; push-denied/other OS variants still manual |
| QA-054 | Subscribe/unsubscribe preference | Other platform | Web preference control; no native control in current feature |
| QA-055 | Unsubscribe email link | Other platform | Email/web confirmation; separate service/browser tests |
| QA-056 | Daily new-match digest | Other platform | Scheduled worker/email test with controlled inboxes |
| QA-057 | No matches and opt-out suppression | Other platform | Scheduled worker suppression test with controlled inboxes |
| QA-058 | Assistant basic and listing flow | Implemented; feature/fixtures | assistant_listing; question, cancel/retry with photos, confirmed private draft analysis/review; no implicit publication |
| QA-059 | Offline and reconnect | Implemented; device pending | offline_recovery; Wi-Fi/data failure and recovery, original radios and listing data preserved |
| QA-060 | Background during analysis | Implemented; photos | background_analysis; actual create UI, same job ID before/after background, analysis/mannequin completion, no duplicate draft |
| QA-061 | Small screen and keyboard | Manual visual | Per-case screenshots aid review; no automated layout certification |
| QA-062 | Accessibility basics | Manual accessibility | TalkBack, focus order and text scaling need explicit accessibility run |
| QA-063 | Cross-account direct links | Other platform | Web direct-link case; native private isolation covered by QA-006 |
| QA-064 | Production smoke | Separate scope | Production smoke is not part of staging-mutating Android suite |

## Completion gate

- Account B has been provisioned ([setup/verification record](DEVICE_FARM_ACCOUNT_B_SETUP_2026-11-09.md)); supply remaining reviewed workflow fixtures and category-specific photo sets.
- Populate and review the 21 implemented workflow data fixtures, exact staging APK digest, and observer-session authentication.
- Confirm actual sandbox payment/shipping configuration before transactional cases.
- Review the actual broad-suite and focused retest results; resolve remaining Blocked cases and the tracked Profile-tab overlap using the defect workflow.
- Resolve failures, run a second Android device/OS configuration, and retain new-build evidence.
- Complete manual visual/accessibility/OS checks and separate email/web cases.
- Require no unreviewed Blocked/Not Run cases for any whole-application release claim.

No manual gap, unconfigured workflow or other-platform case is silently marked Pass.
