# Analysis execution reliability and consistent reanalysis

## Implemented execution fixes

- Serialize execution of each job using a PostgreSQL session advisory lock (local SQLite uses a file lock). Duplicate deliveries cannot execute concurrently; crashed workers release the lock when their connection closes.
- Skip jobs already marked succeeded, including forced-fresh payloads redelivered for the same job ID. A deliberate new analysis must have a new job ID.
- Treat success as terminal. A late timeout/retry cannot reset it or replace its result item ID.
- Store a job checkpoint in the committed listing analysis, allowing recovery if a worker dies between saving the listing and marking the job succeeded.
- Run optional image staging outside the item/pricing analysis timeout. Staging has its own timeout and up to two attempts; failure does not invalidate committed analysis.
- Renew SQS visibility while processing, and log message ID, receive count, job ID and acknowledgment for correlation. Busy/failed deliveries are not acknowledged.
- Keep append-only item/listing/owner associations across reanalyses and use them when resolving debug owners. Old records whose associations were already overwritten need a separately verified historical repair; this does not infer owners from similar images or brands.

## Why intentional fresh analyses can still disagree

`GptItemProfiler._profile_cache` is an instance-local dictionary. The key includes image bytes, brand, category, size, condition/source and description. The dictionary is neither shared between workers nor durable across restarts. This matches the observed pattern of each worker repeating its own estimate while two workers produced different comparisons and prices.

The separate database reuse path scans only recent analyses, checks image hashes, brand/model confidence and condition, and can be bypassed for photo changes or a forced refresh. It is not an atomic, versioned canonical-result registry. Even with low sampling variability, independently researched comparison sets can differ.

## Parallel pipeline

New listing jobs persist a frozen snapshot of original-photo URLs, byte hashes and
user inputs before launching three independent components in parallel:

- Item identification/pricing: existing 300-second, two-attempt analysis policy.
- Mannequin: its own visual planning identifies garment type from originals, without
  waiting for pricing or relying on a pricing-generated title. Default total timeout
  is 300 seconds per attempt, at most two attempts.
- Background cleanup: operates on original photos, with a default 120-second timeout
  per attempt and at most two attempts. Disabled/unprocessed cleanup is skipped.

Each component has durable status, attempts and error information. Pricing success
makes the listing reviewable immediately; optional-image failures never retry or
invalidate pricing. Owner job endpoints expose component states, and both Closet
clients keep refreshing while optional components remain pending.

Components share one SQS delivery and run on separate threads/connections, not
separate queues. The delivery stays leased until all components finish. On worker
redelivery, completed components are skipped and interrupted components resume;
saved result checkpoints recover a crash between result merge and status update.
Each merge locks only the listing row, checks the latest job and photo revision,
and writes only its own fields. Pricing preserves manual text edits and other
components' assets; image branches preserve pricing, photo order and hero selection.
New previews on already-active listings remain pending owner review.

Timeouts cancel async work; synchronous provider work already dispatched to threads
can still take time to unwind under the provider's own request timeout. Its cancelled
coroutine cannot subsequently merge a result. No runtime schema migration is used.

## Consistency layers: implemented identity and proposed pricing work

### Identity reuse implemented in the current working tree

Migration `0006_listing_product_identities` adds a listing-and-owner-scoped
identification registry for the default hybrid profiler. Its fingerprint includes
listing ID, owner subject, all original-byte hashes (sorted), category, explicit
brand correction, identity policy version and Gemini model. Database keys and
queries also require the listing/owner, independently of the fingerprint. The
resolver validates the listing's current owner before any read/create. Two listings
never look up one another's persisted identity record. A separately validated
full-analysis reuse may copy evidence into the receiving listing's own record.
The earlier unscoped `product_identities` table is not read or imported.
Size, user condition, file order/names and generated descriptions do not reset
identity. New/removed/changed photos, category/brand corrections, or model/policy
changes select a new identity. A database/file lock serializes concurrent
identification across workers. Only recognizable brand/model identities with
model/profile confidence at least 0.7 are persisted; ambiguous results are not frozen.

Unchanged, previously linked analyses can seed the registry after checking exact
photo hashes, category, corrections and analysis-job history for this listing/owner.
A supplied source-item pointer alone is insufficient. Existing canonical identity wins over a
conflicting seed. Database full-result reuse is rejected when it disagrees with
the canonical brand/model. No ownership, item IDs or old valuation fields transfer
with identity. New hybrid pricing receives this identity and fresh condition/input
context, with no old price/condition-dependent listing description. Valuation output
cannot replace the saved identity fields. A pricing failure keeps identity but
does not silently re-identify or resurrect its old price.

`refresh_pricing=true` is available as a form field on the owner analysis-job
endpoint, and a query parameter on the admin rerun endpoint. It bypasses whole-result
reuse while preserving identity. Ordinary reruns can still reuse valid full results.
Identity reuse/provenance, including listing/owner scope, appears under profiler
workflow debug `identity_reuse`. Whole-analysis reuse is deliberately global,
including across owners, but requires an exact complete photo-content match,
matching condition/category, compatible explicit brand correction and description
context. It hashes current resolved bytes rather than trusting a stale source-item
pointer. Candidates use hashes captured for that analysis (legacy records resolve
its specific uploaded-image IDs), not the item's later expanded image collection.
Missing/unreadable images fail closed; photo order is irrelevant but missing,
additional or changed content cannot match. Filename/length coincidences do not
deduplicate distinct content. No owner, gallery, review state or listing-component
checkpoint is copied from the source listing. Standalone `/v1/analyze` requests
without a verified listing do not read/write persisted identity or reuse the
process-local profile cache. The scoped fallback memory-cache key also includes
listing/owner IDs.
Alternate provider orders and standalone profilers without a database retain their
legacy fallback behavior; shared identity is specifically the configured hybrid path.

There is no new user-facing refresh button or manual model-confirmation UI in this
change. Arbitrary description/title edits are not treated as identity corrections;
structured brand/category corrections and photo changes are the invalidation inputs.

### Still proposed

1. Compute a versioned input fingerprint from all original-photo hashes and the actual supplied inputs (condition, size, category, brand corrections and description). Include model/provider, prompt/schema and pricing-policy versions. Ignore generated/staged images. Never reuse when original photos or relevant user facts change.
2. Persist one canonical successful result for that fingerprint in the shared database. Use an atomic single-flight claim so independent workers do not produce competing canonical results. Do not promote failed/incomplete results; preserve the pricing-review state for genuinely unresolved values.
3. Separate stable reanalysis from explicit market-price refresh. Stable reanalysis returns the saved result. A refresh creates a new version with a new evidence snapshot rather than silently replacing a prior estimate.
4. Persist product identification, comparable sources/prices/condition, retrieval time, exclusions and the pricing calculation. Compute the final value deterministically from that fixed evidence and policy where possible.
5. Test across workers/restarts, simultaneous requests, reordered images, changed conditions/photos, explicit refreshes and model/policy upgrades. Measure title, comparison-set and valuation differences separately.

This guarantees stable reuse for the same versioned inputs; it does not claim that unrelated fresh model calls or genuinely new market evidence must produce identical estimates.
