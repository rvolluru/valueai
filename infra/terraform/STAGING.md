# Staging Environment (Separate from Production)

## Application rollouts (existing stack)

Verified October 25, 2026: source `ec13811`, image `staging-ec13811`, API task
revision 10 and worker revision 3. Migrations, service stability, public health,
unauthenticated rejection and authenticated assistant reads passed. Production
was unchanged. No listings, analyses or trade requests were created by verification.

Use `scripts/deploy_staging_services.py` for an already-built, versioned ARM64
image in the `valueai-staging-api` ECR repository. It validates staging database,
bucket and queue references, rejects live billing/shipping credentials and
unreviewed secret references, runs migrations first, updates the staging API and
worker, waits for stability and checks health/authentication. Rollout/smoke failure
restores the prior service task definitions. Migrations themselves are not reversed.

```bash
AWS_PROFILE=rajesh_volluru AWS_DEFAULT_REGION=us-east-1 python3 scripts/deploy_staging_services.py \
  --image 537595754494.dkr.ecr.us-east-1.amazonaws.com/valueai-staging-api:VERSIONED_TAG
```

No production service or Terraform state is targeted by that script. Do not copy
production users or payment credentials into staging. The staging web/API origin
is `https://staging.jouft.com`; `staging-api.jouft.com` is not configured.

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
