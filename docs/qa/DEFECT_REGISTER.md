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

Follow [the workflow](DEVICE_FARM_DEFECT_WORKFLOW.md) when adding or changing a report.
