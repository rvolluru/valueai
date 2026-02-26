# API

Base path: `/v1`

Auth: `x-api-key: <API_KEY>`

UI:

- `GET /` serves a browser UI for testing uploads and viewing results/debug

## `POST /v1/analyze`

Multipart form fields:

- `item_id` (required)
- `images[]` (required, 1-4 files)
- `category` (optional): `clothes|shoes|handbag`
- `item_description` (optional): free-text description/title from user
- `purchase_year` (optional): integer year (used in valuation adjustment)
- `debug` (optional): `true|false`

Image expectations:

- `images[0]`: full item photo (required)
- `images[1..]`: recommended close-ups (tag/label, logo/hardware, monogram, defects)

Response:

```json
{
  "item_id": "abc123",
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
- Debug artifacts are saved to storage when `debug=true`.
- Optional GPT vision fallback can be enabled via env flags and runs only when OCR-based brand fusion returns `unknown`.
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
