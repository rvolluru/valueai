# Listing analysis: technical review notes

Reviewed October 16, 2026 against release `51bb1bd` and its application sources.
The identity-registry changes described below are local, not yet deployed.
This describes implemented behavior, not a proposed agent architecture. Model names
and flags below are repository defaults unless explicitly marked as deployment settings.
No new model requests, listing reanalyses, or production mutations were made for this review.

## 1. Executive summary

Jouft uses an application-controlled AI workflow. Gemini normally identifies the
product; OpenAI normally researches its resale value. Separate Gemini calls plan,
generate, and inspect an optional mannequin preview. Background cleanup is another,
independent operation and does not generate the mannequin.

After original photos have been resolved and snapshotted, three components run in
parallel. A listing becomes reviewable when pricing finishes; it does not wait for
either image component. The owner controls publishing and inclusion of generated
previews. A missing price triggers manual-review handling, not a request for the
owner to invent a value.

```text
Upload/select original photos
    → Initial category + photo-coverage check (Gemini; separate from valuation)
    → User supplies category, condition and size; listing/job created
    → SQS worker in production / background task when no queue is configured
    → Freeze original URLs + content hashes + listing/user-input snapshot
        ├─ Pricing: cache/reuse OR identification → research → condition-aligned value
        ├─ Mannequin: visual planning → front-photo synthesis → coverage/fidelity review
        └─ Cleanup: original-photo segmentation → original-pixel white composite
    → Independently merge each result if the job/photos are still current
    → Owner review → publish, subject to pricing/mannequin decisions
```

The branches share one queued job; they are not three separately queued services.
Each branch has its own persisted component status and result checkpoint.

## 2. Original photos and the initial coverage check

The app accepts up to six images. Mobile camera capture, library uploads, direct
multipart uploads, and presigned uploads eventually provide stored originals.
Images have storage records, IDs, role hints and content hashes. Orientation is
normalized where needed; originals, not AI previews, are used for analysis.

`POST /v1/images/classify-roles` sends the supplied images to Gemini to identify
category and photographic roles. It explicitly does **not** identify, authenticate,
or value the item. A photo can have a primary role and additional roles.

| Category | Required coverage | Recommended coverage |
| --- | --- | --- |
| Clothes | Full front, brand label | Full back, size/material label, condition/wear |
| Shoes | Side/profile, brand label, sole | Size/material label, condition/wear |
| Handbag | Full front, brand label, interior | Full back, hardware/detail, condition/wear, serial/authentication mark |
| Accessories | Full front, brand label | Size/material label, hardware/detail, condition/wear |

This is an upload-quality check, not proof of authenticity or a guarantee that
enough construction detail exists for mannequin generation.

The initial check has a 30-second HTTP timeout. Timeouts log
`image_role_classification_timeout` with duration, actor and image count; the API
returns 504. Other checking failures return 503. The UI can continue without this
check, but must obtain a category from the user if detection did not finish. Full
item/pricing analysis still runs. This bypass does not skip later analysis.

## 3. Creating and dispatching the analysis job

Listing creation/editing and explicit analysis endpoints create a
`listing_analysis_jobs` record linked to listing ID and owner subject. The listing
uses `Analyzing` while work is pending. Owner/admin reruns create a new job ID.
Brand corrections are carried into the pricing prompt as authoritative user input.
Photo-change edit paths request fresh analysis rather than ordinary database reuse.

Production enqueueing uses SQS messages containing job/listing/owner IDs and input
hints, not photo bytes. Without an SQS URL, a FastAPI background task runs the same
pipeline. The explicit multipart analysis-job endpoint also supports supplied files.

The worker verifies the schema at startup, receives one message at a time, and
renews its visibility lease while processing. Default visibility is 600 seconds;
renewal is immediate and then at most 60 seconds apart. Failed/busy deliveries are
not acknowledged. Completed processing deletes the message—even if an individual
component has reached its terminal `failed` state after its own retry policy.

Before execution, a database session advisory lock serializes deliveries of the
same job; local SQLite uses a file lock. Job/owner/listing relationships are checked.
Completed pricing cannot be reset by a late timeout. A saved listing checkpoint
can recover a crash between committing the result and recording job success.

