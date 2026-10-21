# Jouft listing analysis: complete process

Release candidate — October 21, 2026: the threaded assistant, listing tools and
chronological review UI described below are being prepared for production rollout.
Migration `0010_assistant_conversations` runs before application rollout; the web
build and API flags enable both assistant conversations and the listing agent.
Production verification is pending; local-only notes below are not yet a claim
of production availability. Existing form creation/evaluation and pricing-model
routing remain unchanged.

Local next-step guidance (not deployed): chat exposes missing required facts and
the next specific question from saved state, including after a context/status read.
Required evidence is requested before facts; optional recommendations do not block
progress. If a model turn stops after a read without a pending intake question,
bounded recovery uses existing saved evidence to set the next question. It does not
repeat a provider coverage call outside the turn timeout or infer approval. Old
sessions with no pending question still receive concrete read-only guidance.

Current local chat timeline (October 21; not deployed): messages, uploaded photo
sets, coverage results and review/confirmation states are ordered by saved event
times, not current listing stage. Session JSON keeps up to 80 deduplicated,
allowlisted presentation snapshots, including photo/coverage invalidation and
subsequent assessments. Parent replies retain their produced result cards. Old
untimed records use message-anchor inference (marked `inferred_time`), so exact
historical timing is not claimed where unavailable. Historical review/trade cards
are read-only; only the latest action card renders existing version-bound controls.
Approval tokens are not stored in timeline snapshots, and normal listing analysis,
valuation, ownership checks and confirmation rules are unchanged. This supersedes
the earlier local panel-placement descriptions below.

Local-only October 21, 2026: the threaded parent assistant can directly select
guarded operations on its linked, owner-checked listing session: evidence assessment/
removal, validated facts/corrections, analysis preparation/start/status, review and
trade preparation/cancellation. Real uploads still use the upload control. These
adapters reuse child request/tool ledgers, domain validation and bounded recovery;
they do not create new pricing/coverage rules. Final approvals remain separate
version-bound UI controls; model arguments cannot contain approval tokens or select
publication/trade-send/edit-confirmation operations. The parent composer is shared
with embedded upload/review controls, but child control history remains separate.
No production deployment, regular form change or automatic revaluation is included.
The local threaded UI now projects linked listing messages into the main transcript,
without nested history. Shared messages are deduplicated, uploads display as “Added
photos,” and current condition choices send normal parent-chat messages. New event
timestamps aid ordering; older records use shared-message anchors. This presentation
does not merge approval ledgers or change analysis/publication authorization.
During intake the photo panel follows the upload message before the next evidence/
fact question; condition choices are attached to their question. Review and approval
controls remain at the current end rather than at an old upload.
Local web/mobile photo panels show the persisted coverage assessment: category,
per-photo roles, missing required views, waived/unavailable views, optional
recommendations and warnings. Invalidated evidence is shown as not assessed;
timeouts/unavailable checks are not presented as successful coverage. The summary
explicitly distinguishes coverage from full item analysis/valuation, and adds no
model call or change to requirements. Not deployed to production.
Local confirmation placement uses separate photo/coverage and action-control
slots from the same listing controller. Photos stay at the upload step; current
analysis/publication/trade confirmation controls follow the latest message, after
the user's fact answers. This is presentation only, not a new approval path.
Local correction validation explicitly checks category-specific allowed sizes and
shows domain rejections in chat without mislabeling them as stale revisions. The
universal shoe-size example was removed. Rejected corrections do not save changes
or rerun valuation; actual revision conflicts still require reload/review.
Local chat correction replies explicitly report saved field values on success.
For an already-published listing, size correction rejection reports “not saved,”
the actual saved size, and the published-item editing limitation rather than asking
the user to wait for analysis. Invalid sizes still follow category allowlists.

Local threaded-chat entry point (not production): when both assistant-conversation
and listing-agent flags are enabled, chat may start a new listing session or resume
its owner-checked linked session/private-listing review. Opening a session does not
create a listing, run analysis, publish or trade. The existing photo/fact collection,
explicit analysis confirmation, worker dispatch, review and separate publication/
trade approvals remain authoritative. Web/mobile reuse the existing listing-agent
workflow inside the selected thread; parent state holds a session link, not copied
approval tokens. Ordinary form creation/evaluation, pricing and reuse are unchanged.

Local-only chat confirmation UX: general assistant publication and trade prompts
provide Yes/No buttons for the current pending action. Yes follows the existing
signed confirmation path; No cancels it. This does not bypass publication checks
or change analysis or pricing.

Updated October 21, 2026. This document explains the functional process: inputs,
model calls, decisions, outputs and user review—not a reliability assessment.

**Admin guide access (live-site verified October 19, 2026):** `/docs/listing-analysis`
loads a sign-in shell. The guide itself is fetched from
`/v1/admin/docs/listing-analysis` with a Clerk bearer token and server-side admin-role
authorization on every request. API keys alone do not grant access. HTML is packaged
outside public static assets and served with private/no-store caching and noindex.
The admin workspace links to this page. Authorized readers can still save copies.
Release `34a5a12` includes Docker packaging of this protected artifact. The production
web bundle contains the guide viewer and the document endpoint returns 401 without
a bearer token. Local authorization regressions verify 403 for non-admins and 200
with no-store for admins. GitHub's rollout status remained delayed/inconsistent at
this verification; full workflow completion and an authenticated production browser
check were not yet independently confirmed.

**Implementation status:** production release `635ec54` deployed successfully on
October 16, 2026. Persistent listing identification, explicit pricing refresh,
strengthened photo-content reuse checks and comparable policy v4 are deployed.
Parallel pricing/mannequin/cleanup processing remains enabled. Existing listing
values are not automatically recalculated by deployment.
**Deployed October 18, 2026, release `9bbe8f5`, workflow `39193566712`:** policy `same-brand-comparables-v5` adds enforced OpenAI
search-domain restrictions and server-side source-role validation described below.
**Deployed and enabled in `9bbe8f5`:** optional sticky pricing-model
cohorts use `GPT_PRICING_MODEL_ROUTING_ENABLED` (default false) and
`GPT_NEW_LISTING_PRICING_MODEL` (default `gpt-6.1-sol`). Existing listings are
grandfathered to GPT-5 by explicit migration `0008_listing_pricing_models`; new
listings requiring fresh pricing use Sol when routing is enabled. Gemini and chat
models are unchanged. Verified locally October 18: routing is enabled, 136 existing
listings were pinned to GPT-5, Sol model access returned HTTP 200, and the restarted
backend passed its health check. The production deployment now explicitly enables
routing on both API and workers, retains GPT-5 as the legacy/OCR model, and keeps
application-controlled research disabled to match local behavior. Explicit migration
0008 pins pre-existing production listings before either service is rolled out.
New duplicates may inherit the reused analysis's model assignment without a new
call; new fresh Sol listings remain on Sol for subsequent reruns.
The rollout completed successfully: migration and both ECS service stability checks
passed; the deployed smoke task verified routing settings, assignment-table access,
Sol model access and an OpenAI request. Public health returned OK. No listing values
were automatically recalculated.
**Deployed October 18, 2026, release `238f0d3`, disabled by default:** `GPT_CONTROLLED_RESEARCH_ENABLED=true` enables
the generalized per-site research and persisted snapshot path described in section 8.
Migration `0007_pricing_research_snapshots` must run explicitly before app startup.
**Deployed in `238f0d3`:** complete-analysis reuse no longer compares description
text or requires a saved description-input context. This applies to blank,
generated and owner-edited descriptions; explicit brand corrections remain a
separate reuse guard. The fallback in-memory profile cache also ignores description.
**Included in `238f0d3`, controlled research remains disabled:** protocol v2 uses ID-only comparable
selection and server-side factual binding. Research filtering now applies the same
source-title support checks as final validation. The observed seller-title spelling
“Louis Vuittion” is normalized only for an established Louis Vuitton identity;
generic fuzzy brand matching is not enabled.
**Deployed October 17, 2026, release `fecdad2`:** matching policy `same-brand-model-flexible-v3` removes
literal model-name and model-number equality requirements. Same-brand, same-product-family
comparables may use different names. Nonliteral exact claims are downgraded to
related/unconfirmed and require similarity and pricing-adjustment explanations.
**Deployed in `fecdad2`:** when primary-reference validation fails but accepted
comparables remain, OpenAI gets one pricing-only recalculation using only those
unchanged accepted records. Search is disabled, rejected records and the previous
price are excluded, and no currency conversion is performed. The retry preserves
identity, user condition and condition-pricing guidance. With no supplied official
retail evidence it must leave MSRP null. The server checks record immutability and
revalidates every primary reference against the original provider metadata. Retry
failure, changed evidence, unsupported references or insufficient evidence leaves
the item in manual review. The retry uses the remaining configured pricing-call
time budget and is skipped when five seconds or less remain. Debug evidence records
the attempt and original rejections; evaluation captures retain both calls.
**Hotfix deployed:** release `3da3a58` deployed successfully October 17, 2026,
to both API and analysis workers. Source matching policy
`source-identity-context-v2` relaxes overly literal title/summary comparisons as
described below. It does not change production model names, source eligibility,
retail guidance, condition pricing or the requirement for qualified resale anchors.
Model names are repository defaults;
environment configuration can override them.

