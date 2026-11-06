# Staging Environment (Separate from Production)

## Application rollouts (existing stack)

Verified November 5, 2026: release `2b1d87c` deployed to staging API 21 / worker 12
and production API 192 / worker 60. Both environments completed rollout at desired
task counts and passed public health, sign-in enforcement and exact served
JavaScript/CSS hash verification. Images update the homepage, mannequin-first
marketplace cards, removal of manual hero controls and upright preview generation
with an explicit orientation review gate. All container runtime settings and
secret references were preserved; no infrastructure or schema changes were made.
Native mobile source changes remain undistributed; no mobile builds were requested.

Verified November 5, 2026: website release `0043177` makes mannequin previews the
primary closet-card image, with original-photo fallback. Staging API revision 20
and production API revision 191 completed rollout; live bundle hashes, health
and unauthenticated assistant rejection passed. Web assets and the bundled guide
were layered onto each existing API image, preserving backend code, analysis
workers, all runtime settings and secret references. Native mobile builds were
not requested or deployed.

Verified November 3, 2026: source release `371c508` deploys shoe close-up framing
and the closet preview-control removal to staging (API 18 / worker 11) and production
(API 189 / worker 59). Migrations, completed rollouts, public health and sign-in
requirements passed. The image-only deployment preserved all live environment
values and secret references. Staging retains six-photo support, 240/300-second
timeouts, hybrid provider order and the shared AI-provider secret references.
The verified reader guide is published separately as an API image documentation
layer; worker code and runtime configuration remain the same.

Verified October 25, 2026: source `ec13811`, image `staging-ec13811`, API task
revision 10 and worker revision 3. Migrations, service stability, public health,
unauthenticated rejection and authenticated assistant reads passed. Production
was unchanged. No listings, analyses or trade requests were created by verification.

Use `scripts/deploy_staging_services.py` for an already-built, versioned ARM64
image in the `valueai-staging-api` ECR repository. It validates staging database,
bucket and queue references, rejects live billing/shipping credentials and
unapproved secret references, reads production’s current analysis settings, runs migrations first, updates the staging API and
worker, waits for stability and checks health/authentication. Rollout/smoke failure
restores the prior service task definitions. Migrations themselves are not reversed.

```bash
AWS_PROFILE=rajesh_volluru AWS_DEFAULT_REGION=us-east-1 python3 scripts/deploy_staging_services.py \
  --image 537595754494.dkr.ecr.us-east-1.amazonaws.com/valueai-staging-api:VERSIONED_TAG
```

Production service task definitions are read only to copy analysis settings; the script
does not update production services or Terraform state. Do not copy
production users or payment credentials into staging. The staging web/API origin
is `https://staging.jouft.com`; `staging-api.jouft.com` is not configured.

## Analysis configuration parity

The staging release helper copies the explicit `ANALYSIS_SETTINGS_KEYS` allowlist
from the matching currently deployed production API/worker task definition.
This includes brand and condition behavior, identification models, provider order,
pricing routing, research flags, photo limits, profile and overall attempt timeouts,
valuation settings, image staging/Photoroom behavior and mannequin configuration.
It removes stale staging overrides for allowlisted keys absent from production,
allowing the application defaults to apply. Infrastructure settings, credentials,
Vertex project/datastore IDs and access tokens are excluded. The normal staging
database, bucket, queue, billing and shipping isolation checks still apply.

Current production values include Gemini `gemini-3.8-flash`, base OpenAI `gpt-5`,
new-listing pricing `gpt-6.1-sol`, pricing routing enabled, six profile images,
`hybrid,gemini,openai` provider order, a 240-second profile timeout and a 300-second
overall analysis-attempt timeout. Existing pricing model cohort assignments follow
the normal routing policy. The staging Terraform var file records the current
production values for supported analysis variables.

Verified November 3: analysis parity rollout API 17 / worker 10 completed. The prior model-only rollout
(API 16 / worker 9) completed, but retained older staging timeouts and photo limits.
The broader rollout preserves application images, shared secret references and
non-analysis settings. Effective settings inside ECS, allowlist parity, completed
rollouts at desired task counts and public health passed. Production was unchanged.
The previously verified Gemini inference request remains applicable to its
unchanged model and key.

## Shared AI-provider credentials

Staging API and analysis worker use `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`PHOTOROOM_API_KEY`, and `FIRECRAWL_API_KEY` as ECS Secrets Manager references to
the same `valueai/prod/runtime` JSON fields as production. The execution role
`valueai-staging-task-execution-role` has `GetSecretValue` on that secret; ECS
injects only the four selected fields into these containers. Database, storage,
queue, billing/shipping credentials and feature flags retain their staging values.
Providing a Photoroom key does not enable background cleanup by itself.

`ai_provider_secret_arn` in `terraform.staging.tfvars` controls the four references.
`runtime_secret_arn` remains empty for staging, so the full production runtime
configuration is not injected. The deployment helper permits only these exact AI
references and rejects duplicate inline AI keys or other secret references.

ECS loads secret values when a task starts. After rotating a shared key, force a
new deployment of both staging services (and separately refresh production tasks
when desired). Editing the secret does not update a running container. Test a real
OpenAI response request as well as public health; a models-list request alone does
not establish available inference credits.

Verified November 3, 2026: API revision 15 and worker revision 8 reached completed
rollouts at their desired task counts. Public health and a real OpenAI response
request passed. Production task definitions remained API 188 / worker 58.

The November 3 credential rollout uses the existing service images and narrowly
updates IAM/task definitions. It does not apply the entire staging Terraform plan.

## Infrastructure changes

This repository now supports a separate staging stack using:

- State key: `valueai/staging/terraform.tfstate`
- Var file: `terraform.staging.tfvars`
- Distinct resource prefix: `project_name = "valueai-staging"`
- App env: `app_env = "staging"`

## Deploy staging

```bash
cd infra/terraform
terraform init -reconfigure -backend-config=backend.staging.hcl
terraform apply -var-file=terraform.staging.tfvars
```

## Deploy production

```bash
cd infra/terraform
terraform init -reconfigure -backend-config=backend.hcl
terraform apply -var-file=terraform.tfvars
```

Use `-reconfigure` whenever switching between prod/staging backends to avoid writing to the wrong state key.
