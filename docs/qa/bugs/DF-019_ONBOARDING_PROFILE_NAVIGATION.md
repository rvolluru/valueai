# DF-019 — Onboarding keeps Profile scrolled below its heading

- Status: Ready for retest
- Classification: Automation
- Severity: Medium
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Run: `848c71e9-8cf7-4bc3-9550-2ccd31c751c2`
- Device/build: Pixel 9 Pro XL / Android 15, staging Android 0.1.0 (4)

Registration and Clerk test-code verification completed, and the new QA profile was saved. The application advanced onboarding to Style while keeping the current vertical scroll position. The helper then required the offscreen SETTINGS heading to navigate within Profile, and its sign-out cleanup failed for the same reason. The account exists; do not blindly repeat registration or reset its password.

Candidate: restore the scroll position before locating Profile's heading when a Profile tab action is requested. Preserve original failure causes when cleanup also fails. A fully configured B sign-in/cross-account retest is planned, but that alone does not close this incomplete-onboarding regression; an isolated new-user onboarding retest is still required.

No application behavior or production authentication settings were changed.