This release also replaces OpenAI's legacy `web_search_preview` tool
with `web_search` and explicitly sets configurable chat reasoning effort (default
`low`). Candidate pricing/chat models are isolated in
`config/ai-model-candidates.env`, not activated automatically. See
[AI model lifecycle and evaluation policy](AI_MODEL_LIFECYCLE.md) for the inventory,
comparison procedure, weekly retirement reviews and promotion/rollback gates.
Production model names remain unchanged until evaluation and an approved deployment.

**Deployed comparable policy `same-brand-comparables-v4`.** OpenAI pricing
returns structured comparable brand/model, variant, condition, price type, price,
currency, URL and matching evidence. Exact brand/model/variant matches are preferred.
Similar models and unconfirmed variants from the same brand can also anchor resale
when the model explains their similarity and material differences/pricing adjustments.
Missing exact matches or discontinued models alone do not require manual review.
Different brands remain excluded. Native provider source titles are preferred. If
the retrieved URL has no native title, the comparable's model/product name can
instead match the short model-written summary for that same URL. This fallback
requires the URL to appear in actual provider search/open-page/citation metadata;
a URL present only in generated text is insufficient. An existing contradictory
native brand/product conflict cannot be overridden by a generated summary.
Short generic titles can be corroborated by provider-retrieved product URL paths
and source summaries. Accepted sources record `native_title`,
`model_reported_summary_retrieved_url`, `retrieved_product_url_identity` or
`retrieved_url_title_summary_context` support explicitly.
This verifies title support or generated-text consistency, not the truth of the extracted price,
variant or final transaction amount. A sold page's displayed price is not proof of
payment. Title checks ignore labelled catalog IDs/sizes, a leading collection year
and common condition/tag qualifiers. The hotfix normalizes Unicode hyphens,
possessives, the LV abbreviation for an already established Louis Vuitton brand,
and ZipThrough/Zip-Through spelling. It allows omitted descriptive color, trim,
fabric and condition words without a 60% whole-description overlap requirement.
In the deployed v3 matcher, model/collaboration names and model numbers need not
match exactly. Brand support and either two shared product terms or a shared
product family are required. Nonliteral exact claims (including different native
source model names) are treated as related/unconfirmed, with similarity and
pricing-adjustment explanations required. Target/comparable product families
must also be compatible. Explicit conflicting product families and denim/leather
descriptions remain blocked. A provider-retrieved product slug may corroborate a
short summary such as “Exact style title”; URL query keywords do not count as
product identity. Tracking parameters do not make the same retrieved page appear
unretrieved (including eBay itmmeta/itmprp tracking); item-identifying query and
eBay variation parameters are preserved. Brand-only URLs,
unretrieved model-written URLs and unrelated summaries still fail. This checks
source identity, not price truth, final payment or exact physical-item equivalence.

For the production hotfix, the broad comparable-policy marker stays
`same-brand-comparables-v4` (the separate local source-restriction candidate retains
v5); provenance adds `matching_policy: source-identity-context-v2`. Previously qualified analyses
remain eligible because this is a matching relaxation, not a new pricing/source
policy. Previously blocked listings are not automatically assigned a value; their
cleared estimates require a normal analysis rerun. No rejected source is silently
dropped to retain the original price: the deployed accepted-evidence repair instead
requests a new model estimate and validates it again.

Without qualified evidence, the policy clears retail/resale prices and all bands;
condition retries, retail-derived fallback and crawler fallback cannot restore a
value. Existing missing-value/manual-review/admin-alert handling applies. Provider
fallback results without this policy are also blocked from pricing. Cross-listing
full-analysis reuse requires the current qualified policy marker; older cached
prices are not reused. Saved item identification can still be reused independently.

### Document maintenance and version history

This is the canonical process document. Changes to the analysis workflow must update
it in the same commit as the implementation, including the updated date and deployment
status. See the [repository instructions](../AGENTS.md).

Git/GitHub history is the version record; separate dated copies are not needed.
Use `git log --follow -- docs/LISTING_ANALYSIS_PROCESS.md` to view revisions and
`git diff <older-commit> <newer-commit> -- docs/LISTING_ANALYSIS_PROCESS.md` to compare them.

## 1. Purpose and final outputs

The process turns original photos and user-provided item facts into:

- Identified brand, product/model and category, with supporting evidence.
- A listing title and item description.
- A resale/trade value for the selected condition, with available range, confidence,
  rationale and references.
- Product attributes, visual condition observations, authenticity-document expectations
  and shipping estimates where available.
- An optional AI mannequin styling preview.
- Optional cleaned-background versions of the original photos.
- A listing ready for owner review—or a manual-pricing-review requirement.

Analysis does not automatically publish the item. The owner reviews the result,
chooses whether to include generated images and decides whether to publish.

## 2. End-to-end flow

```text
Original photos
    ↓
Gemini: category + photographic coverage
    ↓
User: category, condition, size and optional description
    ↓
Create listing/job and resolve original-photo evidence
    ↓
    ┌────────────────────────┬────────────────────────┐
    │                        │                        │
Item analysis + pricing   Mannequin preview       Photo cleanup
    │                        │                        │
Reuse matching analysis   Plan from originals     Segment background
    OR                       ↓                        ↓
Use saved identity       Generate from front      Composite original
    OR                   reference photo         pixels over white
Gemini identification       ↓                        │
    ↓                    Inspect candidate            │
OpenAI pricing              │                        │
    ↓                        │                        │
Select condition-aligned     │                        │
value                       │                        │
    └────────────────────────┴────────────────────────┘
                             ↓
               Results saved independently
                             ↓
              Owner review / manual pricing review
                             ↓
              Choose images and publish
```