## 4. Frozen inputs and independent components

At first execution the pipeline persists an input snapshot in
`listing_pipeline_components`: original-photo URLs, exact byte hashes, listing
baseline and user-input hints. Generated images are excluded. On resume, original
bytes must still match those hashes; the pipeline refuses to substitute other photos.
The snapshot is taken at worker execution, not at the instant the queue message is sent.

Three threads execute pricing, mannequin and staging with separate database
connections. Each component records `queued`, `running`, `retrying`, `succeeded`,
`failed`, `skipped` or `superseded`. Disabled/inapplicable image components are skipped.

The worker holds its SQS lease until all branches finish. However, pricing updates
the listing and marks the main analysis job succeeded as soon as its result is saved.
The owner job endpoints expose component states, and web/mobile Closet polling
continues while optional image components remain queued/running/retrying.

## 5. Product identification and pricing

### 5.1 Reuse before new model calls

The database reuse path looks for a recent analysis matching original image hashes.
Full-analysis reuse is allowed across listings and owners when the complete set
of actual photo-content hashes and condition/category match, with compatible
explicit brand corrections and supplied description context. A source-item pointer
alone is insufficient. Candidate hashes are captured per analysis; images added
to that item later do not retroactively change what its analysis saw. Missing,
extra or changed photos cannot match, and partial/unreadable photo sets fail closed.
It additionally requires an identifiable brand/model, brand confidence at least 0.7,
matching normalized user condition, and a usable condition-aligned valuation.
It revalidates valuation rather than blindly copying an old selected price.
Photo-change/forced-fresh and brand-override paths bypass this database reuse.
Reused evidence does not transfer ownership of the source analysis's item.

The profiler also has a separate **process-local memory cache**, keyed by image
bytes and input facts. It is not shared across workers or durable across restarts.
Bypassing database reuse does not itself clear this memory cache.

**Local implementation update:** the database-backed default hybrid path now uses
a separate shared, versioned identity registry **scoped to listing ID and owner**.
Those IDs, all original-photo hashes, category, brand correction and model/policy
version form its key. Storage lookups separately enforce the listing/owner and
validate ownership. A listing never looks up another listing's identity record;
validated global full-analysis reuse can seed its own separate record with the same evidence.
Condition, size, photo order
and generated description do not. Concurrent jobs identify once; recognizable
brand/model results with confidence at least 0.7 persist across workers/restarts.
Exact-hash-verified legacy results with this listing/owner's job history can seed it; conflicting seeds cannot
replace the canonical identity. Pricing refresh bypasses the whole-profile memory
cache and uses the saved identity without its previous prices. Weak identities are
not frozen. Provider-order configurations outside this hybrid path retain the legacy
behavior described below. See [identity implementation details](analysis-reliability.md).

### 5.2 Default provider waterfall

The default provider order is `hybrid,gemini,openai`:

1. **Hybrid:** Gemini identifies the item, then OpenAI supplies valuation fields.
2. **Gemini:** another Gemini profile attempt if the preceding result/errors require fallback.
3. **OpenAI:** a full-profile fallback if earlier providers do not produce usable data.

Partial profiles can survive when no provider returns a fully usable result. Thus
“pricing is OpenAI” describes the preferred path, not every possible result.

| Purpose | Repository default |
| --- | --- |
| Coverage, identification, mannequin planning/review | Gemini `gemini-3.8-flash` |
| Hybrid valuation and OpenAI fallback | OpenAI `gpt-5` |
| Mannequin image synthesis | Gemini `gemini-3-pro-image` |
| Listing-chat orchestration | OpenAI `gpt-5-mini` |

Environment overrides can change these. Class names such as `GptItemProfiler`,
debug labels such as `gpt_primary`, and retained older classifier settings are not
reliable evidence of which provider actually produced a particular response.
The direct analysis route does not invoke the older trained brand/condition pipelines.

Within Gemini identification:

