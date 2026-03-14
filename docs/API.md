# API

Base path: `/v1`

Auth:

- Legacy/MVP: `x-api-key: <API_KEY>`
- Clerk (recommended): `Authorization: Bearer <clerk_session_jwt>`

UI:

- `GET /` serves a browser UI for testing uploads and viewing results/debug

## `GET /v1/auth/me`

Requires a Clerk bearer token.

Returns the authenticated Clerk user identity (and claims in debug/dev configurations).

Example response:

```json
{
  "provider": "clerk",
  "user_id": "user_2abc...",
  "email": "seller@example.com",
  "username": "sellerfit",
  "first_name": "Avery",
  "last_name": "Lane"
}
```

## `POST /v1/analyze`

Multipart form fields:

- `item_id` (optional; auto-generated if omitted)
- `images[]` (required, 1-4 files)
- `category` (optional): `clothes|shoes|handbag`
- `user_condition` (optional): `New|LikeNew|Good|Fair|Poor`
- `item_description` (optional): free-text description/title from user
- `purchase_year` (optional): integer year (used in valuation adjustment)
- `debug` (optional): `true|false`

Authentication for this endpoint:

- `x-api-key` OR Clerk `Authorization: Bearer ...`

Image expectations:

- `images[0]`: full item photo (required)
- `images[1..]`: recommended close-ups (tag/label, logo/hardware, monogram, defects)

Response:

```json
{
  "item_id": "item-2f9f7f1f-1f02-4f72-bf2f-0f1b0f4f0ef0",
  "category": "shoes",
  "brand": {
    "name": "Nike",
    "confidence": 0.88,
    "evidence": "ocr_tag"
  },
  "condition": {
    "grade": "Good",
    "confidence": 0.78,
    "issues": [
      {"type":"scuffs","severity":"light","location":"unknown"}
    ]
  },
  "user_condition": "Good",
  "item_profile": {
    "model_identification": {
      "name": "Bing Crystal Mule 85",
      "confidence": 0.87,
      "attributes": ["pointed toe", "crystal strap", "85mm heel"]
    },
    "authenticity_screen": {
      "verdict": "inconclusive",
      "confidence": 0.62,
      "reasons": ["logo placement appears consistent", "serial/craft code not visible"],
      "required_checks": ["interior serial stamp", "stitch count", "hardware engraving macro"],
      "disclaimer": "Screening only; not definitive authentication."
    },
    "retail_price_estimate": {
      "estimated_price": 995.0,
      "currency": "USD",
      "confidence": 0.71,
      "rationale": "Comparable current season listings indicate high-900s USD.",
      "references": [{"source":"brand_site","url":"https://..."}]
    },
    "resale_price_estimate": {
      "estimated_price": 420.0,
      "currency": "USD",
      "confidence": 0.66,
      "rationale": "Comparable pre-owned listings for same/similar model cluster in low-400s USD.",
      "condition_assumption": "Good",
      "references": [{"source":"poshmark","url":"https://..."}]
    }
  },
  "valuation": {
    "estimated_value": 185.0,
    "currency": "USD",
    "range_low": 157.25,
    "range_high": 212.75,
    "confidence": 0.62,
    "basis": "median_sold_comps_with_condition_adjustment",
    "comps_summary": {
      "count": 7,
      "median_sold_price": 250.0,
      "source_breakdown": {"stub": 7}
    }
  },
  "requested_photos": [],
  "warnings": [],
  "debug": {
    "uploads": [],
    "brand": {
      "evidence_boxes": [],
      "ocr": [],
      "brand_candidates": [],
      "thresholds": {
        "BRAND_ACCEPT_SCORE": 78,
        "BRAND_ACCEPT_SCORE_LOW": 70,
        "BRAND_GAP_MIN": 8
      }
    },
    "condition": {
      "crop": {},
      "category": {},
      "condition": {
        "probabilities": {
          "New": 0.08,
          "LikeNew": 0.18,
          "Good": 0.46,
          "Fair": 0.2,
          "Poor": 0.08
        }
      }
    },
    "valuation": {
      "base_market_value_median": 250.0,
      "condition_multiplier": 0.75,
      "issue_deduction_total": 0.03,
      "selected_comps": []
    }
  }
}
```

Notes:

- Brand decision uses configurable medium-threshold fusion rules (env vars).
- `requested_photos` is populated when brand evidence is weak/contradictory.
- `user_condition` can be supplied by the client and is persisted for future model-training use.
- When `user_condition` is supplied, valuation uses the user-provided condition grade as the pricing input until the model is trusted with enough training data.
- `warnings` includes a condition mismatch warning when the user marks an item as `New`/`LikeNew`/`Good` but the model flags it as `Fair`/`Poor`.
- Debug artifacts are saved to storage when `debug=true`.
- Optional GPT vision fallback can be enabled via env flags and runs only when OCR-based brand fusion returns `unknown`.
- Optional GPT item profiling enrichment can be enabled via env flags (`GPT_ITEM_PROFILE_ENABLED=true`) to return:
  - exact model identification (best effort)
  - authenticity screening (`likely_authentic|inconclusive|likely_counterfeit`)
  - estimated retail price
- Valuation is returned when brand is known and valuation is enabled.
- Valuation uses `item_description` (for comp query context) and `purchase_year` (conservative age adjustment) when provided.

### Brand fallback debug fields

When `debug=true`, `debug.brand.gpt_vision` includes:

- `enabled`
- `called`
- `error`
- `candidate` (if GPT vision produced a brand candidate)

### Valuation providers (MVP)

Configured by `VALUATION_PROVIDERS` (comma-separated). Supported provider names:

- `stub` (implemented, local deterministic comps)
- `brand_site` (implemented, official brand-site retail comps via Firecrawl for `New` items)
- `firecrawl_agent` (implemented, optional structured Firecrawl agent market summary with separate new/resale medians)
- `ebay` (placeholder)
- `poshmark` (placeholder)
- `the_realreal` (placeholder)
- `rebag` (placeholder)

Implementation status:

- `ebay`: implemented using eBay Finding API (`findCompletedItems`) with `EBAY_APP_ID`
- `poshmark`: implemented best-effort HTML/Next.js parsing (listed/sold detection where available)
- `the_realreal`: implemented best-effort HTML JSON-LD/Next.js parsing (listed comps)
- `rebag`: implemented best-effort HTML JSON-LD/Next.js parsing (listed comps)
- Optional Firecrawl-backed page fetch can be enabled for JS-heavy sites (`poshmark`, `the_realreal`, `rebag`)
- `brand_site`: implemented for curated brands using official-site search pages scraped via Firecrawl; only runs when valuation condition is `New`
- `firecrawl_agent`: implemented as an optional structured fallback that asks Firecrawl Agent for separate `new` and `resale` market medians; its `new` median is treated as a retail reference and its `resale` median is treated as a resale comp

## `GET /v1/health`

Returns:

```json
{"status":"ok"}
```

## `GET /v1/version`

Returns:

```json
{"version":"0.1.0"}
```