The three branches run in parallel. Pricing completion makes the listing reviewable;
optional images can finish later. Mannequin generation does not depend on the price
or on a pricing-generated title.
With controlled research enabled locally, the “OpenAI pricing” step expands to:
reuse eligible research snapshot → otherwise parallel per-site research and save
snapshot → search-disabled model valuation → frozen-evidence validation.

## 3. Inputs and their roles

| Input | Use |
| --- | --- |
| Up to six original photos | Identity, label reading, construction/condition evidence, mannequin references and cleanup |
| Category | Clothes, shoes, handbag or accessories; selects coverage requirements and processing paths |
| User condition | Authoritative pricing condition: New With Tags, New or Like New |
| Size | Product/listing context; pricing instructions prohibit size-based premiums or discounts |
| User description | Additional context for fresh analysis; not a criterion for analysis reuse |
| Explicit brand correction | Authoritative user correction; changes identification context |
| Listing ID and owner | Associate results correctly and scope saved identity |
| Pricing refresh request | Obtain fresh pricing without necessarily identifying the item again |

Original photos remain the analysis evidence. AI mannequin images and cleaned display
variants are not substituted for originals when identifying or valuing the product.

## 4. Upload photos and check coverage

The user captures photos in the mobile app or selects/uploads existing images.
The application stores originals and permits a hero-image selection. The hero is a
presentation choice, not an instruction to analyze only that image.

Gemini receives the supplied images and returns:

1. One category and category confidence.
2. A primary photographic role for each image, with additional roles when applicable.
3. Required/recommended photo coverage that is present or missing.

| Category | Required coverage | Recommended coverage |
| --- | --- | --- |
| Clothes | Full front, brand label | Full back, size/material label, condition/wear |
| Shoes | Side/profile, brand label, sole | Size/material label, condition/wear |
| Handbag | Full front, brand label, interior | Full back, hardware/detail, condition/wear, serial/authentication mark |
| Accessories | Full front, brand label | Size/material label, hardware/detail, condition/wear |

An image can satisfy more than one role. For example, hardware with inspectable
branding can provide both detail and brand-label evidence.

This call does **not** identify the exact model, authenticate the item or calculate
a value. It checks the category and photographic coverage only.

If the 30-second initial check does not finish, the photos remain available. The
user selects a category if detection did not complete and can continue. Only the
initial coverage check is skipped; full item identification and pricing still run.

## 5. Collect basics and start the listing analysis

The user selects condition and size and confirms/selects category. The app creates
the listing and its analysis job, displaying `Analyzing`. An edit or support rerun
can create a new analysis job for the same listing.

The worker resolves the complete current original-photo set and records photo
content hashes and user inputs. It does not infer current evidence solely from an
old source-item reference. A missing original is not silently treated as permission
to analyze a smaller photo set.

In production, the job is dispatched through the analysis queue. Local configurations
without a queue use application background processing. Once inputs are established,
item/pricing, mannequin generation and requested cleanup start independently.

## 6. Decide whether previous work can be reused

There are two distinct reuse decisions.

### Complete-analysis reuse across listings

A previous analysis can be reused **across listings and owners** when:

- Its pricing evidence has the current policy's qualified marker (`same-brand-comparables-v4`
  in production; local code requires `same-brand-comparables-v5`);
  older pricing must be researched again.

- The complete original-photo content matches. Photo order does not matter; changed,
  added or missing photo content does not qualify.
- User condition and category match.
- Explicit brand corrections are compatible with the analyzed brand.
- Brand/model identification is usable and a condition-aligned value can be selected.

Matching compares actual current photo bytes against evidence recorded for the source
analysis. It does not rely on filenames, file lengths, an old source-item pointer,
or photos that were attached to the source item after its analysis.
Description text is excluded from reuse matching, whether blank, AI-generated or
owner-edited. New listings commonly start blank, and saving generated copy must
not turn the same photos and condition into a different analysis request. Text
still reaches the model when a fresh analysis is explicitly requested or otherwise
required. Missing historical description metadata does not invalidate reuse.

If eligible, the application reuses the model evidence without repeating model calls
and reapplies the condition-selection rules. The receiving listing keeps its own
owner, listing ID, original photos and review decisions. The source listing's gallery,
mannequin decisions, pricing-review state and processing checkpoints are not copied.

Explicit pricing refresh and applicable fresh-analysis/correction paths bypass ordinary
complete-result reuse. If a listing already has a saved identity, a cached analysis
with an incompatible brand/model is not substituted for it.

The release regression test exercises upload/create/background-job/readback with
different source/new description text, checks identical reused value and condition
bands, and fails if fresh model analysis starts. The current deployment does not
automatically reconcile existing listings whose earlier independent estimates differ.

### Sticky pricing-model assignment (deployed and enabled in production)

Production release `9bbe8f5` enabled this routing on the API and analysis workers.
Existing listings were persisted as GPT-5 by migration 0008; new listings requiring
fresh analysis use Sol and retain their assignment on later reruns.

Complete-analysis reuse still runs before a new model is selected. With routing
enabled, an eligible new duplicate inherits its reused analysis's recorded pricing
model (legacy analyses without model metadata are treated as GPT-5), without a
model call. Source pricing-model provenance is rebound to the receiving listing
and owner. An already pinned listing does not accept cached pricing from another
model cohort; it retains its assigned model for fresh pricing instead.

For fresh pricing, `listing_pricing_models` persists the first assignment with
listing ID, owner, model, reason and timestamp. Migration 0008 pins every existing
listing to GPT-5 once; listings created afterward are assigned the configured new
model on their first fresh pricing request. Atomic first-writer assignment handles
concurrent jobs. Retries, photo/condition changes and explicit reanalysis do not
change the assignment. Provider failures do not silently switch cohorts. The model
is selected on a per-request profiler copy rather than mutating the shared profiler.
Pricing repair and the New-from-Like-New follow-up use that same model. Gemini
identification and the existing OpenAI label-OCR fallback model remain unchanged.
Saved profiles record `_workflow.pricing_model_assignment` for auditability.

Unscoped/standalone analysis retains the base configured GPT-5 model; sticky routing
requires a real listing and validated owner. The application feature flag defaults
off, but local and production configurations explicitly enable routing. This rollout
does not reprice existing listings,
enable controlled research, or promise identical results between model cohorts.

### Saved identity for the same listing

If fresh pricing is needed, an existing identity can be reused for **that listing
and owner** while its evidence/context is unchanged.

The identity key includes listing, owner, all original-photo hashes, category,
explicit brand correction, Gemini model and identity-policy version. Size, condition,
photo order, filenames and generated descriptions do not change the identity key.

Only recognizable brand/model results with model/profile confidence of at least
70% are persisted. The correction deployed in release `55c105a` (workflow
`39192241451`) also permits model confidence of at
least 50% when overall identity confidence is at least 90% and OCR directly reads
the same full brand name at at least 85% confidence. Reported model confidence is
not raised. Missing-brand recovery can use a corroborating full-label batch OCR
result instead of logo-only selected OCR; conflicting OCR brands are not combined.
Condition-only changes reuse this identity and rerun pricing, not identification.
Weak/unknown identities are not made permanent. Eligible prior
evidence can initialize the listing's own identity record, including a separately
validated complete-analysis reuse. A listing does not directly look up another
listing's persisted identity record.

Saved identity contains product evidence, not old valuation fields. It lets pricing
run with current condition/context without asking Gemini to identify again. New
photos or explicit category/brand corrections require a new identity context.

## 7. Identify the product with Gemini when needed

If neither an eligible complete analysis nor a saved identity is available, the
preferred hybrid path performs identification:

1. **Read labels.** Gemini OCR extracts brand/model/label text; OpenAI OCR can help
   when Gemini does not establish a brand.
