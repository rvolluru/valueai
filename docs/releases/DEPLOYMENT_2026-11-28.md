# Staging and production deployment — November 28, 2026

Source: `b1ae31bf7531bf29d84962ef144dda3f5ebfebca`.
Production workflow: https://github.com/rvolluru/valueai/actions/runs/46183586360 (success).
Sanitized service verification: `DEPLOYMENT_2026-11-28_SERVICES.json`.

## Changes

- Accessories, including scarves, now enter the parallel mannequin generation component.
- All mannequin generation attempts request complete-product close-ups within a central 4:3 hero-safe area; review checks framing.
- Marketplace web safe fitting is removed in both environments.
- Existing-session sign-in recovery opens My Closet instead of displaying an already-signed-in error.

## Verification

96 pipeline/mannequin tests and the sign-in regression test passed. Web build,
analysis-guide synchronization and diff checks passed. API and worker services
reached COMPLETED in both environments. Live web JS/CSS contain the Closet redirect
and no mannequin-safe-fit selector; both health endpoints returned ok.
Production workflow model smoke passed. Production environment and secret-binding
hashes match pre-deployment values; staging environment and secret bindings were
compared directly and match. Staging retains its own Clerk configuration and isolated data.

Staging migrations 0014 and 0015 initially hit profile-table locks held by idle
read-only transactions. Guarded one-off cleanup closed only idle SELECT sessions
holding profile locks and no write-level relation locks; the successful cleanup
used transaction age because the worker polled within the uncommitted transaction.
Migrations then succeeded and rollout proceeded. Production migrations succeeded normally.

No native build, app-store submission, production listing mutation or mannequin
backfill was performed. Existing scarf listings still need mannequin regeneration.
Post-deployment documentation status updates are committed separately from the deployed image.
