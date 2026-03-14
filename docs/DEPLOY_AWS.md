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

1. Create an AWS credentials profile with permissions for VPC, ECS, ALB, IAM, S3, RDS, CloudWatch Logs.
2. Copy and edit vars:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

3. Apply:

```bash
terraform init
terraform apply
```

4. Build and push API image to ECR (Terraform outputs repo URL).
5. Update ECS task definition image tag and re-apply (or wire CI/CD later).

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