2. **Research identity.** Gemini receives original-image and text evidence, including
   label context, and uses grounded search to research the product.
3. **Structure results.** A separate Gemini formatting call converts the result to
   the required JSON fields without search tools.
4. **Normalize the profile.** Application code normalizes product names, categories,
   confidence, visual condition, references and other structured fields.
   Local parser correction: rationale price-range reconciliation requires currency,
   normalizes Unicode dashes and excludes URLs, so sizes, day ranges and product
   IDs cannot overwrite a valid numeric estimate as if they were price ranges.
5. **Persist eligible identity.** A sufficiently identifiable result is saved for
   the listing so later pricing can reuse it.

The profile may include brand/model, visible distinguishing features, product
attributes, listing description, visual condition, authenticity screening, expected
documents and shipping characteristics. Category can be reconciled from this profile.

User condition remains authoritative for pricing. Visual condition is separate
evidence, not an automatic replacement for the user's selection. When condition is
not supplied to direct analysis, it defaults to Like New with a warning.

Authenticity screening is not certification. Missing supporting documents for an
applicable brand can generate warnings or an authenticity-receipt photo request.

## 8. Research and estimate value with OpenAI

### Approved sources (deployed and enforced in production)

Production release `9bbe8f5` includes policy `same-brand-comparables-v5`, with
search-domain restrictions and server-side source-role validation for both GPT-5
and Sol. Application-controlled research remains disabled locally and in production;
the active pricing model searches these approved sources itself.

OpenAI Responses `web_search.filters.allowed_domains` limits pricing research to
The RealReal, Poshmark, Vestiaire Collective, Rebag, Depop, Vinted and eBay, plus
the official website registered for the brand identified by image analysis. These
are the seven distinct websites supplied by the user. Explicit regional domains
are included; see `apps/api/app/pricing_sources.py` for the complete versioned list.
Subdomains are accepted, but lookalike domains, userinfo URLs, non-HTTPS URLs and
nonstandard ports are rejected by server-side hostname validation. A claimed
source label cannot authorize a URL. Prompt overrides cannot remove these checks.

The maintained brand registry uses exact normalized brand names and explicit
aliases. The model cannot invent a domain; unregistered brands get resale sources
only. Collaborations do not automatically inherit a base brand's official site.
Official sites provide identity/specifications/original retail evidence, never
resale anchors. Resale anchors must use approved resale sites. Retail estimates
without provider-retrieved references from the identified brand's registered site
are cleared independently; this does not erase supported resale pricing.

The API's combined-identification fallback is restricted to resale sites because
it does not yet have a fixed image-analysis identity to select an official site.
Gemini identification search prompts use the same resale-site names, but Google
grounding has no equivalent enforced OpenAI domain filter here; identity research
is not itself approved pricing evidence. Existing fallback/manual-review gates
still prevent unqualified pricing from bypassing the comparable policy.

The policy records its source-policy version, permitted resale domains, selected
official brand domains and accepted/rejected evidence in the saved item profile.
Old complete-analysis cache entries must be researched again under v5; scoped
photo identity can still be reused. No existing listing is automatically repriced.

Domain restrictions do not independently verify a price, condition or product
image. With the current local and production setting, research and valuation are
still one OpenAI call: **OpenAI finds the pricing comparables**, using the listing's
assigned model (GPT-5 for pre-rollout listings; Sol for new fresh analyses, retained
on reruns). Gemini's grounded search supports **product identification**, not the
selection of approved pricing comparables. The backend applies source and comparable
validation to OpenAI's result before accepting a value. Eligible complete-analysis
reuse requires no new research or pricing call.
The optional runtime path below separates them; independent page-content and
transaction verification remain unimplemented.

### Optional application-controlled research (deployed, disabled by default)

**Currently disabled in both local and production.** In this mode the backend
controls research scheduling, queries, approved-site coverage, evidence filtering
and snapshot reuse, but **OpenAI still performs the comparable searches**, using
the listing's assigned pricing model. Gemini supplies the established identity;
it is not the comparable-research provider. The subsequent OpenAI valuation call
has search disabled and receives the saved evidence set. The model still estimates
the value; the application does not calculate a weighted final price. Reusing a
snapshot reduces evidence-driven variability, not all model-output variability.

The runtime module `apps/api/app/controlled_research.py` is shared with the earlier
evaluation script. It builds an ordered plan from the established brand/model and
product-family terms, rather than hard-coded Louis Vuitton denim-jacket queries.
Each approved resale site gets one domain-filtered request; a registered official
brand site gets a separate retail-only request. These seven/eight requests run in
parallel. Each requests at most three individual product pages, first with the
model-name query then a predefined broader product-family query if needed.
Queries do not include user condition or size. Hosted search can rewrite queries:
application scheduling and domain coverage are enforced, not exact internal queries.
Requested plans, structured responses and actual provider tool metadata are saved.

The application checks retrieval provenance, source role/domain, brand, compatible
product family, positive USD price and a price-containing model-reported excerpt.
No currency conversion is performed. Conflicting duplicate price/condition facts
are excluded. Remaining records are deduplicated and ranked deterministically by
model-token overlap then canonical URL; no equal weights or price-based source
selection are imposed.

`pricing_research_snapshots` stores immutable research snapshots. Their key includes
protocol/source-policy version, requested plan, currency, condition-independent
identity and listing/owner/original-photo fingerprint. Ownership is checked before
lookup. Different listings/owners cannot accidentally share snapshots; existing
global complete-analysis reuse remains separate and unchanged. Same-listing
condition/size changes and pricing refreshes reuse eligible research. Changed
photos, brand/model identity or research policy invalidate the key. Snapshots expire
after `GPT_CONTROLLED_RESEARCH_TTL_S` (default seven days). Expiry appends a new
version, retaining the prior record. There is currently no separate manual research
refresh endpoint. Cross-worker locking avoids duplicate concurrent research.
Empty or partially failed research runs are not cached. Partial current evidence
may still be valued if defensible; coverage failures remain recorded.

Valuation uses the normal retail/condition guidance with search disabled. Its
comparable-selection schema returns only a bounded snapshot record ID plus match,
similarity and pricing-adjustment judgments. The server reconstructs URL, brand,
model, source condition, price, currency and price type from the immutable record;
the model does not reproduce these fields. Unknown/duplicate IDs or injected factual
fields fail validation. It may choose useful candidates and explain adjustments, but cannot
change observed facts, introduce
new sources or treat retail as resale. Research and final validation both check
source-title identity support. The explicit seller-title spelling “Louis Vuittion”
is recognized only for the established Louis Vuitton brand, not via broad fuzzy
matching. Every primary reference is revalidated
against the original research metadata. Official retail estimates must be backed
by a referenced frozen official price. The model still determines the target value;
the runtime does not import the experiment's weighted-mean arithmetic. Failed
validation does not fall back to independent searching or resurrect prior prices.
No resale evidence leaves the item requiring review. A New-from-Like-New pricing
retry reuses the same scoped snapshot when available.

Research receives 65% of the configured pricing time budget; valuation receives
the remaining time. Debug provenance records snapshot ID, key, creation time,
research model, reuse status, site coverage and validation errors. Evaluation captures
can additionally retain the full snapshot and valuation response. Final condition
price bands are not cached by this feature: fresh valuation from the same evidence
can still vary. This is an evidence-consistency foundation, not a deterministic
price guarantee. The feature requires a scoped listing and hybrid identification;
unscoped callers cannot silently bypass it.

