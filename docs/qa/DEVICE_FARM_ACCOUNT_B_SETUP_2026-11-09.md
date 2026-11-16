# Device Farm staging account B — November 9, 2026

Status: **Account created/configured and fresh sign-in verified; all five selected native checks passed after focused retests.**

- Email: `rajesh_mid+clerk_test@yahoo.co.in`.
- Clerk subject: `user_3Lt5h7cMj2kZpzMdmu6Isp5Fik5` (a new ordinary staging identity).
- Credentials: `jouft/devicefarm/staging-login-b`, **us-east-1**, generated password stored only in Secrets Manager and read in memory.
- Device Farm: us-west-2, execution role `jouft-devicefarm-tests`; new inline `ReadSecondStagingTestLogin` policy permits GetSecretValue on that exact Virginia secret only. Existing account A permission remains unchanged.
- Staging Clerk instance: `firm-mink-35.clerk.accounts.dev`; existing Test mode was already enabled. Native registration used the app's Clerk SDK and `424242`; no inbox bridge or real Yahoo verification mail was required.
- Native APK: staging 0.1.0 (4), EAS `777562a3-e97d-4c64-a784-612d6179eafe`, Pixel 9 Pro XL / Android 15.

## Provisioning and fixtures

Native registration created the account and saved its QA personal profile. A staging-only fixture setup completed synthetic size/style preferences, a dummy QA shipping address and the free plan, with no card, charge, provider API call or real shipment. It seeded one B-owned matching listing, one uniquely named A-private listing and one A-owned excluded-preview fixture. The gallery fixtures reuse approved QA product imagery; the excluded fixture has a seeded exclusion decision. These are fixture states, not newly observed owner-publication actions.

[Fixture IDs and preservation checks](evidence/account-b-setup-2026-11-09/seed-results.json). All original A listings and the original `rajesh_mid@yahoo.co.in` profile were unchanged. Added QA records are deliberately retained for repeatable testing.

The runner now defaults broad native/required-B workflow runs to this Virginia secret. Override with `JOUFT_TEST_SECOND_SECRET` / `JOUFT_TEST_SECOND_SECRET_REGION`. Isolated registration has its own opt-in credential loader and cannot use shared-account credentials as a disposable registration identity. **59 focused host checks pass.**

## Retained registration attempts

| Run | Outcome |
| --- | --- |
| `45f21687-01df-4a11-ac4e-a2e034f17f55` | Setup manifest failed its fixture guard before native signup; corrected inputs. |
| `d5797481-8c98-4e01-9a81-bc33d7262775` | First Email field failed: shared element-scoped ancestor lookup, DF-018; no signup submitted. |
| `9e9fa1d8-a398-468a-b41a-44e60775121d` | Candidate hit a UiAutomator2 XPath 2 engine exception before entering Email; no signup submitted. |
| `848c71e9-8cf7-4bc3-9550-2ccd31c751c2` | Signup, test-code verification and Account profile save completed. Overall test failed navigating/signing out after onboarding advanced to Style; DF-019. Do not repeat signup or reset the created account. |

The field resolver now uses full-hierarchy XPath and the host's recommended XPath 1 compatibility setting. Profile navigation restores the scroll position before requiring its heading; original exception causes are retained when cleanup also fails. [DF-018](bugs/DF-018_ANDROID_FIELD_ANCESTOR_LOOKUP.md) and [DF-019](bugs/DF-019_ONBOARDING_PROFILE_NAVIGATION.md) retain their evidence/status. An incomplete-onboarding retest remains required for DF-019; a completed-profile sign-in alone cannot close it.

## Native cross-account verification

Original run `b8242749-e6c6-443d-8eb6-4cd998bc9ae0`: **2 Pass / 3 Fail**. Search and B's verified sign-in/private isolation passed. Three gallery cases stopped before opening detail because the helper counted nested accessibility nodes as separate cards ([DF-020](bugs/DF-020_NESTED_LISTING_ACCESSIBILITY.md)).

Focused retest `44210bd2-be1b-4889-8af8-0b298794d6b9`: **3 Pass / 0 Fail** on the same APK and device model/OS after grouping nested card targets. The latest result for all five selected cases is **Pass**; this combines retained executions rather than claiming one clean five-case run.

| Check | Latest result |
| --- | --- |
| A searches for B's matching listing | Pass |
| A opens B's detail/gallery and advances images | Pass |
| B signs in, shows VERIFIED identity, and cannot find A's private fixture in Closet or Marketplace | Pass |
| B sees the included mannequin and disclosure in A's public gallery | Pass |
| B sees original photos without the excluded mannequin in A's public gallery | Pass |

[Sanitized per-case evidence and archive digests](evidence/account-b-setup-2026-11-09/verification-summary.json), [original outcomes](evidence/account-b-setup-2026-11-09/cross-r1-results.json), and [focused retest](evidence/account-b-setup-2026-11-09/cross-r2-results.json).

Safe screenshots: [B's verified sign-in identity](evidence/account-b-setup-2026-11-09/second-account-verified-identity.png), [public include gallery](evidence/account-b-setup-2026-11-09/public-gallery-include.png), [public exclude gallery](evidence/account-b-setup-2026-11-09/public-gallery-exclude.png). The Security screenshot was captured only after checking all password-change fields were blank.

Raw recordings and logs are kept under `output/android-account-b-2026-11-09/`, excluded locally from Git. Only sanitized evidence belongs in docs. No app/backend deployment, production key, Clerk production setting, or real account password was changed.

## Remaining coverage

Observer authentication, disposable recovery data, trade/event fixtures and verified staging payment/shipping provider configuration remain prerequisites for other workflows. This account setup does not certify the entire application or close the separate assistant/Profile overlap defect.
