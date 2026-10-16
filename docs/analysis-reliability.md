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

## Proposed next consistency layer (not implemented)

1. Compute a versioned input fingerprint from all original-photo hashes and the actual supplied inputs (condition, size, category, brand corrections and description). Include model/provider, prompt/schema and pricing-policy versions. Ignore generated/staged images. Never reuse when original photos or relevant user facts change.
2. Persist one canonical successful result for that fingerprint in the shared database. Use an atomic single-flight claim so independent workers do not produce competing canonical results. Do not promote failed/incomplete results; preserve the pricing-review state for genuinely unresolved values.
3. Separate stable reanalysis from explicit market-price refresh. Stable reanalysis returns the saved result. A refresh creates a new version with a new evidence snapshot rather than silently replacing a prior estimate.
4. Persist product identification, comparable sources/prices/condition, retrieval time, exclusions and the pricing calculation. Compute the final value deterministically from that fixed evidence and policy where possible.
5. Test across workers/restarts, simultaneous requests, reordered images, changed conditions/photos, explicit refreshes and model/policy upgrades. Measure title, comparison-set and valuation differences separately.

This guarantees stable reuse for the same versioned inputs; it does not claim that unrelated fresh model calls or genuinely new market evidence must produce identical estimates.
