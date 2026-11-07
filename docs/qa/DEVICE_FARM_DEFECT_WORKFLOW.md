# Device Farm failure and defect workflow

Effective November 7, 2026. Applies to Android/iOS automated runs and remote-access
manual testing. This is the repository QA procedure; it does not automatically
create external tickets, change GitHub settings or deploy fixes.

## 1. Preserve the failed result — tester

Keep the original run and test result as failed. Record UTC time, run URL/ARN,
case/scenario, environment, exact APK/IPA build and source revision when known,
device/OS, fixture identity and failing stage. Capture relevant screenshot, video,
JUnit report, UI hierarchy and log excerpts. Record whether a listing, offer,
publication or payment was already created before failure.

Use `output/devicefarm/<run-id>/` for local evidence and keep each run separate.
Before Device Farm artifacts expire, retain required redacted evidence in the
team's access-controlled issue/evidence storage; local output paths alone are not
shared durable evidence. Do not upload raw credential-bearing Appium logs, test
passwords, OTPs, signed URLs, unsubscribe tokens or customer data. A pointer to
restricted evidence is preferable to copying sensitive content into an issue.

## 2. Triage — tester and engineering owner

Classify as **Application**, **Automation**, **Device/service**, **Test data/configuration**,
or **Unclassified**. Record observed facts separately from suspected causes.
A failed assertion is not by itself proof of an app bug. Preserve multiple causes
as separate linked defects when both the app and harness are faulty.

Reproduce once when useful and safe; compare another device/build if that resolves
uncertainty. Inspect current server state before repeating a mutation: a timeout
after Publish or Create Label can occur after the action succeeds. Never retry a
payment, label or publish blindly. Do not start concurrent runs on a shared account.
Unknown cause stays Unclassified with an investigation owner, not Pass.

## 3. Track and assign — triage owner

Search for an existing issue before opening a duplicate. Use the GitHub **Device
Farm defect** issue form, or copy [the local template](templates/DEVICE_FARM_DEFECT.md)
into `docs/qa/bugs/` when no issue tracker is available. Local reports are tracked
in [the defect register](DEFECT_REGISTER.md); add the external issue link when one
is created. Creating an external issue is a separate authorized action.

Record owner (or explicitly Unassigned), severity, repair priority, affected
builds/platforms, impact, evidence and acceptance criteria. Link the case's results
row to this issue/report. Mark the case Fail or Blocked as observed; never turn a
known failure into N/A because it is inconvenient.

| Severity | Meaning |
| --- | --- |
| Critical | Sensitive data exposure, wrong-account access, unintended real financial action |
| High | Core workflow blocked with no practical workaround |
| Medium | Partial malfunction with a practical workaround |
| Low | Cosmetic issue without task impact |

Repair priority (P0 urgent, P1 next planned fix, P2 scheduled, P3 backlog) is separate
from severity and from a test case's execution priority. Triage owner sets it based
on impact and release scope; uncertainty should be explicit.

## 4. Fix — assigned engineer

Move Open → Investigating → In progress. Link code/config/test changes to the report.
Fix the established cause; do not disable assertions, bypass app validation or edit
results to obtain a green run. Add focused regression coverage where warranted.
Application changes follow repository instructions, including analysis-process
document maintenance when relevant. Record local validation and any remaining risks.

A code change alone does not mean fixed on a device. Record the candidate commit,
build artifact and target environment, then mark **Ready for retest** only when that
artifact/configuration is available. Do not deploy unrelated changes under this process.

## 5. Retest — tester

Run the original reproduction against the identified candidate artifact on the
original device/OS configuration. Run affected branches and relevant regression
cases; compare another device when the suspected cause is device-specific.
Confirm server/public state where the test claims persistence or publication.

Use a new results row and evidence directory; link original failure and retest.
Record run/build IDs, date, observed outcome and regression scope using
[the retest template](templates/DEVICE_FARM_RETEST.md). If reproduction is blocked,
record Blocked and its dependency. A generic green run on a different build/case
is insufficient evidence for closure.

## 6. Close, reopen and release — tester and release owner

Close only when acceptance criteria pass, relevant regression checks pass and the
report contains the tested build and run evidence. Record deployment status
separately: **local only / staging verified / production deployed / production verified**.
Closing a staging defect does not imply production deployment.

If it still fails, mark Reopened, retain all earlier evidence and assign the next
investigation. Duplicate/Not a defect dispositions require a rationale and link;
they do not retroactively make the original test Pass.

Release review requires all applicable P0 cases passing and explicit review of
Blocked/Not Run coverage. Unresolved Critical/High defects normally block release.
Any accepted exception must record the release owner's name, rationale, mitigation,
scope and follow-up issue/date. QA recommends; the release owner decides. This
document does not authorize an exception or deployment by itself.

## Status transitions

Open → Investigating → In progress → Ready for retest → Closed.
Failed retest → Reopened → Investigating. Use Blocked with a named dependency and
next action rather than silently abandoning a report. Owners update the register
and report together; do not delete historical outcomes.

## Run handoff checklist

- [ ] Exact build, device/OS, scenario and environment recorded
- [ ] Failure classified; mutation outcome checked before retry
- [ ] Redacted evidence retained and accessible to the reviewer
- [ ] Issue/report linked; owner, severity and priority recorded
- [ ] Fix candidate and regression scope identified
- [ ] New retest evidence linked; disposition and deployment status accurate
- [ ] Release blockers/untested coverage communicated; test data and sessions cleaned up
