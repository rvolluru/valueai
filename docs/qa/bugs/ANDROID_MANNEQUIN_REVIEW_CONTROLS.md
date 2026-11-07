# Android bug: mannequin decision controls missing from Review and Publish

- **Tracking ID:** DF-001 (local report; no external issue filed).
- **Owner:** Codex (implementation and staging retest).
- **Repair priority:** P1.
- **Workflow:** [Device Farm defect lifecycle](../DEVICE_FARM_DEFECT_WORKFLOW.md).
- **Status:** Ready for final verification — staging Android include/exclude retests passed; cross-account gallery check pending.
- **Reported:** November 7, 2026.
- **Severity:** High — publishing a listing with a pending mannequin decision is blocked in the standard review flow.
- **Environment:** Staging; Google Pixel 9 Pro XL / Android 15.
- **APK:** EAS build `81efdfb8-1edd-4f20-b7c7-d8567e8127fd`, version 0.1.0, Android build 3, built November 2, 2026. Not a verification of a newer APK.
- **Device Farm run:** `914b08a8-54e9-40d9-8057-c17e64ee2bcc`.
- **Listing:** `db3ede13-0844-42bb-a559-b041eccb53f6` — Free People Eyelet Scalloped Shorts.

## Preconditions

Sign in to the dedicated staging account. The listing is in Review with completed
analysis, a $28 valuation, no pending pricing review, and generated mannequin
images awaiting an inclusion decision.

## Steps to reproduce

1. Open My Closet and locate the listing.
2. Open its Review and Publish / Listing Details screen.
3. Inspect the review actions and gallery for a choice to include the mannequin image or use original photos only.
4. Tap Publish.

## Expected

The standard Android review flow displays an explicit mannequin include/exclude
choice before publication. The selected decision is submitted with publication.
After successful publication, the listing is Active and its public gallery
respects that decision. Users should not have to switch to a separate assistant
workflow to complete the standard review task.

## Actual

The captured standard review screen shows Edit and Publish without the required
image-decision controls. Publication returns:

> Choose whether to include the mannequin image in Review and Publish

The listing remains unpublished. The automated run failed waiting for My Closet
after clicking Publish. Missing controls are an application defect, not an
expected feature omission or a device photo-permission failure. The original test
also lacked an explicit choice step; that separate test gap has been addressed
locally, but does not resolve the missing app controls.

## Evidence and implementation findings

- [Failure screenshot](../../../output/devicefarm-android-shorts-nov07-artifacts/create-listing-failure.png)
- [Captured UI hierarchy](../../../output/devicefarm-android-shorts-nov07-artifacts/create-listing-failure.xml)
- [JUnit result](../../../output/devicefarm-android-shorts-nov07-artifacts/junitreport.xml)
- The local standard review implementation in `apps/mobile/App.js` renders plain Publish and calls `publishListingToMarketplace(selectedListing)` without an image decision.
- `apps/mobile/src/components/ListingAgentChat.jsx` implements Include mannequin image / Use original photos only controls in the separate listing-agent review flow. Their presence there does not make them available in the standard Listing Details flow.
- The installed APK predates later repository changes. These observations establish the reproduced build's defect and a local standard-flow gap; they do not prove a particular commit was deployed or identify a platform rendering-engine cause.

## Retest acceptance criteria

1. Install the identified fixed staging APK on Android; record build and run IDs.
2. Review an existing draft with pending mannequin images through the standard closet path.
3. Verify controls are visible, accessible and usable, including on a small screen with scrolling.
4. On separate drafts, exercise Include and Original photos only. Verify saved Active status and the corresponding public gallery from a second account.
5. Verify pending pricing review still blocks publication; no backend guard is bypassed.
6. Preserve original failure evidence and attach new decision/publication artifacts.

No fix, deployment, external issue submission or passing retest is claimed by this report.

## Fix progress — November 7, 2026

Standard native review now renders explicit publish-with/publish-without actions
and sends `mannequin_choice` in the listing update. Synthetic assets are detected
even when previously excluded; plain Publish remains for listings without them.
Five shared media tests pass; analysis guide build/check pass. No production
release has occurred. Device Farm retest must use the new APK, not build 3.

Candidate: commit `c69446f`, EAS staging Android build
`777562a3-e97d-4c64-a784-612d6179eafe` (version code 4).
See [the retest record](DF-001_RETEST.md) for verification progress.

Both Android retests passed on build 4; see the retest record for run IDs and
retained evidence. Pricing-review regression checks pass. DF-001 remains open
until the remaining cross-account gallery acceptance is checked.
