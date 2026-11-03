# Staging Environment (Separate from Production)

## Application rollouts (existing stack)

Verified October 25, 2026: source `ec13811`, image `staging-ec13811`, API task
revision 10 and worker revision 3. Migrations, service stability, public health,
unauthenticated rejection and authenticated assistant reads passed. Production
was unchanged. No listings, analyses or trade requests were created by verification.

Use `scripts/deploy_staging_services.py` for an already-built, versioned ARM64
image in the `valueai-staging-api` ECR repository. It validates staging database,
bucket and queue references, rejects live billing/shipping credentials and
unapproved secret references, reads production’s current model settings, runs migrations first, updates the staging API and
worker, waits for stability and checks health/authentication. Rollout/smoke failure
restores the prior service task definitions. Migrations themselves are not reversed.

```bash
AWS_PROFILE=rajesh_volluru AWS_DEFAULT_REGION=us-east-1 python3 scripts/deploy_staging_services.py \
  --image 537595754494.dkr.ecr.us-east-1.amazonaws.com/valueai-staging-api:VERSIONED_TAG
```

Production service task definitions are read only to copy model settings; the script
does not update production services or Terraform state. Do not copy
production users or payment credentials into staging. The staging web/API origin
is `https://staging.jouft.com`; `staging-api.jouft.com` is not configured.

## Model configuration parity

The staging release helper copies these environment settings from the matching
currently deployed production API/worker task definition: `GPT_ITEM_PROFILE_MODEL`,
`GPT_ITEM_PROFILE_GEMINI_MODEL`, `GPT_NEW_LISTING_PRICING_MODEL`,
`GPT_PRICING_MODEL_ROUTING_ENABLED`, and `GPT_ITEM_PROFILE_VERTEX_SEARCH_MODEL`.
It does not copy other production environment values. The staging Terraform var
file records the same current values: Gemini `gemini-3.8-flash`, base OpenAI
`gpt-5`, new-listing pricing `gpt-6.1-sol`, routing enabled, and empty Vertex model
override. Existing model assignments follow the normal cohort policy.

Verified November 3: configuration-only rollout API 16 / worker 9 completed at
desired task counts. A real Gemini request and public health passed. Application images, shared secret references,
timeouts and staging data configuration were preserved.

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