- Label OCR attempts Gemini first, with OpenAI OCR fallback when needed.
- Label context is added to the image/text input.
- A Gemini grounded-search call researches product identity and evidence.
- A second Gemini call formats the result as structured JSON, without search tools.
- Grounding sources, OCR output and workflow diagnostics accompany the profile.
- Repair/normalization logic can recover missing structured facts from grounded text.

The profile includes brand/model, category, visual features, visual condition,
pricing/reference data, authenticity-document expectations and shipping information.
The API may reconcile category/brand from this profile. This is evidence-based
screening, **not a guarantee of authentication**.

### 5.3 What OpenAI receives in the hybrid pricing call

The hybrid valuation request includes text input context and structured Gemini
identity/visual-condition information. It does **not** forward the image parts in
this pricing-specific request. OpenAI has a web-search tool and a strict valuation
JSON schema. Separate OpenAI OCR/full-profile fallback calls can receive images.

The pricing prompt targets patient peer-to-peer trading value over roughly 30–60
days, rather than liquidation value. It prioritizes resale evidence, requests
original full retail price rather than markdowns, and says not to adjust value for
size or season. Luxury resale can be above retail; contemporary-apparel prompt
guidance is different. Source priorities are prompt instructions, not proof that
every returned comparable was independently verified as a completed sale.

### 5.4 Condition alignment and the final value

User-selected condition is authoritative for pricing. The public normalized inputs
are `NewWithTags`, `New`, and `LikeNew`; internal price parsing also understands
additional used-condition tiers. With no user condition, the API defaults to LikeNew
and emits a warning. The API's top-level condition is therefore not an independent
visual condition reassessment; visual observations live inside the item profile.

Final selection follows this order:

1. Use a positive primary resale estimate only when its declared condition matches.
2. Otherwise select a positive breakdown row for that exact condition.
3. For **New**, if no priced New estimate exists but a priced LikeNew row does,
   make one OpenAI pricing-only request to derive a separate New estimate. Preserve
   identity, require explicit New condition and matching currency, and cap its
   confidence at **20%**. There is no fixed uplift; insufficient evidence can return null.
4. If no usable resale price exists but a retail reference exists, a deterministic
   retail-derived fallback remains available.
5. If still unavailable, configured comparable-provider fallback may run. Otherwise
   the listing pipeline records value zero and requests manual pricing review.

Comparable-provider fallback is disabled by default (`valuation_comps_enabled=false`).
When enabled, `ValuationService` fetches configured providers concurrently and passes
their market-comparable records to the deterministic valuation engine. Provider
errors, timing and returned counts are captured. The default provider setting is
`stub`; enabling the flag alone is not equivalent to enabling real market research.

The retail-derived fallback uses retail × category factor × condition multiplier,
with optional visual-condition adjustment. Category factors are clothes 0.72,
shoes 0.80, handbag 0.88, accessories 0.75. Condition multipliers include NWT 1.10,
New 1.00 and LikeNew 0.90. New excludes an inferred tags/full-set premium and skips
the visual multiplier. The derived range is ±15%, confidence at most 35%.
The **20% cap applies to New-from-LikeNew inference, not all fallback prices**.

The response records value, currency, available range, confidence, pricing basis,
selected condition/band, retail reference and inference provenance. A nonzero
value is not itself evidence of strong confidence. `comps_summary.count=1` on the
profile-derived path is an application summary, not a count of verified sold comps.

## 6. When no value can be determined

The listing remains reviewable with a `pricing_review.status=pending` marker and a
message that it needs manual review. The old price is not used to disguise failure.
The owner is not asked to set the value, and pending pricing review blocks publishing.
Owner edits cannot clear the review marker or supply an overriding value.

The system creates a `pricing_review_required` production incident. It looks up
admin-role users through Clerk's directory using trusted public/private metadata,
then sends alerts to their verified primary email addresses via configured email
delivery. Clerk supplies recipient identity; it is not the email delivery provider.
Delivery outcomes are recorded and already-sent recipients are skipped when that
saved review record is reused. Missing directory credentials, no admins or email
failure are recorded; alert delivery is not guaranteed merely by creating an incident.

## 7. Mannequin generation: independent from pricing

This branch runs only when enabled, a Gemini key exists, and input category is
clothes or handbag. Shoes/accessories do not currently use it. It uses the originals,
not staged photos or prior generated images, and does not wait for a pricing title.

