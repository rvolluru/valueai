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
# Email update preferences

Deployed to staging and production November 2, 2026.

- `GET /v1/me/email-updates`: authenticated; returns `{ "subscribed": true|false }`
  for the account's saved profile email. Missing profile email returns 409.
- `PUT /v1/me/email-updates`: authenticated; accepts `{ "subscribed": true|false }`.
  A strict boolean is required. The server resolves the address from the profile.
- `GET /v1/email-updates/unsubscribe?token=…`: token-authenticated confirmation page;
  does not modify preferences. Invalid tokens return 404.
- `POST /v1/email-updates/unsubscribe?token=…`: token-authenticated, idempotent opt-out;
  also supports one-click email-client POSTs.

See [daily match feed behavior and rollout](DAILY_MATCH_FEED.md).

## Entrupy item authentication (disabled)

As of November 15, 2026, this router is unregistered; these endpoints are unavailable
in the current source configuration even if `ENTRUPY_ENABLED=true`. The contracts
below describe retained dormant code. Production release `55ced44` was deployed and verified on November 15, 2026;
Entrupy routes remain absent from its live schema.

Clerk bearer token and listing ownership required:

- `POST /v1/listings/{listing_id}/authentication/authorize` accepts
  `sdk_authorization_request`; returns `signed_authorization_request` and
  server-derived capture `metadata`.
- `GET /v1/listings/{listing_id}/authentication` returns the live Entrupy result,
  final/authenticated booleans, retake state and eligible certificate URL.

No listing writes or publication changes. See [setup and contracts](ENTRUPY_INTEGRATION.md).

## Public Help & Support (production deployed November 24, 2026)

`GET /support` and `GET /support/` return the public web application shell without
authentication. The client renders searchable help before entering the sign-in
flow and without initializing a Clerk provider. This is user documentation, not
a new ticket-submission endpoint. Listing-specific support APIs are unchanged.
General email contact opens a draft for the user to review and send.

See [user help](USER_HELP.md) and [acceptance notes](qa/HELP_SUPPORT_ACCEPTANCE.md).


## Admin-managed membership trial invitations (production deployed November 24, 2026)

Migrations `0012_invitation_trials` and `0013_trial_listing_allowances` are required before starting the updated API.
Admin endpoints require an authenticated Clerk administrator; member endpoints
require Clerk sign-in. API keys cannot administer or redeem trial invitations.

| Endpoint | Behavior |
| --- | --- |
| `POST /v1/admin/trial-invitations` | Create an offer and return its plaintext code once; only its hash and last four characters are stored. |
| `GET /v1/admin/trial-invitations` | List configuration, usage/reservations and redemption history. |
| `PUT /v1/admin/trial-invitations/{offer_id}` | Edit future offer terms; existing and pending redemptions retain snapshots. Codes cannot be changed. |
| `PATCH /v1/admin/trial-invitations/{offer_id}` | Enable/disable new redemptions without revoking previously reserved or active trials. |
| `POST /v1/admin/trial-invitations/redemptions/{id}/revoke` | End an active non-renewing trial; does not cancel a paid Stripe subscription. |
| `POST /v1/me/trial-invitations/preview` | Check eligibility using the verified primary Clerk email; return terms and their version. |
| `POST /v1/me/trial-invitations/redeem` | Require consent and current `offer_version`; atomically reserve a place and grant no-card access or return Stripe checkout. |
| `GET /v1/me/trial-invitations` | Recover pending checkout completion and return current trial status. |
| `POST /v1/me/trial-invitations/sync` | Server-verify a Stripe session owned by this account and fulfill idempotently. |

Configurable settings: name/code, Starter or Pro plan, 1–365 trial days, a total listing allowance (1–2,147,483,647 or unlimited), required
card, expire-without-charge or automatic renewal, monthly/annual renewal cycle,
redemption start/end timestamps with timezones, total redemption limit, verified
email/domain restrictions (either list may match), first-trial-only and
new-subscriber-only eligibility. Empty restrictions permit any verified primary
email. Renewing trials always require a card and explicit recurring-charge consent.
Renewal prices use the existing server plan catalog. Codes do not bypass community
admission, age checks or profile setup. Membership benefits exclude shipping and
trade charges. Support for this feature is exposed in the shared help articles.

