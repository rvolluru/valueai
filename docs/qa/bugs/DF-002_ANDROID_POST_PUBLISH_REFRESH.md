# DF-002 — Android post-publication verification uses unavailable tab

- Classification: Automation.
- Severity: Medium; repair priority: P1.
- Owner: Codex.
- Status: Closed — verified on staging Android build 4.
- Environment: Staging Android build 4, Pixel 9 Pro XL / Android 15.
- Run: `08c722f7-2e63-4637-924b-d38a0918e58b`.

After successful Publish without mannequin image, the test navigated to Create
then attempted to return through a tab bar hidden during creation. It failed on
that verification action even though server state was Active and both synthetic
assets had decision `exclude`. The new controls and publication had succeeded.

Expected: refresh Closet and verify persisted Active state without opening Create.
Fix: both publication scenarios now tap Closet Refresh directly. New run
`2e44da67-5358-4c7e-8bcd-5ae3d0b2b828` retests the same APK with updated harness.
Original evidence: `output/df001-exclude-artifacts/`; server-state verification
and controlled staging fixture reset: `output/df001-state-reset-log.json`.
No original failed result was changed to Pass. Closure awaits passing new evidence.

Retest passed: `2e44da67-5358-4c7e-8bcd-5ae3d0b2b828` (exclude) and
`d90e45d7-5ee0-4c97-90cc-dcbf37015c46` (include). Both verified persisted
Active state after direct Closet refresh. Original failed run remains unchanged.