The evaluation CLI, `scripts/evaluate_controlled_research.py`, schedules
one separately domain-filtered GPT-5 research request for each approved resale
website plus the registered official brand site, using application-supplied queries.
Hosted search can rewrite queries; the script records the requested plan and actual
provider tool calls. It checks URL retrieval provenance, source role, brand,
product/material, positive USD price and a model-reported excerpt containing the
price. It deduplicates and deterministically ranks candidates, records exclusions,
and sends the identical saved pool to GPT-5 and Sol with no tools. The original
experiment gives retail references zero resale weight. An optional
`--preserve-retail-guidance` mode instead preserves the production brand-tier
rules: contemporary NWT apparel uses 45–60% of original MSRP unless sold evidence
demonstrates lower, while luxury/heritage products anchor to supported secondary
evidence without a 60% MSRP cap. It removes the experiment-only blanket zero-weight
constraint, not the requirement for supported same-brand resale evidence. It records
how retail context was used, rejects unsupported exact-target MSRP claims, and
requires any weighted retail-to-resale conversion to identify supporting used
resale sources and explain the conversion. Raw MSRP cannot simply be averaged
into resale prices. Context-only retail references can still have zero weight;
neither a fixed retail share nor equal weights are forced. Model names do not
change, and this mode is evaluation-only, not deployed.
Models still choose resale weights/condition adjustments;
the application audits IDs, references and comparable price preservation. It
calculates the weighted mean and nearest-USD-25 rounding using decimal arithmetic,
and flags model estimates inconsistent with that calculation. Source
facts remain model-extracted, not independently verified page or transaction facts.
Its research planning/filtering implementation is shared with the optional runtime
path, but its two-model comparison and arithmetic audit remain evaluation-only and
do not replace the runtime comparable validator. Research can be reused locally
with `--reuse-research` without paying for another search run.
Its source-neutral valuation policy removes the older eBay-sold-only instruction
from the experimental request: supplied resale asking and sold-displayed prices
are eligible on the same terms across websites. This does not modify the runtime
prompt; original prices remain fixed and any asking-to-clearing adjustment must
be explicit.

For a deployed-pricing baseline, `scripts/evaluate_deployed_pricing_case.py`
verifies an ECS task-definition image against an explicit Git revision, extracts
that revision into an isolated temporary directory, and imports its profiler,
evidence validator, identity extractor and final value selector together. It
replays pricing with the saved Gemini identity and original category/size/condition
hints, preserving the deployed request and fresh independent search behavior.
It runs the deployed OpenAI model and a Sol model-only substitution, recording raw
and validated results separately. Unlike the shared-research experiments, it
does not add an allowlist, assessment schema, weights or rounding rule absent from
that deployed revision. It is pricing-only: no fresh identification, production
identity/cache/database operations, mannequin generation or listing writes occur.
The script stores only nonsecret ECS profiler settings; credentials stay out of
artifacts. This baseline tool is evaluation-only and not part of runtime analysis.

### Comparable matching and valuation

The following policy is deployed in release `635ec54`. Exact brand/model/variant matches are
preferred, but supported same-brand similar models are valid resale anchors. The
model compares product type, material, construction, quality tier, collaboration and
edition, explains differences and their price adjustment (or why none is justified),
and reflects inference uncertainty in its confidence/range. Brand alone is not enough;
different-brand references cannot anchor a value. Related-model estimates do not
automatically enter manual review. No supported defensible estimate still means review.
Every comparable records match evidence, condition, asking/sold-display type,
similarity basis and adjustment explanation. The server checks native provider
search titles for the actual comparable's brand/model (not the target's), or uses
the retrieved-URL/model-summary fallback described above, and records
accepted/rejected evidence. This does not independently verify the extracted price
or final payment. It tolerates catalogue/size qualifiers and partial descriptive
overlap as described above, but retains distinctive model-name and brand checks.
Collaboration-to-base-brand normalization is still a separate unresolved limitation;
this title-matching update does not change the brand equality rule.

Local evaluation tooling can capture the exact pricing request, fixed identity and
condition, full provider response (including native search metadata and usage),
pre-validation valuation and post-validation result. Capture is opt-in; production
does not save these additional artifacts. The evaluation runner checkpoints results
after each completed call in owner-readable, Git-ignored local files. Its `--replay`
mode applies the current server evidence rules to the stored pre-validation response
without API calls or loading credentials. This can test validator changes only;
it cannot simulate a new prompt, new search results or a different model response.

The separate local `scripts/evaluate_fixed_comparables.py` experiment can send a
URL-deduplicated union of captured comparables to both pricing models, with identical
identity, condition, evidence and schema and web tools disabled. It requires explicit
`--execute` for paid calls and saves full responses and an evidence hash locally.
Experimental instructions request source weights and adjusted prices and a rounded
weighted-mean estimate; this is not the production pricing algorithm or approval.
Its `--fixed-weights --ids C3,C8,C9,C10` mode uses exactly four selected resale
references at 25% each, strips prior adjustment recommendations, and requests only
per-reference adjusted prices and rationale. Code validates the source IDs and
calculates the mean, rounded to the nearest USD 25 (half-up). Missing/null source
adjustments do not permit reweighting: they leave the experiment incomplete. This
is a local evaluation mode, not a change to production valuation.

The preferred hybrid pricing request receives:

- The Gemini/saved identity and visual-condition information.
- Current user condition, size and description context.
- Pricing instructions, a strict valuation schema and a web-search tool.

This pricing-specific request contains **text and structured identification**, not
original image parts. Separate OCR/full-profile fallback requests can receive images.

The pricing instructions establish the following basis:

- Estimate patient peer-to-peer trade/resale value, targeting roughly 30–60 days,
  rather than liquidation or wholesale trade-in value.
- Prioritize relevant resale evidence, including specialist luxury resale and
  peer-to-peer marketplaces; eBay evidence should be sold listings.
- Distinguish original full retail price from markdown, clearance or outlet prices.
- Value the exact user condition. New is not Like New, and New does not receive an
  inferred tags/new-in-box/full-set premium.
- Do not adjust price for size or season.
- For contemporary NWT apparel, use 45–60% of original MSRP unless sold comparable
  evidence demonstrates a lower value; the supported-resale-evidence policy still
  prevents an unsupported MSRP-percentage fallback.
- Do not apply a blanket 60%-of-retail cap to luxury/heritage products.
- Return a primary condition-specific estimate, available condition-tier bands,
  confidence, rationale and sources.

These are research/model instructions, not a guaranteed sale price or proof that
every returned reference is a completed sale.

Application code merges valuation fields into the profile without allowing pricing
output to replace its persisted brand/model identity.

## 9. Select the final value for the user's condition

The application does not simply take the highest price or the first condition row.

### Additional pricing request for New when necessary

If a New item has neither a priced New primary estimate nor a priced New band, but
has a usable Like New band, the app makes one additional OpenAI **pricing-only** request:

- Preserve product identity.
- Use Like New as reference evidence—not as the final New price.
- Estimate a separate New value with item-specific evidence, not a fixed uplift.
- Require explicit New condition and compatible currency.
- Return no estimate if evidence is insufficient.
- Cap a resulting inferred New estimate's confidence at **20%**.

### Final value selection

The application then selects:

1. A positive primary resale estimate explicitly matching the requested condition.
2. Otherwise, a positive breakdown estimate for that exact condition.
3. Otherwise, an eligible retail-reference-derived resale estimate.
4. If still unavailable, configured market-comparable-provider fallback when enabled.
5. Otherwise, manual pricing review.

### Retail-reference calculation

