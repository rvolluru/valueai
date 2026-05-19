# Deploy on AWS (MVP)

## Architecture

- API + inference: ECS Fargate (CPU)
- Storage: S3 (uploads + debug artifacts)
- DB: RDS PostgreSQL
- LB: ALB (public HTTPS can be added with ACM later)
- Auth: `x-api-key` header (MVP)

No AWS Textract/Rekognition or vector DB is used.

Cost-focused default in this repo:

- ECS service runs in public subnets with public IPs (behind ALB)
- RDS remains in private subnets
- NAT Gateway is omitted to reduce monthly cost

Tradeoff:

- Lower cost for MVP/demo environments
- Less strict network posture than private-subnet ECS + NAT/VPC endpoints

## Local-first run

1. Install deps:

```bash
python3 -m pip install -e '.[dev]'
```

2. Start local API (SQLite + local disk storage):

```bash
cp .env.example .env
make run
```

3. Optional Docker Compose (Postgres + MinIO + API):

```bash
docker compose up --build
```

4. Test:

```bash
make test
```

## Terraform deploy

1. Create an AWS credentials profile with permissions for VPC, ECS, ALB, IAM, S3, RDS, CloudWatch Logs in the target account.
2. Copy and edit vars:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set one of these in `terraform.tfvars`:

- `aws_profile = "your-target-profile"` if your local AWS CLI profile already points to the target account.
- `aws_assume_role_arn = "arn:aws:iam::<target-account-id>:role/<role-name>"` if you need Terraform to assume a role into the target account.

Verify account before apply:

```bash
AWS_PROFILE=your-target-profile aws sts get-caller-identity
```

3. Apply:

```bash
terraform init
terraform apply
```

4. Build and push API image to ECR (Terraform outputs repo URL). Ensure the `container_image` account ID matches the target account.
5. Update ECS task definition image tag and re-apply (or wire CI/CD later).

## CI/CD deploy (recommended)

This repo includes a GitHub Actions workflow:

- `.github/workflows/deploy-prod.yml`
- Trigger: **Actions → Deploy Production → Run workflow**

It automatically:

1. Builds the API image
2. Injects `VITE_CLERK_PUBLISHABLE_KEY` at build-time
3. Pushes to ECR
4. Runs `terraform apply` with the new `container_image`

### Required GitHub repository secrets

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `VITE_CLERK_PUBLISHABLE_KEY`
- `TFVARS_PROD_B64` (base64 of your full `infra/terraform/terraform.tfvars`)
- `TF_BACKEND_CONFIG_B64` (base64 of Terraform S3 backend config)

Create `TFVARS_PROD_B64` locally with:

```bash
cd infra/terraform
base64 terraform.tfvars | pbcopy
```

Then paste into GitHub Secrets as `TFVARS_PROD_B64`.

Create `TF_BACKEND_CONFIG_B64` locally from a `backend.hcl` file like:

```hcl
bucket         = "valueai-terraform-state-537595754494"
key            = "valueai/prod/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "valueai-terraform-locks"
encrypt        = true
```

Encode and copy:

```bash
base64 backend.hcl | pbcopy
```

Paste into GitHub secret `TF_BACKEND_CONFIG_B64`.

### One-time migration to remote state

Run once locally after creating the S3 bucket + DynamoDB lock table:

```bash
cd infra/terraform
terraform init -migrate-state -backend-config=backend.hcl
```

This moves existing local `terraform.tfstate` into remote S3 state so CI and local use the same state.

## Required environment variables (ECS task)

- `API_KEY`
- `DATABASE_URL` (RDS PostgreSQL)
- `STORAGE_BACKEND=s3`
- `S3_BUCKET`
- `S3_REGION`
- `BRAND_ACCEPT_SCORE`
- `BRAND_ACCEPT_SCORE_LOW`
- `BRAND_GAP_MIN`
- Optional GPT vision fallback:
  - `BRAND_ENABLE_GPT_VISION=true`
  - `BRAND_GPT_VISION_MODEL=gpt-5`
  - `BRAND_GPT_VISION_TIMEOUT_S=20`
  - `OPENAI_API_KEY`
- Valuation:
  - `VALUATION_ENABLED=true`
  - `VALUATION_PROVIDERS=stub,ebay,poshmark,the_realreal,rebag`
  - `VALUATION_MIN_COMPS=3`
  - `VALUATION_MAX_COMPS=25`
  - `VALUATION_CURRENCY=USD`
  - `VALUATION_PROVIDER_TIMEOUT_S=12`
  - `VALUATION_PROVIDER_USER_AGENT=...` (optional)
  - `VALUATION_USE_FIRECRAWL=true` (optional, helps JS-heavy sites)
  - `FIRECRAWL_API_KEY=...` (required if Firecrawl enabled)
  - `FIRECRAWL_API_BASE_URL=https://api.firecrawl.dev` (optional override)
  - `EBAY_APP_ID=...` (required for eBay provider)
- Optional model weight paths if bundled/mounted

## Brand threshold tuning (medium unknown policy)

Defaults:

- `BRAND_ACCEPT_SCORE=78`
- `BRAND_ACCEPT_SCORE_LOW=70`
- `BRAND_GAP_MIN=8`

Behavior:

- Accept if top candidate >= `BRAND_ACCEPT_SCORE`
- Accept if top candidate >= `BRAND_ACCEPT_SCORE_LOW` and top-vs-second gap >= `BRAND_GAP_MIN`
- Otherwise return `unknown` and request close-up tag/logo photos

## Production notes

- Add ACM + HTTPS listener to ALB.
- For production hardening, move ECS service to private subnets and add NAT Gateway or VPC endpoints.
- Add WAF/rate limiting.
- Move API key validation to proper auth later.
- Bundle real detector/classifier weights and enable health checks for model load.
