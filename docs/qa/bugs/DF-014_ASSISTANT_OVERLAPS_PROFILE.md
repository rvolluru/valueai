# DF-014 — Floating assistant overlaps the Android Profile tab

- Status: Ready for retest (local fix; not deployed)
- Classification: Application UI
- Severity: Medium
- Owner: Codex
- Reported: November 9, 2026
- Environment: staging Android 0.1.0 (4), Google Pixel 9 Pro XL / Android 15
- Run: `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3`

## Reproduction and evidence

Sign in, open Marketplace, and inspect the bottom navigation. The floating J assistant overlaps the upper part of Profile. A center-coordinate tap used by the automation does not reliably navigate to Profile. Four Profile-dependent checks failed at navigation before reaching their assertions.

[Actual device video frame, at 90 seconds](../evidence/DF-014/profile-tab-overlap.png).
The overlap is visible; the exact event routing on every failed tap is not proven by this frame alone.

## Next action and acceptance

Position the launcher above the navigation bar using its measured height and safe-area insets. Verify on Android with gesture and three-button navigation and on iOS; Profile and assistant must have separate, unobstructed touch targets.

The harness now taps the uncovered lower portion of each tab to continue independent checks. This is a diagnostic workaround, not a product fix. Do not close this defect based on those checks passing. The local application fix is described below; it has not been deployed or device-verified.

## Local fix — November 10, 2026

Moved the assistant launcher into a dedicated 62-point row immediately above the navigation bar, with a 12-point gap below the 50-point button. Both rows participate in normal layout inside the safe-area root, so navigation height and system insets cannot cause overlap. The launcher stays inside its parent's touch bounds; the unused row area lets touches pass through. This removes the fixed 84-point offset. When navigation is hidden, the launcher row sits above the safe-area bottom. Create still hides the launcher. The reserved row also prevents the launcher from covering page content or the Profile Save footer.

Validation: the modified application parses with Expo's Babel preset. Android gesture/three-button navigation and iOS touch-target verification remain pending on a new build. Keep this defect open until those checks prove that Profile and the assistant both respond independently; the existing automation workaround is not acceptance evidence.