```text
resale estimate = original retail reference
                × category factor
                × condition multiplier
                × applicable visual-condition adjustment
```

| Category | Factor |
| --- | --- |
| Clothes | 0.72 |
| Shoes | 0.80 |
| Handbag | 0.88 |
| Accessories | 0.75 |

User-condition multipliers are New With Tags 1.10, New 1.00 and Like New 0.90.
Other internally parsed used-condition tiers have lower multipliers. New excludes
the inferred visual tags/packaging premium. Other eligible visual adjustments can
incorporate pristine/packaging signals, capped at 1.18. This fallback has a ±15%
range and confidence capped at 35%.

The 20% cap applies specifically to New-from-LikeNew inference, not every fallback.

### Optional comparable-provider calculation

This is a separate configured valuation service, not the OpenAI web-search call.
When enabled, providers fetch comparable records and a deterministic pricing engine
evaluates them. It is disabled by default; the default provider list includes a stub,
so real-market provider configuration matters.

The saved valuation identifies its basis, selected condition, estimate, currency,
available range, confidence, retail reference and inference provenance.

## 10. Handle an item whose value cannot be determined

If no eligible value is found, the application:

1. Saves the analyzed listing for review without substituting an old price.
2. Marks pricing as pending manual review and tells the user the item needs review.
3. Creates an admin-review incident linked to the listing/item/job.
4. Finds admin-role users through Clerk and sends alerts to their verified primary
   email addresses using the configured email-delivery service.
5. Blocks publishing while manual pricing review is pending.

The user is not asked to enter a value. Owner edits cannot remove the pending-review
requirement or supply a price to bypass it. Alert delivery status is separate from
the item's need for review. Clerk supplies admin identities, not email transport.

## 11. Parallel branch: create the mannequin styling preview

This optional branch currently applies to **clothes and handbags**, when enabled.
It does not need the final valuation or pricing-generated description.

### Plan from original photos

Gemini receives up to six unique originals and identifies product type, photo views,
visible construction constraints, evidence sufficiency and ambiguities needing review.
Verified saved photo-role labels are reused when available. Label-only images inform
identity but are not garment-shape generation references.

A complete usable front and applicable visible construction evidence are required.
Flat-lay and hanger photos are acceptable. Hidden closures/interiors, exact measurements
or unknown fiber composition are not automatically mandatory for a front-view preview.
Insufficient essential visible evidence means no preview is produced from that plan.

### Generate the image

All original references inform planning and later inspection. **Only the best verified
front original is sent to image synthesis** in the current strategy.

The prompt asks for a front-facing matte white headless mannequin on a neutral studio
background, preserving visible product construction and appearance. Styling depends on type:

- **Bottoms:** add an opaque neutral supporting T-shirt without obscuring the bottom.
- **Tops/open jackets:** add appropriate supporting clothing/underlayers while preserving the listed item.
- **Dresses/jumpsuits:** preserve intentional shoulders, cutouts, straps and exposed legs.
- **Handbags:** use existing handles/straps on a simply dressed mannequin.

Supporting clothing is not part of the listed product.

### Inspect and save

Gemini compares the candidate against original photos and planned constraints.
Clothing coverage must explicitly pass. For bottoms, inadequate upper-body coverage
triggers stronger corrective instructions and, if needed, a **lower-body-only mannequin**.

Construction-fidelity differences are recorded for owner review; they are not an
unconditional rejection once clothing coverage passes. The preview is therefore
not a certified exact reconstruction.

A saved preview includes its plan, prompt, references and review result, with an
owner decision initially set to `pending`. Drafts can display it for review. If it
finishes after the listing becomes public, it is not automatically inserted into
the public gallery.

## 12. Parallel branch: clean up original-photo backgrounds

“Image staging” is optional background cleanup—not mannequin generation.

When requested and configured, the system opens/orients the original, obtains a
foreground mask using segmentation such as Photoroom or configured rembg, composites
the **original product pixels** over white, and saves a linked display variant.

This path does not use generative replacement to redesign the product. Gallery data
keeps original (`p_img`) and display (`d_img`) images separate. Photo order and hero
selection are preserved. Disabled/unavailable providers can leave originals unchanged;
a cleaned version is not required for listing review.

## 13. Assemble the listing for owner review

Results from each branch are saved independently. The item/pricing branch supplies
title, brand/category/model, description, user condition/size, selected value,
detailed analysis, warnings and any manual-review requirement.

Owner-authored descriptions are retained where appropriate. Image branches attach
their own assets without replacing pricing or unrelated user edits. Results from
an obsolete photo set or superseded run are not attached to the updated listing.

The owner can inspect/zoom through photos, review generated previews and correct
listing details. Brand corrections are carried into analysis as user corrections.
Changed photos are new evidence. By default, explicit pricing refresh requests fresh
research while preserving eligible identity. When controlled research is enabled,
pricing refresh instead revalues eligible saved evidence; only expiry or changed
photo/identity/policy inputs starts new research.

## 14. Publish to Marketplace

The owner chooses whether to publish. Pending manual pricing review must first be
resolved. If generated mannequin assets exist without an owner decision, the owner
must choose whether to include or exclude them.

Included previews can appear in Marketplace; excluded previews stay out of the public
gallery. This disclaimer is associated with the **AI mannequin image**, not every original:

> AI-generated styling preview. Garment details, fit, and color may differ from the actual item. Refer to the original photos for accuracy. Additional styling items are not included.

The published value can be used for marketplace/trade matching. Matching also applies
viewer preferences, including the relevant category's size preferences. Matching is
downstream of analysis; it is not another calculation of the item's price.

## 15. Model and information handoffs

| Task | Default model/service | Receives | Returns |
| --- | --- | --- | --- |
| Initial coverage | Gemini `gemini-3.8-flash` | Supplied photos | Category and photo roles |
| Label reading | Gemini; OpenAI OCR fallback | Original-photo evidence | Label text and brand evidence |
| Identification | Gemini `gemini-3.8-flash` | Originals, labels, user context and grounded search | Structured identity/profile |
| Comparable research and hybrid valuation (current active path) | Assigned OpenAI model: `gpt-5` for existing cohort; `gpt-6.1-sol` for new fresh cohort | Structured identity/current facts and approved-domain web search; no image parts in this call | Pricing comparables, retail/resale estimates, bands and references |
| Application-controlled research (disabled locally and in production) | Backend orchestration + assigned OpenAI model | Established identity and application-planned approved-site queries | Filtered, persisted comparable snapshot; subsequent valuation cannot search |
| New-from-LikeNew inference | Same assigned OpenAI pricing model | Existing identity and LikeNew reference band | Separate New estimate or no estimate |
| Mannequin planning/review | Gemini `gemini-3.8-flash` | Originals and, for review, candidate image | Plan, coverage and fidelity assessment |
| Mannequin synthesis | Gemini `gemini-3-pro-image` | Best front original and styling prompt | Preview image |
| Photo cleanup | Configured segmentation service | Original image | Original-pixel white-background variant |
| Listing chat | OpenAI `gpt-5-mini` | Conversation and workflow state | Structured action and response |

The configured default provider order retains hybrid/Gemini/OpenAI alternatives.
With the new database-backed hybrid identity path, pricing failure preserves identity
rather than silently identifying again to obtain a price. Other configurations and
standalone analysis can follow the legacy provider waterfall. Not every historical
result should therefore be assumed to have used the preferred sequence.

## 16. Chatbot entry into this process

### Existing path (default)

Listing chat collects evidence and item facts, helps create the listing, presents
analysis results, accepts corrections and helps publish with user confirmation.
Its structured actions are executed by application code through listing APIs.

