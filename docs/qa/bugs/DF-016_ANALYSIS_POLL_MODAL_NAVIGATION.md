# DF-016 — Analysis polling opens Create and loses the navigation footer

- Status: Closed
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Run: `6e980389-92c4-412d-be20-738b773a352e`
- Device/build: Pixel 9 Pro XL / Android 15, staging Android 0.1.0 (4)

## Evidence

Fresh creation and analysis succeeded. The polling routine opened the full-screen Create modal merely to refresh the closet, then tried to find a Closet footer tab hidden by that modal. The final screenshot shows the empty Create form, rather than failed analysis.

Private video and JUnit are retained in `output/android-all-2026-11-09/focused-r4-artifacts/`.

## Candidate and acceptance

Use the visible Closet Refresh action after returning from detail. Retest the complete fresh creation, analysis, mannequin decision and publication flow.

This is a test-only repair; no app/backend or production configuration changes.

[Failed-test draft cleanup evidence](../evidence/DF-016/failed-test-draft-cleanup.json): the exact new draft was removed after terminal analysis/component checks; both original account listings were unchanged.

## Verified retest

Run `950346ce-ba47-4536-aba3-315af9719629`, same staging build 4 and Pixel 9 Pro XL / Android 15. The complete fresh flow passed after using Closet Refresh rather than opening Create to refresh.

[Fresh-flow assertions](../evidence/DF-017/review-publish-checks.json) and [explicit include decision](../evidence/DF-017/mannequin-publication-decision.json).