### Planning and the photo-view validator

Gemini receives up to six unique original references to determine product type,
front/back/detail/label views, visible construction constraints, sufficiency and
ambiguities. Saved photo classifications are reused when resolved from matching
stored image identity/content, rather than guessed from filenames.

The local validator requires sufficient evidence, a verified complete front first,
valid reference indices/views, nonempty construction constraints and an explicit
human-review decision. It rejects label/other-only reference selections. Ordinary
flat-lay and hanger photos are valid. Hidden closures, unseen interiors, unknown
fabric composition and inapplicable construction details are not mandatory.
Bad structured plans get up to two planning/validation attempts.

Upload coverage and mannequin planning are different checks. A coverage label such
as “full front” helps reuse the view, but does not override an insufficient-evidence
decision about essential visible construction.

### Which photos actually generate the image?

All selected original references inform planning and later fidelity review.
**Only the best verified front image is passed to image synthesis** in the current
`front_only_minimal` strategy. Labels do not drive garment shape reconstruction.
The planner's product type selects the styling prompt independently of pricing.

### Generation, clothing coverage and fidelity

The image prompt asks to preserve the listed product's visible construction, color,
fabric appearance and orientation. For bottoms it explicitly requires a supporting
opaque neutral T-shirt. If coverage fails, generation retries with stronger clothing
instructions, then falls back to a lower-body-only mannequin. These are up to three
candidate attempts **inside** a mannequin component attempt; the component itself
can retry twice. Most other products have one candidate strategy per component attempt.

Each candidate is decoded as an image and reviewed by Gemini against the originals
and plan. Clothing coverage must explicitly pass with evidence. An unavailable
review cannot pass coverage. Construction-fidelity disagreement is logged and
stored, but **is not a hard rejection once clothing coverage passes**; such a preview
can be retained for owner review with `fidelity_passed=false`.

Saved metadata includes prompt, plan, review, source hashes/references, model,
strategy, clothing attempt, display mode and `review_decision=pending`. Draft/review
galleries can show the pending preview. An image finishing after the listing is
already Active is not automatically added to its public gallery.

## 8. Background cleanup (“image staging”)

Staging means an optional presentation variant of an original image. It currently
uses Photoroom segmentation and/or configured rembg to obtain a mask, then composites
the **original product pixels** onto white. Generative background replacement is
disabled in this path for product fidelity, even though older helper/settings remain.

This branch runs only if the job requests staging and the staging flag is enabled.
It processes photos concurrently within its branch. Disabled providers, unusable
masks or no changed images can yield a skipped result. It is not guaranteed for
every rerun. The deployment workflow explicitly disables Photoroom, so configuration
must be considered before assuming that staging will produce new images.

Gallery entries retain `p_img` (original) separately from `d_img` (display variant).
Cleanup replaces only the matching display image and preserves hero/order and other
components' work. Original images remain the analysis evidence.

## 9. Saves, review and publication

Every pipeline merge locks the listing row and checks that the job is still latest
and original-photo signature unchanged. Pricing also rejects changed category,
condition or size. Superseded results are not attached to the edited listing.

Pricing writes pricing/analysis fields while preserving generated/presentation
assets and manually changed text fields relative to its baseline. Image merges
preserve pricing, user edits and other branch results. Component checkpoints allow
already-committed work to be recognized after interruption.

Pricing normally moves a draft from `Analyzing` to `Review`; successful reanalysis
can retain `Active`. Failed pricing can set `AnalysisFailed`. A succeeded job may
still have running/failed image components. Optional images do not block review.

When generated previews exist, initial publication requires the owner's include/
exclude decision. Excluded images and pending previews on active listings are kept
out of the public gallery. The AI disclaimer is shown for the generated mannequin
image, not every original:

> AI-generated styling preview. Garment details, fit, and color may differ from the actual item. Refer to the original photos for accuracy. Additional styling items are not included.

### Chatbot entry point