Chat is not a separate pricing authority and does not replace the analysis above.
Marketplace search, finding tradeable matches and preparing a trade are later
actions using the resulting listings.

### Tool-using listing agent (implemented locally, disabled by default)

The opt-in agent uses the configured chat model with strict function tools. Its
server-owned loop executes a permitted tool, persists the real outcome and feeds
that outcome back to the model to choose a next tool/question. It pauses for human
input, exact-summary approval, or background analysis rather than keeping an
unbounded request alive. Default limits are six model/tool steps, 1,800 output
tokens per model call, and 90 seconds per turn.

Local recovery update (not deployed to production): repeated identical tool calls
without a changed photo/fact/evidence/draft/job snapshot stop early. When this
happens or the six-step model budget runs out, bounded server recovery checks
coverage if needed and presents the next required photo/fact question or summary
confirmation. If the exact summary was already approved, it can finish creating
the private draft and starting the same guarded analysis job. It does not add an
unbounded model loop, bypass approval, waive missing views, or change evaluation.
Recovery stays within the turn deadline and logs model-step count and reason.
Photo questions explicitly distinguish required views from optional recommended
views. Once required coverage is complete, server question handling moves to
missing category/condition/size or confirmation instead of requesting recommended
photos or waivers. Claiming an upload in text does not change saved evidence. Web/mobile show
selected-but-not-uploaded photos, require uploading them before a text reply, and
clear that selection once upload succeeds, even if the subsequent model turn fails.

Agent uploads add unique originals to the saved set by content hash, up to six
total; they never silently replace existing photos. Duplicate-only uploads leave
coverage and approval intact. Web/mobile show saved thumbnails and explicit remove
controls before draft creation. Removal detaches one owned session photo (not a
storage-object deletion) through a revision-checked, request-idempotent endpoint.
Actual additions/removals invalidate coverage, waivers, approval and photo-inferred
category, then clients request reassessment. Once a draft exists, image changes
continue through the ordinary listing editor. These changes are local only.

Clear standalone answers to the active, version-current category/condition/size
question are recorded through the same validated fact tool using the exact user
message as evidence, then advance directly to the next question or confirmation
without a model call. This prevents a model-generated evidence-quote mismatch
from losing an answer such as `New`. Only explicit recognized condition/category
choices and allowed category sizes qualify; ambiguous answers still use the model. It does not infer facts
from images, change evidence validation, or authorize creation/analysis without
the confirmation control. This intake fix is local only.

Size validation is category-specific and matches the web listing form's allowed
options. For shoes, `10` is not valid; `US 10` is a valid explicit selection.
The agent receives the allowed list, shows it when asking size, and rejects
unsupported values on both direct and model-proposed paths. Model-proposed sizes
must also appear explicitly in the user message; no inferred US/EU conversion is
permitted. Confirmation, draft creation and analysis start reject an invalid saved
size. Invalid historical values are not added to form dropdowns or silently fixed.

Explicit migration `0009_listing_agent_sessions` creates owner-scoped session,
request-replay and tool-ledger records. Dedicated DB connections, cross-process
session locks and revision checks prevent concurrent turns from silently
overwriting state. Replaying a request with changed input is rejected. Draft and
job IDs are deterministic per session. A 60-second dispatch lease permits queued
job recovery without dispatching on every poll; existing worker locks deduplicate
concurrent deliveries. No schema changes happen inside tools.

The agent receives uploaded originals bound to its owner/session; client-supplied
workflow stage, photo-role assertions, owner/listing IDs or approval booleans are
not accepted. It invokes the existing coverage service and records facts proposed
from user messages. Confirmation shows those facts and any explicitly unavailable
views; the confirmation control is bound to the current photo/fact/evidence
snapshot. Changing photos invalidates coverage, waivers, approval and any old
photo-inferred category. Coverage timeout skips only the initial check: category
still must be supplied, and full item/pricing analysis still runs.

After approval, shared validated listing creation produces one private draft and
the existing analysis worker pipeline runs unchanged, including subscription and
ownership checks, identity/reuse rules, sticky GPT/Sol assignment, source policy,
manual review and optional parallel imagery. The agent does not invent prices.
Returning/polling reads the actual job and saved listing without another chat-model
call. Missing valuation is shown as needs-review. The local review/publication extension shows current listing details,
value and saved gallery in chat, plus synthetic previews with the AI disclaimer.
When generated assets exist, the user must choose include/exclude explicitly.

Publication requires a separate “Confirm and publish to Marketplace” action with
a `publication_token` bound to the current listing snapshot and successful job.
Analysis approval and chat prose cannot authorize it. The guarded publication tool
rechecks ownership, current successful analysis, category-valid size, positive
valuation and pending pricing review, then uses the normal listing update path
for subscription, mannequin review, gallery normalization, rejection feedback and
publication-email handling. Atomic optional `expected_updated_at` and latest-job
write checks reject a concurrent listing edit or reanalysis; ordinary updates
without these conditions are unchanged.
Request replay and a persisted publication approval permit post-write recovery
without duplicate publication. A successful session becomes `published` and shows
the real Active listing. Manual review blocks publishing; users are not asked to
set a value. Corrections require a fresh review snapshot.
This extension is local only; production and evaluation/model routing are unchanged.
The agent cannot complete trades or charge payments and does not proactively resume a model conversation after
job completion; review cards/status are projected from actual saved state.

Local existing-listing entry: the general assistant's `review_listing` intent
resolves an owned listing by ID/title or numbered closet results and returns a
`review_listing_id` handoff. Both clients explicitly open that listing's owner-scoped
review session; they do not reuse an unrelated last conversation. With this feature
enabled, general-chat publication requests also enter this review boundary.
Review lookup ignores command words such as “review” when matching titles.
Ambiguous targets show actual candidate cards for selection. An unmatched title
shows recent owned drafts, or a clear no-listing message if none exist; the user is
never asked to choose from empty results. Opening review never creates another listing
or analysis job. Saved legacy analysis without a job may be reviewed as persisted
analysis; missing analysis cannot authorize publication.

Local shared context/capability layer: both model paths receive the same Jouft
capability guide covering Closet, Marketplace, listing analysis, images, trades,
shipping, profile and notifications, including unsupported-operation limits.
Listing chat exports its source listing, displayed result IDs/domain, focused item,
session ID, stage and pending-operation type to general chat on web/mobile. It does
not export approval tokens/signatures. General chat owner-checks session metadata
and rechecks referenced record visibility; private other-owner IDs cannot reveal
details/photos. Handoffs clear old general pending-action approvals.

The source owned item and focused Marketplace target are separate. General chat
uses `view_photos` / `view_item`, and the listing agent uses read-only
`view_listing_photos` / `view_listing_details`. A request for an already displayed
matched item's photos cannot reverse the matching direction; an ambiguous group
requires selection. Available photo reads return a gallery action to the existing
full-screen viewer; transient request IDs prevent duplicate opens/reopening on
ordinary session reload. Reads preserve price/analysis and do not grant publication
or trade permission. General own-item matching delegates to the same matching
service as listing chat. This is a shared context contract, not a merger of the
general structured router/client transcript with the persisted listing-tool loop.

