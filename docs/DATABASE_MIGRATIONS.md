# Database migration lifecycle

Schema changes run explicitly before application rollout, not in API requests,
email/reminder tasks, analysis retries, mannequin generation or image staging.

## Commands

```sh
PYTHONPATH=apps/api python -m app.migrations
PYTHONPATH=apps/api python -m app.migrations --check
```

Both use `DATABASE_URL` from the normal settings. The first applies pending
versions; `--check` only reads the migration ledger and fails if required versions
are missing. `make migrate` and `make schema-check` provide equivalent local commands.
`make run` and `scripts/backend-dev.sh start` migrate before launching the server,
so hot reload never performs schema work.

`Database.initialize()` remains an explicit migration helper for tests and local
tools. Runtime paths must not call it. They connect normally; API and worker startup
verify the required versions and fail clearly rather than silently self-migrating.

## Production deployment

The deployment workflow runs `scripts/run_ecs_migrations.py` before either the fast
ECS rollout or Terraform application rollout. It launches the **new image** as a
standalone migration task using the existing API service's network, database secret
and task permissions. Nonzero exit, timeout or launch failure blocks rollout.
No API or worker service is updated by the migration runner itself.

This requires existing infrastructure. Initial provisioning, or moving to a
different database/secret, must provision and migrate that target separately before
application rollout. The gate migrates the database referenced by the existing
service, not an unprovisioned Terraform target.

## Versioning and safety

- A database-scoped session lock prevents concurrent migration runners.
- `schema_migrations` records a version only after it succeeds. A rerun skips
  completed versions; failed versions are not marked applied.
- `0001_application_schema` bootstraps pre-versioned installations. It inventories
  existing columns before any legacy `ADD COLUMN`, avoiding duplicate-column lock
  attempts. Errors propagate instead of being swallowed. This legacy bootstrap
  commits incrementally and is intentionally idempotent for interrupted upgrades.
- `0002_analysis_listing_links` creates historical item/listing/owner associations
  and backfills only relationships established by stored IDs. It cannot reconstruct
  already-overwritten history without separately verified evidence.
- `0003_listing_media_urls` moves the former startup media repair into a one-time
  data migration.
- `0004_listing_pipeline_components` persists independent pricing/mannequin/staging
  checkpoints and immutable input snapshots, and indexes latest-job lookups.
- `0005_product_identities` stores versioned shared product identifications separately
  from pricing, allowing pricing refreshes without repeating identification.
- `0006_listing_product_identities` introduces strict listing/owner-scoped storage.
  Unscoped identities are not imported or read by the scoped implementation.
- Future schema or data changes need a **new** migration version. Never alter the
  meaning of a version already deployed. Keep migrations additive/backward-compatible
  while old API/worker instances drain; use transactions or idempotent operations
  so interrupted versions can be rerun safely.
- Readiness checks accept additional applied versions, allowing rollback to older
  application images when the schema changes are backward-compatible.

Table locks can still block a genuine pending migration. The runner fails rather
than pretending success. Long-lived idle transactions need separate transaction
lifecycle cleanup; they are not terminated automatically by this change.
