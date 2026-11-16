# DF-004 — Staging APK guard rejects Device Farm re-signing

- Status: Closed
- Classification: Automation
- Severity: High
- Repair priority: P1
- Owner: Codex
- Reported: November 9, 2026
- Scope: all Android workflow cases on the Amazon Linux 2 public-device host
- Build: staging Android 0.1.0 (4), EAS `777562a3-e97d-4c64-a784-612d6179eafe`
- Mutation outcome: no application mutation from this preflight check

The workflow preflight originally required the host APK's entire-file SHA-256 to
match the uploaded archive. AWS re-signs Android apps on public devices using the
Amazon Linux 2 host, changing the container/signature. That requirement would
reject the expected host artifact. Discovered during run preparation, before
claiming a workflow execution failure.

[AWS signing behavior](https://docs.aws.amazon.com/devicefarm/latest/developerguide/apps.html)
and [host run context](https://docs.aws.amazon.com/devicefarm/latest/developerguide/custom-test-environment-variables.html)
are the confirmed service contracts.

The candidate retains the exact APK hash path. If the container hash differs,
it permits only a Device Farm run context and requires independently pinned,
byte-for-byte SHA-256 matches for both `assets/app.config` and
`assets/index.android.bundle`. It still checks the embedded staging environment,
API origin and package. Code/config mismatch is rejected. Native payload integrity
beyond these files is entrusted to Device Farm's app-processing service; this is
not a general APK signature verifier.

Focused host tests cover accepted expected re-signing and rejected changed JS.
Original and updated test packages remain separate under
`output/android-all-2026-11-09/`. Candidate hardware retest:
`20592dbb-482d-4570-953e-157b90ec3eb5`, Pixel 9 Pro XL / Android 15.

Acceptance: the host-processed staging APK passes identity checks and a workflow
reaches its native actions; altered code/config remains rejected by host tests.
No production app/backend configuration was changed by this fix. Hardware acceptance passed: the camera workflow reached native capture and passed in run `4b2f1a44-ccc1-40aa-addd-a5cbdb4f7da3`. The altered-container compatibility branch is covered by host tests; the device result alone does not prove AWS changed the APK container on this run.