Before publication, users describe corrections in chat; there is no embedded edit
form. The `propose_listing_changes` tool validates user-quoted fields and saves an
explicit change/update/set/correct/replace request directly, without a second Save
step. Questions/hypotheticals, unsaved photo changes and unrelated older staged
fields are not implicitly approved. Invalid sizes remain rejected. An invalid saved
size prompts for a correction here in chat, with allowed sizes and a “Change size
to …” example, not a redirect to My Closet. Size-only corrections retain value.
Older/staged
proposals can be resolved by typing “Save changes” or “Discard changes”; the
server binds saving to the current proposal, revision and owner, not publication.
The local review UI collapses photo management, descriptions and prior conversation
by default, keeping the current saved summary and change action visible. Proposals
show saved-to-proposed values with message-based save/discard instructions. Publication is
shown only when the review is publishable and no proposal is outstanding. Chat
replies with an outstanding proposal give the same save/cancel instruction rather
than another confirmation question. Saving remains distinct from publication.
Legacy `apply_listing_changes` controls still require proposal-bound approval.
Title/description/size-only corrections retain the saved value and analysis;
brand/category/condition or confirmed photo changes queue ordinary reanalysis.
This size-only preservation rule is scoped to agent corrections; ordinary listing
creation/evaluation is unchanged. Clear correction requests never authorize publication.
The existing model assignment, identity/reuse and condition-specific pricing rules
remain in force. No price/admin fields can be edited through these tools.

Review photo uploads/removals are staged until the changes are confirmed. They do
not immediately alter saved listing images. Pending corrections merge and are
shown again after photo changes; publication is blocked until changes are confirmed
or explicitly discarded. Keep as draft never publishes or silently saves unsaved
changes. Cancel/discard restores staged photos without editing the saved listing.
Every confirmed edit invalidates publication approval; snapshot/latest-job/write
checks reject stale edits. A fresh review is required after reanalysis. My Closet
remains an alternative editor. These handoff and correction changes are local only.

Explicit chat create intents start a new session using a stable per-intent request
ID, rather than resuming the prior listing conversation. Retries/remounts reuse
that ID, and old drafts/listings are not modified. Review still opens its selected
listing, while ordinary resume can return to saved progress (local implementation).
Current condition questions offer New with tags, New and Like new as quick-reply
buttons in web/mobile chat. A choice sends the same validated message as typing;
it does not bypass evidence, analysis or publication approval. Typed replies remain
available, and quick replies are disabled while busy or photos await upload.

After explicit publication, chat supports the read-only `find_marketplace_matches`
tool, via natural messages or Find matching items / Refresh matches. It delegates
to the existing closet-to-Marketplace matching service: the source must be owned
and Active, targets must be other-owner Active items with positive values, the
existing target-value tolerance applies, and targets must fit the viewer's saved
category and category-specific size preferences. Already-sent offer pairs are
excluded. Cross-category matches use the target category's sizes, not the source's.
Web/mobile display up to 12 real results with total/empty-state information and
item-detail navigation. Clicking a match photo opens the existing full-screen image
viewer/carousel without leaving chat, using original URLs and the thumbnail image
first; duplicate photo URLs are removed. Refresh/reopen rechecks current availability/preferences;
historical message text is not authoritative availability. A private draft gets a
publication prerequisite, never automatic publication. Matching does not create
offers or trades. This extension is local only; regular matching logic is unchanged.

Final chat step (local only): selecting Request trade or asking for a specific
matched item invokes `prepare_trade_request`, which verifies the owned published
source and a currently displayed eligible match. It shows both items, sizes,
conditions and values. A distinct `trade_token` confirmation control is required
for `send_trade_request`; model calls, ordinary chat prose and publication approval
cannot send. Cancel trade request discards only this unsent preparation. Match
cards are hidden during confirmation so the two-item summary is the current action.
Before sending, source/target snapshots and current preferences/match eligibility
are rechecked; changed/removed/own/out-of-band targets require a fresh selection.
The normal offer path still checks entitlement, ownership, Active statuses, values
and duplicate requests, stores normal shipping-profile context and notifies the
other member. It creates a standard pending offer of this source item (sender-side
agreement follows existing offer semantics), not final acceptance or a payment.
The server assigns a stable internal offer ID per approved proposal so a lost
response can recover the exact committed offer without duplicate insertion or
notification. Ordinary public offer requests do not expose this internal ID input.
Chat shows success and Trade Inbox guidance; no accept, cancel-sent-offer, shipping
purchase or payment tools are added. Normal listing creation/evaluation is unchanged.

`LISTING_AGENT_ENABLED` on the API, `VITE_LISTING_AGENT_ENABLED` for web and
`EXPO_PUBLIC_LISTING_AGENT_ENABLED` for mobile are default-off opt-ins. Both client
and server flags must be enabled for the relevant pilot client. Local API/web/Expo
opt-ins were enabled October 19, 2026, using the local backend. The standard form
retains its existing creation and evaluation path, covered with the agent flag
both on and off; local activation does not change pricing models or reuse rules.
No production
activation or paid evaluation has been performed. See
`docs/CHATBOT_AGENT_PLAN.md` for endpoints, implementation limits and release gates.

## 17. User-facing outcomes when a stage does not finish

| Stage | Outcome |
| --- | --- |
| Initial coverage unavailable | Keep photos, obtain category if needed, continue to full analysis |
| Current originals cannot all be read | Do not analyze a misleading partial photo set |
| Pricing completes | Listing available for review even if optional images are still processing |
| No determinable value | Manual review required; do not ask the user to invent a price |
| Full analysis fails | Listing remains saved with analysis-failure/retry handling |
| Mannequin unavailable or insufficient evidence | Use originals; a mannequin is optional |
| Cleanup unavailable | Keep original display images |

Operational timeout/retry mechanics are documented separately in
[execution and consistency notes](analysis-reliability.md).

## 18. Records and implementation entry points

A **listing** is the owner-facing product record. An **analysis job** is one run.
Analysis **item IDs** and **image IDs** identify evidence/results; a rerun can create
a new item ID without creating a new listing. Historical associations retain the
relationship between results, listing and owner.

Stored data includes original images/hashes, photo roles, input facts, product
profile, valuation/references, listing-scoped identity, generated/display assets and
owner image decisions. Complete-analysis reuse copies eligible evidence, not ownership
or publication state.

Primary source locations:

- `apps/api/app/main.py`: photo checking/uploads, listing APIs, direct analysis,
  value selection, manual review, generation and cleanup helpers.
- `apps/api/app/gpt_item_profile.py`: identification/OCR, research, pricing prompts and structured profiles.
- `apps/api/app/product_identity.py`: listing-scoped identification reuse.
- `apps/api/app/pricing_models.py`: persistent pricing-model cohorts and ownership checks.
- `apps/api/app/controlled_research.py`: optional scheduled research, evidence filtering and scoped snapshots.
- `apps/api/app/listing_pipeline.py`: input assembly and the three parallel branches.
- `apps/api/app/mannequin_fidelity.py`: planning, clothing coverage and fidelity review.
- `apps/api/app/pipeline_results.py`: attach component results to the listing.
- `packages/valuation/src/valuation`: optional comparable-provider valuation.
- `apps/web/src/App.jsx`, `apps/mobile/App.js`: creation, review and publication UX.

Main API handoffs:

- `POST /v1/images/classify-roles`: coverage/category.
- `POST /v1/uploads/images`, or presign/confirm under that path: store originals.
- `POST /v1/listings`: create the listing.
- `POST /v1/listings/{listing_id}/analysis-jobs`: request analysis; the local code
  accepts `refresh_pricing=true` to request fresh pricing.
- Owner job-status endpoints and `GET /v1/listings?mine=true`: progress/results.
- Listing update API: owner corrections, image decisions and publication status.
- `POST /v1/analyze`: direct item analysis only; it does not by itself orchestrate
  mannequin generation, cleanup and publication.
