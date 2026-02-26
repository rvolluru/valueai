# ValueAI MVP

Production-leaning AWS cloud MVP for fashion item analysis from user-uploaded images:

- Brand prediction (OCR-first, logo classifier fallback)
- Condition grading + issue tags
- Valuation estimate (market comps + condition adjustment; stub comps provider included)
- Categories: `clothes`, `shoes`, `handbag`

## Repo layout

- `apps/api` FastAPI service (`/v1/analyze`, `/v1/health`, `/v1/version`)
- `packages/brand` OCR/fuzzy brand pipeline + fusion thresholds
- `packages/condition` cropper + category/condition model interfaces/stubs
- `infra/terraform` ECS Fargate + ALB + S3 + RDS + IAM (minimal)
- `scripts` training stubs and dataset validators
- `docs` API, labeling guide, AWS deployment notes

## Local run

```bash
python3 -m pip install -e '.[dev]'
cp .env.example .env
make run
```

Then open the built-in UI at:

- `http://127.0.0.1:8000/`

## Local test

```bash
make test
```

## Docker Compose (API + Postgres + MinIO)

```bash
docker compose up --build
```