Non-renewing grants expire by server time without needing a scheduled job; they
overlay the existing profile only while valid and do not modify its saved billing
state. Profile saves cannot set subscription status/plan; billing activation remains
the authority. Existing paid/in-progress subscriptions are not replaced.

Card-required non-renewing offers use Stripe Setup Checkout, with no subscription
created. Renewing offers use Stripe Subscription Checkout with a trial and the
normal plan price. Starts and ends are captured after verified checkout; subsequent
renewals and cancellation use the existing billing integration. Stripe must send
`checkout.session.completed` and `checkout.session.expired` signed events as well
as the existing subscription/invoice events. Hosted checkout returns to the existing
`PUBLIC_APP_URL` for the environment, so staging does not redirect to production. Fulfillment runs before marking a
trial checkout event processed, allowing transient failures to be retried. Member
refresh/sync also recovers missed events. No code or client return URL grants access.

Capacity includes completed redemptions (including revoked ones) and pending
checkout reservations. Known sessions release reservations only after confirmed
expiry; sessions that never yielded a persisted URL can abandon their reservation
after an hour. Separate DB transactions serialize redemption checks across workers;
Stripe customer/session creation uses stable idempotency keys. Ten preview/redeem/
sync attempts per authenticated account per minute are allowed. Admin changes and
revocations are audited; redemption records preserve consent text, timestamp,
verified email and the original offer configuration.

Web: Admin → Trial invitations; members: Profile → Subscription. Shared links
prefill the code using `?tab=profile&invitation=CODE` but require sign-in and manual
confirmation. Mobile members can enter a code and refresh status after hosted
checkout. Native admin configuration remains on the web. Live Stripe/sandbox
acceptance and physical-device acceptance are still pending; automated provider
checks use mocked Stripe responses, never production charges.


Trial listing allowances (production deployed November 24, 2026):
`listing_limit` defaults to 25; any positive integer up to 2,147,483,647 is a finite
allowance and JSON `null` means unlimited. It is a total number of new listing
records during the trial, not a monthly reset or an active-inventory cap. Listings
created before redemption do not count. Drafts count when saved; subsequent edits,
analysis retries and publication of the same listing do not consume more slots.
Archiving or deleting a listing does not restore its used slot. A failed database
insert rolls back slot consumption. Profile/trial status returns `listing_limit`,
`listings_used` and `listings_remaining` (null for unlimited). Preview and stored
consent include the allowance; offer edits apply only to future redemptions.

All `Database.insert_listing` paths enforce the active trial allowance, including
assistant-created drafts. Listing insertion and the durable usage ledger commit
atomically under the trial transaction lock; exhaustion returns HTTP 409. Existing
listings remain editable. A paid upgrade stops applying the previous trial cap.
For a renewing trial, the custom allowance applies only through the original
trial end while the matching Stripe subscription is current; the normal paid
plan takes over afterward. This does not introduce new quotas for non-trial plans.


## Public profile usernames (production deployed November 24, 2026)

`GET /v1/me/profile-quiz` returns `username`. `PUT /v1/me/profile-quiz`
accepts an optional username: 1–40 ASCII letters, numbers, or underscores.
An optional leading `@` is removed and handles are stored lowercase. Invalid
handles return HTTP 400; a handle owned by another account returns HTTP 409.
Missing/blank values retain an existing handle or generate `first_name_last_name`
for a new profile, with numeric suffixes for collisions. Accents are transliterated;
unsupported names fall back to `member`. Handles are unique and independent of
Clerk login usernames. Changing first/last names does not overwrite an existing handle.

