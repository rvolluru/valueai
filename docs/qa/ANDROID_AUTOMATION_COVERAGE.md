# Android coverage against the manual QA plan

Updated November 7, 2026. All 64 cases are accounted for below. **New broad tests
are not yet device-verified.** “Recipe required” means a registered execution slot,
not a finished or passing business test. Manual gaps remain visible; do not report
the entire application as passing from smoke coverage alone.

See [suite setup](../../tests/devicefarm/ANDROID_SUITE.md) and
[defect workflow](DEVICE_FARM_DEFECT_WORKFLOW.md). Existing DF-001 publication
passes are tracked separately and do not validate the new broad suite.

| Case | Manual case | Android coverage | Implementation / remaining work |
| --- | --- | --- | --- |
| QA-001 | Launch and navigate | Native checks | test_navigation; each screen destination |
| QA-002 | Email/password sign-in | Native checks | Login prerequisite of each native case |
| QA-003 | Invalid credentials | Native checks | test_invalid_signin |
| QA-004 | Required sign-in fields | Native checks | test_required_signin_fields: empty and malformed identifiers |
| QA-005 | Password recovery | Recipe required | password_recovery; mailbox integration still required |
| QA-006 | Sign out and account isolation | Native + fixtures | test_signout; test_second_account_private_isolation |
| QA-007 | Session restoration | Native checks | test_resume_session |
| QA-008 | Registration and invite rules | Recipe required | registration; disposable inbox/invite prerequisite |
| QA-009 | Create clothing draft | Existing flow | test_create_listing / fresh test_review_publish; clothing fixture set |
| QA-010 | Create shoe draft | Configured existing flow | Set category Shoes and supply shoe photos; not exercised by full default Clothes setup |
| QA-011 | Handbag and accessory categories | Configured existing flow | Run separately with category-specific fixtures; handbag/accessory not exercised by full default |
| QA-012 | Photo count limits | Partial | test_create_without_photos covers zero only; 1–6/excess still manual |
| QA-013 | Photo coverage guidance | Partial | Existing creation requires complete coverage; insufficient-evidence guidance still manual |
| QA-014 | Category and condition validation | Partial | Existing create selects category/condition/size; invalid combinations manual |
| QA-015 | Back, cancel and repeated submit | Manual gap | Back/cancel/double-submit assertions not implemented |
| QA-016 | Camera capture | Recipe/manual required | camera_capture; managed camera may be unavailable |
| QA-017 | Denied photo permission | Recipe/manual required | photo_permission_recovery; OS action extension needed |
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
| QA-036 | Edit and persist | Recipe required | edit_save_restore; exact owned disposable fixture and cleanup |
| QA-037 | Publish draft | Existing flow | test_review_publish_existing / test_review_publish |
| QA-038 | Remove listing | Recipe required | delete_disposable; irreversible only on disposable seed |
| QA-039 | Browse, search and detail | Partial | test_search_known_title; test_marketplace_detail_gallery; pagination manual |
| QA-040 | Matches and preference eligibility | Recipe required | style_matching; known eligible/ineligible source-target pair |
| QA-041 | Like and share | Recipe/manual required | like_restore; external share sheet manual, no social posting |
| QA-042 | Compose and send proposal | Recipe required | trade_send; two users, eligible items, sandbox shipping/payment |
| QA-043 | Decline proposal | Recipe required | trade_decline; disposable proposal |
| QA-044 | Accept proposal | Recipe required | trade_accept; sandbox and disposable proposal |
| QA-045 | Duplicate/stale action | Recipe required | trade_stale_action; multi-session coordination still needed |
| QA-046 | Address validation and persistence | Recipe required | shipping_address_save_restore; controlled address |
| QA-047 | Quote and label | Recipe required | shipping_quote_label; sandbox verified |
| QA-048 | Payment method lifecycle | Recipe required | payment_add_default_remove; sandbox provider interaction extension as needed |
| QA-049 | Subscription changes | Recipe required | subscription_change_cancel; sandbox verified |
| QA-050 | Account and style persistence | Partial | Profile section loads; profile_save_restore requires reviewed recipe |
| QA-051 | Security actions | Partial | Security section renders; security mutations remain manual/disposable account |
| QA-052 | Activity and push preferences | Partial | test_notification_history; preference save/read state requires manual evidence |
| QA-053 | Push permission and delivery | Recipe/manual required | push_delivery; enabled entitlement, OS permission and sender event |
| QA-054 | Subscribe/unsubscribe preference | Other platform | Web preference control; no native control in current feature |
| QA-055 | Unsubscribe email link | Other platform | Email/web confirmation; separate service/browser tests |
| QA-056 | Daily new-match digest | Other platform | Scheduled worker/email test with controlled inboxes |
| QA-057 | No matches and opt-out suppression | Other platform | Scheduled worker suppression test with controlled inboxes |
| QA-058 | Assistant basic and listing flow | Partial | test_assistant_open_close; assistant_listing requires reviewed recipe |
| QA-059 | Offline and reconnect | Recipe/manual required | offline_recovery; network controls extension needed |
| QA-060 | Background during analysis | Recipe required | background_analysis; pending job fixture and assertions |
| QA-061 | Small screen and keyboard | Manual visual | Per-case screenshots aid review; no automated layout certification |
| QA-062 | Accessibility basics | Manual accessibility | TalkBack, focus order and text scaling need explicit accessibility run |
| QA-063 | Cross-account direct links | Other platform | Web direct-link case; native private isolation covered by QA-006 |
| QA-064 | Production smoke | Separate scope | Production smoke is not part of staging-mutating Android suite |

## Completion gate

- Supply reviewed listing fixtures, category-specific photo sets and a second test account.
- Implement/review recipes and necessary provider/OS actions before enabling controlled workflows.
- Confirm actual sandbox payment/shipping configuration before transactional cases.
- Run broad suite on the pinned Android device and classify every failure using the defect workflow.
- Resolve failures, run a second Android device/OS configuration, and retain new-build evidence.
- Complete manual visual/accessibility/OS checks and separate email/web cases.
- Require no unreviewed Blocked/Not Run cases for any whole-application release claim.

No manual gap, unconfigured recipe or other-platform case is silently marked Pass.
