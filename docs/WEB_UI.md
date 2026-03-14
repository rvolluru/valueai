# React Marketplace UI (MVP)

Location: `apps/web`

Features implemented:
- Sign up / Log in (Clerk when configured, local demo fallback otherwise)
- Item upload + `/v1/analyze` API integration
- AI analysis summary (brand / condition / valuation)
- Sell / trade listing creation workflow
- Marketplace browsing + similar-value trade suggestions

## Local run

```bash
cd apps/web
cp .env.example .env
npm install
npm run dev
```

Default API target is `http://127.0.0.1:8000` and can be changed in the UI top bar.

## Clerk authentication (frontend)

Set in `apps/web/.env`:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
```

The React app will use Clerk sign-in/sign-up and call the backend with a Clerk bearer token.

Backend must also be configured with Clerk verification settings (`CLERK_ENABLED`, `CLERK_ISSUER`, `CLERK_JWKS_URL`, etc.).

## Notes

- Local auth remains available as a fallback when Clerk is not configured
- If `VITE_CLERK_PUBLISHABLE_KEY` is set, Clerk auth is used and the UI sends bearer tokens to the backend
- Listing/trade data is local demo data + seeded sample listings
- Production deployment for the React app is not wired yet (currently AWS deploy serves FastAPI UI)
