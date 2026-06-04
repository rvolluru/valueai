# Staging Environment (Separate from Production)

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
