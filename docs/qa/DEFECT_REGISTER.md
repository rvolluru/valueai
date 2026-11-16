# QA defect register

Local reports are tracked here until an authorized external tracker issue is
created. Unassigned means ownership has not yet been accepted. This is not a list
of every historical Device Farm failure; earlier untracked failures remain in the
Device Farm guide and need separate triage if they recur.

| ID | Report | Classification | Severity | Repair priority | Status | Owner | Deployment / retest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DF-001 | [Android mannequin decision controls missing](bugs/ANDROID_MANNEQUIN_REVIEW_CONTROLS.md) | Application | High | P1 | Ready for final verification | Codex | Android build 4: include/exclude pass; second-account gallery check pending |
| DF-002 | [Android post-publication refresh](bugs/DF-002_ANDROID_POST_PUBLISH_REFRESH.md) | Automation | Medium | P1 | Closed | Codex | Staging build 4: both publication retests pass |
| DF-003 | [Staging transaction providers missing](bugs/DF-003_STAGING_TRANSACTION_CONFIGURATION.md) | Test data/configuration | High | P1 | Blocked | Unassigned | Runtime credentials missing; sandbox not established |
| DF-004 | [Re-signed APK guard](bugs/DF-004_ANDROID_RESIGNED_APK_GUARD.md) | Automation | High | P1 | Closed | Codex | Staging preflight and camera passed; changed-container path tested on host |
| DF-005 | [OTP field selector](bugs/DF-005_ANDROID_VERIFICATION_FIELD_SELECTOR.md) | Automation | High | P1 | Closed | Codex | Verified on staging build 4; original failure and retest retained |
| DF-006 | [Unicode notification selector](bugs/DF-006_ANDROID_UNICODE_TEXT_SELECTOR.md) | Automation | Medium | P1 | Closed | Codex | Notification history passed on staging build 4; DF-014 workaround documented |
| DF-007 | [Empty-photo locator](bugs/DF-007_ANDROID_EMPTY_PHOTO_LOCATOR.md) | Automation | Medium | P1 | Closed | Codex | Verified on staging build 4; original failure and retest retained |
| DF-008 | [Pricing guard expects API wording despite native preflight rejection](bugs/DF-008_PRICING_GATE_CONTRACT.md) | Automation | Medium | P1 | Closed | Codex | Verified on staging build 4; original failure and retest retained |
| DF-009 | [Negative sign-in tests read a partially rendered modal](bugs/DF-009_AUTH_MODAL_FIELD_WAIT.md) | Automation | Medium | P1 | Closed | Codex | Verified on build 4; subsequent independent failures tracked separately |
| DF-010 | [Missing disposable auth credentials raise KeyError](bugs/DF-010_AUTH_PREREQUISITE_CLASSIFICATION.md) | Automation | Medium | P1 | Closed | Codex | Verified on staging build 4; original failure and retest retained |
| DF-011 | [Camera test omits the captured-photo discard confirmation](bugs/DF-011_CAMERA_DISCARD_CONFIRMATION.md) | Automation | Medium | P1 | Closed | Codex | Verified on staging build 4; original failure and retest retained |
| DF-012 | [Creation success assumes visible card count grows](bugs/DF-012_CREATION_VIEWPORT_COUNT.md) | Automation | Medium | P1 | Closed | Codex | Verified on build 4; subsequent independent failures tracked separately |
| DF-013 | [Photo recovery assumes an undeclared full-library permission on Android 15](bugs/DF-013_SCOPED_PHOTO_PICKER.md) | Automation | Medium | P1 | Closed | Codex | Passed on staging build 4 in focused r5; original evidence retained |
| DF-014 | [Assistant overlaps Profile](bugs/DF-014_ASSISTANT_OVERLAPS_PROFILE.md) | Application UI | Medium | P1 | Ready for retest | Codex | Footer-anchored fix in Android APK 10 / iOS build 68; device acceptance pending |
| DF-015 | [Empty-email validation message is missing from the test contract](bugs/DF-015_EMPTY_EMAIL_VALIDATION_CONTRACT.md) | Automation | Medium | P1 | Closed | Codex | Passed on staging build 4 in focused r5; original evidence retained |
| DF-016 | [Analysis polling opens Create and loses the navigation footer](bugs/DF-016_ANALYSIS_POLL_MODAL_NAVIGATION.md) | Automation | Medium | P1 | Closed | Codex | Fresh create/analyze/mannequin/include/publish passed on build 4 in r6 |
| DF-017 | [Mannequin gallery caption outside viewport](bugs/DF-017_MANNEQUIN_GALLERY_VIEWPORT.md) | Automation | Medium | P1 | Closed | Codex | Fresh create/analyze/mannequin/include/publish passed on build 4 in r6 |

| DF-018 | [Android field ancestor lookup](bugs/DF-018_ANDROID_FIELD_ANCESTOR_LOOKUP.md) | Automation | High | P1 | Closed | Codex | Native registration/profile fields worked; later navigation tracked as DF-019 |

| DF-019 | [Onboarding Profile scroll position](bugs/DF-019_ONBOARDING_PROFILE_NAVIGATION.md) | Automation | Medium | P1 | Ready for retest | Codex | New B account created; incomplete-onboarding navigation needs isolated retest |

| DF-020 | [Nested listing accessibility labels](bugs/DF-020_NESTED_LISTING_ACCESSIBILITY.md) | Automation | Medium | P1 | Closed | Codex | All three affected gallery checks passed on staging build 4; ambiguity guard retained |

Follow [the workflow](DEVICE_FARM_DEFECT_WORKFLOW.md) when adding or changing a report.