Listing chat collects evidence and user facts, tracks conversation/workflow state,
and helps the user review/correct/publish. Its model-driven orchestration returns
structured actions such as `create_analyze`, `update`, and `publish`; application
code and clients execute the permitted actions through listing APIs. Chat is not
an additional valuation authority and does not replace the above checks. The broader
assistant can search marketplace/matches and prepare actions, with confirmation
handling for publishing/trade requests. A chat message alone is not evidence that
the full analysis pipeline ran or a listing became public.

## 10. Timeouts and retries

| Scope | Current policy | Consequence |
| --- | --- | --- |
| Initial coverage | 30-second HTTP timeout | Log; skip only initial check; require category if unknown |
| Full pricing component | Two attempts; production configured 300 seconds per attempt | Retry pricing; then failure state/incident if unrecoverable |
| Profiler provider HTTP calls | Default 120 seconds; production workflow configures 240 | A provider may involve several sequential calls; not one overall workflow deadline |
| Mannequin component | Two attempts, 300 seconds each by default | Image failure only; pricing remains saved |
| Individual mannequin HTTP requests | 90 seconds by default | Subject to component timeout and nested candidate/planning attempts |
| Staging component | Two attempts, 120 seconds each by default | Cleanup failure only |
| Photoroom request | 20 seconds by default | Provider failure/fallback; cleanup may be skipped |
| SQS visibility | 600 seconds default, renewed periodically | Prevent normal redelivery while work continues |

The pricing wrapper's environment fallback is 180 seconds; 300 is the production
deployment configuration, not the hard-coded fallback. Timeout cancellation is not
a strict wall-clock kill: synchronous provider work already in threads can continue
until its own timeout, and executor shutdown can wait for it. A cancelled coroutine
does not subsequently perform its normal result merge.

Owner listing reads also mark stale analyzing listings/jobs after a 15-minute cutoff.
That database cleanup is separate from SQS visibility and component deadlines.

## 11. Persistence, ownership and diagnostics

| Record/data | Purpose |
| --- | --- |
| `items`, image records/storage | Original/derived bytes and image identity |
| Analysis records | Model response snapshots and debug evidence for an item |
| `listings` | Current owner, gallery, text, value, status and attached analysis |
| `listing_analysis_jobs` | Job lifecycle, attempts, result item and timestamps |
| `listing_pipeline_components` | Frozen run inputs and independent component lifecycle |
| `analysis_listing_links` | Append-only historical item → listing → owner associations |
| `listing_product_identities` | Persistent identification isolated by owner, listing and evidence fingerprint |
| Production incidents | Pricing review and analysis-failure investigation |

One listing can have several historical item/analysis IDs after reruns; a new item
ID does not necessarily mean a new listing. Uploads/standalone analysis can also
exist before a listing association is established. Historical links are preserved
going forward; backfill only uses stored relationships and cannot reconstruct all
previously overwritten associations. “No linked listing” is unresolved linkage,
not evidence that an owner never existed.

Useful endpoints:

- `POST /v1/images/classify-roles`: initial coverage/category.
- `POST /v1/uploads/images/presign`, `POST /v1/uploads/images/confirm`,
  `POST /v1/uploads/images`: presigned and direct upload paths.
- `POST /v1/listings/{id}/analysis-jobs`: explicit queued analysis.
- `GET /v1/listings/{id}/analysis-jobs/latest`, `GET /v1/analysis-jobs/{id}`: owner-scoped job/component status.
- `GET /v1/listings?mine=true`: owner listings with pending component states.
- `POST /v1/analyze`: direct item analysis; not the full three-component listing pipeline.
- `POST /v1/admin/listings/{id}/rerun-analysis`: owner-linked support rerun.
  The mannequin backfill script is a separate maintenance entry point.

Correlate job ID, listing ID, owner subject, item ID, component and SQS message ID.
Logs cover queue receive/ack, lease renewal failure, component retry, analysis timing,
coverage timeout, generation/coverage rejection, fidelity flags and pricing-review
delivery. Stored workflow diagnostics include grounding/OCR and valuation provenance.

Schema updates run as explicit versioned migrations before rollout. API/worker
startup verifies readiness; requests/jobs must not run `ALTER TABLE`. The production
gate uses the new image in a standalone migration task and blocks rollout on failure.
See [database lifecycle](DATABASE_MIGRATIONS.md).