Migration `0014_profile_usernames` assigns handles to existing profiles and creates
a unique index. Web/mobile profile setup and account settings expose the handle;
listing owner labels show `@username` rather than the member's first name.
Listing API `owner_name` resolves the current profile handle on reads, including
older listings. Legal, billing, shipping and trade participant contact names remain
separate. No existing authentication credentials are changed.


## Signup-interest requests (production deployed November 24, 2026)

Home-page **Request Access** links to `/request-access`, a public information form
instead of account registration. Mobile opens the hosted form in its browser.
No password, Clerk account creation, or subscription is triggered. Each successful
submission queues an internal notification to admin@jouft.com through existing
SES/SMTP settings; no applicant email is sent.

- `GET /v1/access-request-options`: public states, size/range choices, curated
  mid/high-end brands, and the exact contact-consent wording.
- `POST /v1/access-requests`: public JSON submission; all fields required:
  `first_name`, `email`, `city`, `state` (US two-letter code), `clothing_size`
  (one or more distinct sizes from XS–XXL), `shoe_size` (one or more distinct
  US sizes 5–12 in half steps; both size fields are arrays, with legacy single
  fixed-option strings accepted and normalized to arrays), `owned_brands`, `wanted_brands`
  (1–5 distinct names each, custom names allowed, at most 80 characters per name),
  `listing_quantity` (`1-5`, `6-10`, `11-20`, `20+`), `typical_value`
  (`Under $150`, `$150-300`, `$300-600`, `$600-1,000`, `$1,000+`), and
  `email_consent: true`. Optional `website` is an empty honeypot field.
  Returns HTTP 201 and a generic receipt; validation errors are HTTP 422,
  honeypot submissions HTTP 400, and more than five attempts per normalized
  email per UTC hour HTTP 429. A repeat email updates the existing request,
  preserving original creation time. Consent wording and timestamp are stored.
- `GET /v1/admin/access-requests?limit=50&offset=0`: Clerk-admin-only paginated
  submissions, exposed in Admin → Access requests. No public email lookup.

Migration `0015_access_requests` adds request storage and persistent throttling.
These records are signup interests, not active accounts or automatic enrollment
in daily marketplace feeds. Existing profile onboarding is unchanged; the form
stores name, location, sizes, and brand preferences for later onboarding use.


### City/state autocomplete for access requests (production deployed November 24, 2026)

The form combines City / State into one searchable input. After three typed
characters and a 300 ms debounce it calls public
`GET /v1/google/places/city-suggest?q=...`. This uses the existing server-side
Google Places credentials, US region restriction and `includedPrimaryTypes:
["(cities)"]`, resolves address components and returns deduplicated
`{city, state, label}` suggestions. Unlike street-address search, a street is not
required. Selecting an option fills the existing separate city/state submission
fields; changing text invalidates the previous selection. The form requires a
selection before submission. Missing Places configuration returns HTTP 503.
Existing shipping-address suggestions are unchanged. Provider keys are never
returned to the browser. The dropdown includes Google attribution.

Provider reference: https://developers.google.com/maps/documentation/places/web-service/place-autocomplete


### Access request CSV and admin notification (production deployed November 24, 2026)

Admin → Access requests includes Download CSV. Authenticated Clerk admins can
fetch `GET /v1/admin/access-requests/export.csv`; it exports all requests across
pages with UTF-8 BOM, standard CSV quoting, and formula-safe applicant text.
Columns include all submitted fields, request ID, `submitted_at_utc` (original
creation), `last_submitted_at_utc` (latest submission), and consent wording/time.
Multiple sizes/brands use semicolon separators inside a cell. Response is
`Cache-Control: no-store`; UI download uses the admin bearer token.

After each accepted new or repeat submission commits, a background task sends
all submitted details and its UTC timestamp to the fixed recipient
`admin@jouft.com`. It uses the configured notification/SES/SMTP sender and email
provider (`auto` tries SES, then configured SMTP). Validation, honeypot and
rate-limit failures do not notify. Delivery failures are logged without changing
the successful saved request; this background notification has no automatic
retry or durable outbox. End-to-end inbox delivery has not been verified live; production SES configuration is verified.
