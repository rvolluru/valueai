# DF-017 — Gallery detection checks the caption outside the viewport

- Status: Closed
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Run: `fda90d39-831c-4786-8edd-fece9ec0b51c`
- Device/build: Pixel 9 Pro XL / Android 15, staging Android 0.1.0 (4)

## Evidence and diagnosis

The API audit confirms terminal succeeded analysis/pricing/mannequin/staging components. The actual device video at 600 seconds shows the generated mannequin in the detail gallery, with its lower portion and disclosure clipped below the viewport. The test only scrolled the Gallery heading into view, cycled images, and searched currently exposed accessibility text for the disclosure. Its 15-minute generation wait eventually failed despite completed generation.

[Actual gallery frame](../evidence/DF-017/gallery-caption-below-viewport.png). Private video, final assertions and source-site diagnostics are preserved in `output/android-all-2026-11-09/focused-r5-artifacts/`.

Owner draft galleries can contain pending previews. An earlier hypothesis that approval state alone explained the absence was rejected; no application change is justified by this test failure.

## Candidate and acceptance

Bring the gallery image/footer into the Android viewport before scanning its disclosure. Scroll back to the actual Back control when leaving the gallery. Once both mannequin publication actions are present, allow three unsuccessful preview polls before reporting a visibility failure rather than waiting for the full generation timeout.

Acceptance: the fresh flow visibly identifies the AI disclosure and loaded image, opens the actual closet Review and Publish action, makes an explicit mannequin choice and verifies persisted Active behavior. Actual image fidelity and another account's public gallery remain separate checks. No app/backend deployment or key/settings changes.

## Verified retest

Run `950346ce-ba47-4536-aba3-315af9719629`, same staging build 4 and Pixel 9 Pro XL / Android 15. The retest found the visible AI disclosure and loaded mannequin, opened Review and Publish, explicitly chose Publish with mannequin image, then refreshed and verified persisted Active behavior.

[Fresh-flow assertions](../evidence/DF-017/review-publish-checks.json) and [explicit include decision](../evidence/DF-017/mannequin-publication-decision.json).