## 12. Review findings and limitations

These are code-review findings, not fixes made by this documentation change.

1. **Repeated fresh research is not deterministic.** Shared canonical-result storage,
   frozen comparables and deterministic pricing remain proposed. Shared versioned
   **identity** and a single-flight identification claim are now implemented locally
   for the default hybrid path; this does not freeze comparable selection or pricing.
   Same-job duplication is prevented; separate explicit market refreshes can still
   return different comps/prices. See [consistency plan](analysis-reliability.md).
2. **Fallback pricing can remain weakly evidenced.** Retail-derived prices can avoid
   manual review even without condition-specific resale comps. Grounded-text retail
   recovery selects a maximum extracted price at low confidence. These paths should
   remain distinguishable from direct sold-comparable evidence.
3. **Timeouts are cooperative, not hard isolation.** Threaded synchronous provider
   requests can outlive the async timeout. Nested provider fallbacks and mannequin
   candidate retries can make real elapsed time exceed the headline budget.
4. **Mannequin error handling has a defect.** The exception handler inside
   `_generate_verified_mannequin_asset` references `raise_on_error`, which is not a
   parameter/local in that helper. Its exception path can mask the original error
   with `NameError`; the outer component still catches/retries it. This needs a
   focused fix and exception-path regression test.
5. **Fidelity is advisory after clothing coverage.** A clothed but construction-
   inaccurate preview can reach owner review. Do not describe generation as a
   guarantee that every garment detail matches the original.
6. **Retries are durable but not separately scheduled.** One worker waits for all
   components. A failed optional component is terminal for that run; redelivery
   resumes pending/interrupted work, not every exhausted failure. There is no generic
   user-facing per-component retry API in this restructuring.
7. **Some legacy/support paths differ.** Direct `/v1/analyze` has no listing-image
   pipeline, and no-job legacy helpers retain older update behavior. Optional
   Firecrawl enrichment is attached to a BackgroundTasks object; the listing worker
   calls `analyze` directly, so those tasks are not automatically executed by an
   HTTP response in that path. Do not count that enrichment as guaranteed.
8. **Connection lifecycle cleanup is incomplete.** Main component paths close their
   connections, but the pricing wrapper's retry/error bookkeeping creates additional
   Database objects without an explicit close on every exit. This merits a wider
   transaction-lifecycle audit following the runtime-migration fix.
9. **Input and alert guarantees need boundaries.** The snapshot freezes at execution,
   not enqueue. Admin-email discovery/delivery can fail and is reported separately.
   Row/photo guards prevent late attachment but do not cancel the cost of obsolete
   model work already in progress.

## 13. Code map and verification

- `apps/api/app/main.py`: coverage/uploads, listing create/edit/publish, direct analysis,
  condition selection, manual review, image generation and staging helpers.
- `apps/api/app/gpt_item_profile.py`: OCR, provider waterfall, prompts, research,
  structured parsing/normalization and memory cache.
- `apps/api/app/listing_pipeline.py`: frozen inputs, concurrent components, resume/retry.
- `apps/api/app/pipeline_results.py`: photo identity, row-locked narrow result merges.
- `apps/api/app/analysis_execution.py`: same-job lock and committed-result recovery.
- `apps/api/app/analysis_queue.py`, `analysis_worker.py`: SQS enqueue, lease and ack.
- `apps/api/app/mannequin_fidelity.py`: planning, view validation, coverage/fidelity.
- `apps/api/app/db.py`, `migrations.py`: persistence, historical links and schema lifecycle.
- `apps/mobile/App.js`, `apps/web/src/App.jsx`: creation/review UX and pending-work polling.

Relevant regression coverage includes `test_listing_pipeline.py`,
`test_analysis_execution.py`, `test_mannequin_fidelity.py`,
`test_valuation_condition_alignment.py`, `test_migrations.py` and API integration
tests. Release verification passed 308 backend tests before the migration-runner
regression was added; the runner's targeted suite also passed. This review is static
source analysis, not an assertion that every live model/error path has been exercised.
