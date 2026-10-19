# Listing chatbot: current flow and agent implementation plan

Updated October 19, 2026. First bounded implementation is now present locally,
behind default-off flags. No production rollout or paid model evaluation has been
performed for this agent. The current-flow table below describes the retained
legacy path; the new path is described in the implementation status section.

## Implemented local pilot

- `apps/api/app/listing_agent.py`: strict function tools, bounded Responses API
  execution loop, persisted questions/summary confirmation, model usage and redacted
  tool-outcome logging. The existing configured chat model is retained.
- `apps/api/app/listing_agent_routes.py`: owner-scoped sessions/owned uploads,
  validated shared listing creation, deterministic draft/job IDs, existing worker
  dispatch with a 60-second recovery lease, real analysis-state projection.
- Explicit migration `0009_listing_agent_sessions`: sessions, request replay and
  tool ledger. No request-time schema creation. Dedicated DB connections and
  cross-process session locks serialize turns, with revision checks on writes.
- Shared client controller and opt-in web/mobile components replace client-side
  action execution in both dedicated listing chat and the general assistant's
  create-listing handoff. Legacy chat remains the default.
- Human approval is an explicit confirmation control tied to the exact current
  photos, proposed facts, coverage and waived views. Saying "yes" in prose alone
  cannot grant mutation permissions. Uploaded photos are revalidated from storage
  before creation; adding/removing photos invalidates coverage/waivers/approval and
  removes an old photo-inferred category.
- Model/provider calls are stubbed in automated tests. Coverage timeout skips only
  coverage; category must still be supplied and full analysis still starts.

### Local activation (enabled October 19, 2026)

The local API, Vite and Expo opt-ins are enabled in ignored environment files.
Expo targets `http://127.0.0.1:8000` for the iOS simulator rather than production;
Android emulators require `http://10.0.2.2:8000` instead. Production remains off.
The standard listing form still uses its existing creation/evaluation path; a
regression test runs that path with the agent both enabled and disabled and checks
that no agent session is created.

Run the explicit API migration using the same environment/PYTHONPATH as the backend
(`python -m app.migrations`, or the existing backend startup script). Set
`LISTING_AGENT_ENABLED=true` for the API. Set `VITE_LISTING_AGENT_ENABLED=true`
for the web build/dev server and `EXPO_PUBLIC_LISTING_AGENT_ENABLED=true` for
Expo; restart the relevant processes. The API also exposes authenticated
`GET /v1/listing-agent/config`. No production flags or model assignments change.

### Deliberate first-version limits

The agent creates and analyzes one private draft per session, then renders real
results. Polling/returning to chat resumes job status without another model call;
it does not yet run a proactive post-analysis model conversation or push callback.
After a draft is created, corrections and publication use the existing My Closet
editor, not agent mutation tools. The new agent has no publish/trade tool. A new
session is an explicit separate draft. Pre-draft uploads add to the saved photo
set, deduplicated by content hash (up to 6 JPEG/PNG/WebP, 15 MB and 40 MP each).
Both clients show saved thumbnails and allow explicit removal before draft creation;
request IDs preserve
network-retry idempotency. Unresolved pricing is displayed as needs-review, not $0.

Live provider quality/latency, authenticated browser walkthroughs and physical
device testing remain release gates; the local pilot is not production-approved.

### Verification performed

The local migration was applied. Before activation, the full Python suite passed
(501 tests) and shared
client/web JavaScript tests passed (34 tests). The enabled web build and offline
iOS/Android JavaScript exports passed. These are automated/stubbed checks, not a
live model-quality or native-device acceptance test. Recovery tests cover lost
responses, post-insert interruption, stale revisions/confirmations, superseded
interrupted turns, session locking and re-dispatch after an expired lease.

Activation verification: the running API returned `enabled: true` and health 200;
Vite served its enabled flag and Metro loaded the local Expo overrides. All 502
Python tests and 34 JavaScript tests passed after activation. Provider calls in
these tests are stubbed; live agent quality remains to be evaluated.

## Local recovery follow-up (October 19, 2026; not deployed)

The shoe session retained three original photos and still lacked `shoe_sole` when
the member wrote “I uploaded sole photo”. No replacement upload had reached the
session. The turn reused the existing assessment, then repeatedly read context.
The original six-step limit surfaced an internal budget message to the member.

The local fix stops repeated no-progress tool calls and uses bounded domain
recovery to ask for the genuinely missing input or show confirmation. Already
approved work may finish via the existing idempotent draft/job tools. Budgets,
ownership, confirmation and normal evaluation remain unchanged. Required photo
questions now separate optional recommendations. Both clients distinguish pending
selection from saved uploads and prevent sending text instead of uploading a
selected photo set. Provider calls are stubbed in regression tests.

Verification: 509 Python tests and 39 shared-client/web JavaScript tests passed;
the web build and offline iOS JavaScript export passed. The tests cover unchanged
photo claims/context loops, actual replacement uploads and reassessment, optional
views not blocking confirmation, recovery after approval without duplicate jobs,
and a failed model turn after a successful upload. These are stubbed provider
checks, not a rerun of the member's live session.

## First delivery boundary

### Direct intake answers (local only)

A live turn answering `New` failed because the model's `record_user_facts`
evidence quote did not match the current message. The quote guard remains strict.
Recognized standalone condition/category choices and valid category size choices now go
through the same fact tool with the actual user message as evidence, but only for
the current version-bound question and before draft creation. The next required
question/confirmation is presented without a provider call. Ambiguous answers,
compound messages and other questions retain the model path. Confirmation is
still required; no prices or identities are inferred from this parser.

Size follow-up (local only): size must be in the category's existing form options.
Bare `10` is invalid for shoes, while `US 10` is valid. The direct parser and model
fact tool both enforce this; the model cannot add a prefix absent from the user's
answer. Size questions expose the full allowed list. Invalid saved sizes cannot
pass confirmation, creation or analysis start, and edit dropdowns are not expanded
to accommodate them. Existing invalid listings need an explicit valid selection.

Size validation verification: all 533 Python tests and the web build passed,
including parity with the form's category options, invalid/inferred shoe sizes,
and blocking confirmation/creation for an old invalid size.

Verification: all 527 Python tests passed, including direct answers, ambiguous
answers, replay safety, and `New` advancing to size without a model call.

### Additive photo follow-up (local only)

Uploads now append unique originals rather than replacing earlier photos. The
server enforces six total before storing additions, and duplicate-only uploads
preserve evidence and approval. Explicit removal is session/owner scoped,
revision-checked and retry-safe via `POST /v1/listing-agent/sessions/{id}/photos/remove`.
It detaches the photo from this draft; it does not delete the stored media object.
Real photo changes invalidate coverage, waivers, approval and photo-inferred
category. Clients automatically ask the agent to reassess after additions/removals.
If required coverage is complete, backend question handling asks only for missing
category/condition/size or presents confirmation, even if the model tries to ask
for optional photos or optional-view waivers. No standard listing path changes.

Verification: 515 Python tests and 40 JavaScript tests passed, plus the web build
and offline iOS JavaScript export. Added checks cover additive/deduplicated uploads,
the six-photo cap, duplicate-only evidence retention, owner/revision-scoped removal,
last-photo removal, retries and post-creation restrictions, and optional-only photo
requests advancing to facts or confirmation. Provider calls remain stubbed.

Create one owner-scoped, private, review-ready listing draft through conversation.
Publication, marketplace research/matching and trade execution remain outside the
new agent's first tool set. Keep the existing chat path available behind a feature
flag while evaluating the replacement. Retain the configured chat model initially;
this is an orchestration change, not a model migration.

## Current implementation map

| Component | Current behavior | Agent evolution |
| --- | --- | --- |
| `apps/api/app/main.py`: `app_assistant_chat` | One structured-output OpenAI call chooses one intent; Python branches perform application actions. Create intent opens the photo-first flow. | Retain as general app routing initially; hand creation to the bounded listing agent. |
| `main.py`: `listing_assistant_chat` | Loads owner-scoped persisted conversation, merges client context, asks OpenAI for field suggestions/action JSON, then invokes a deterministic orchestrator. | Replace this decision-only call with a bounded function-tool execution loop. |
| `main.py`: `_listing_chat_orchestrate` and `LISTING_CREATION_WORKFLOW` | Fixed missing-field order; stage-dependent rules and explicit photo-role waivers. | Reuse validation policies, but let the model choose among permitted tools/questions based on observed evidence. |
| `apps/api/app/db.py`: listing conversation methods | Persists conversation context/messages/stage and supports active-conversation retrieval. Message IDs provide basic duplicate-message replay. | Extend with durable runs, tool-call records, input versions, pending questions and job linkage; message replay alone is not tool idempotency. |
| `apps/api/app/schemas.py`: assistant request/response models | Client supplies photo count/roles, listing fields and workflow stage; response includes suggestions and action. | Client sends user input and attachment references; backend loads authoritative resource state and emits messages/status/cards. |
| `apps/web/src/App.jsx`, `apps/mobile/App.js` | Both execute `create_analyze`, update and publish actions and synchronize conversation stage. | Render the same server-owned run state; upload photos and submit answers without independently orchestrating tools. |
| Existing photo-role checks, listing CRUD and analysis-job APIs | Already provide evidence assessment, owner checks, validation and asynchronous analysis. | Extract/reuse service functions as narrowly scoped tools; do not bypass routes' safeguards by calling handlers without validation. |
| Identity, pricing and image-generation pipeline | Already handles Gemini identity/OCR, model cohorts, reuse, pricing rules and parallel optional imagery. | Leave these domain responsibilities in place; the agent invokes the pipeline rather than inventing identity, prices or new model routing. |

Current sequence:

    General chat -> create intent -> client photo upload/coverage check
      -> listing chat -> condition/size/category collection -> pre-analysis approval
      -> client creates draft and starts analysis -> client observes completion
      -> review corrections -> explicit publish request -> client publishes
      -> application chat for matches/trades

The two chat endpoints use Responses API structured JSON output today; neither
listing-chat request exposes function tools or feeds executed tool results back
through a model-controlled tool loop.

## Proposed server-owned loop

    User input/attachments -> load owner-scoped session and resource versions
      -> model requests an allowed tool or asks a question
      -> validate arguments, permissions, preconditions and idempotency
      -> execute tool -> persist real result -> give result back to model
      -> continue within call/time/cost limits, or pause for user/job completion
      -> review-ready private draft

Suggested first tools (new wrappers, not existing tool contracts):

- `get_listing_context`: authoritative draft, current photo version, confirmed facts,
  evidence status, pending question and analysis job state.
- `assess_photo_evidence`: invoke existing coverage logic on owned attachment refs;
  return observed/missing roles, detection status and versioned evidence.
- `record_user_facts`: accept supported condition/size/category choices and explicit
  brand/description corrections, retaining user versus model provenance.
- `record_evidence_unavailable`: record only an explicit user waiver of a currently
  requested role. Preserve the existing coverage-timeout/category-selection policy.
- `create_private_draft`: existing creation validations plus an idempotency key.
- `start_listing_analysis`: one eligible job per input version; preserve existing
  pricing-model assignments, duplicate reuse, identity keys and manual review.
- `get_analysis_status`: return actual job outcome; never interpret a pending job
  as failed or turn a missing estimate into a fabricated value.
- `update_private_draft`: validated user-requested corrections, triggering only the
  existing required invalidation/reanalysis behavior.
- `prepare_draft_review`: actual saved snapshot, unresolved issues and confirmations
  needed. This is not a publish tool.

Asking a question is a durable pause: store the question ID, expected answer type
and evidence/version it concerns. Resume on a user answer. Long analysis uses the
existing worker queue; persist its job ID and resume once terminal, without keeping
an HTTP request or unbounded model loop alive.

## Boundaries and gaps to address

- **Server authority:** current listing-chat orchestration merges client-provided
  stage/coverage/fields. Existing listing APIs still validate mutations, but the new
  tool dispatcher must independently reconstruct state and check ownership.
- **Honest outcomes:** current orchestrator can say "I've updated" or "I'll publish"
  before a client-side operation succeeds. New replies must use persisted tool
  results; planned, running, succeeded and failed must be distinct states.
- **Idempotency/concurrency:** retries, duplicate messages, two devices and worker
  callbacks must not create duplicate drafts/jobs or overwrite newer answers.
  Use durable tool keys plus atomic revision checks, not frontend busy flags.
- **Resumption:** a run records session owner, draft, photo/content version, pending
  tool/job, result/error, permitted next actions and bounded model usage. Restart
  the process or change devices without losing the authoritative workflow state.
- **Evidence changes:** new/replaced photos invalidate the relevant evidence and
  analysis using existing pipeline rules. Condition-only changes retain eligible
  identity and reprice with the sticky assigned model.
- **Human decisions:** do not infer the user's condition, silently waive evidence,
  claim authentication, fabricate price or treat approval to analyze as approval
  to publish. Later publication needs a distinct confirmation bound to the exact
  reviewed listing revision.
- **Untrusted inputs:** photo text, retrieved sources, descriptions and client
  messages are data, not tool permissions or workflow policy. Tool arguments cannot
  grant another owner's access or override pricing/review gates.
- **Observability:** trace chosen tools and factual outcomes, latency, retries,
  failures and token usage with redacted data. Do not persist hidden reasoning or
  secrets. A failed tool must never produce a success claim.

## Implementation order and acceptance gates

1. Extract reusable listing/evidence/analysis services without changing behavior;
   add contract tests around ownership and existing validation/reuse rules.
2. Add explicit database migrations for runs/tool ledger and revision-aware session
   state. Test cross-process retry/resume and atomic idempotency.
3. Implement typed function tools and bounded execution using the configured chat
   model; test with stub model responses before any paid evaluation.
4. Connect web and mobile to the same feature-flagged server loop; retain existing
   upload/camera UI, cards and legacy fallback. Resume on job completion.
5. Evaluate real journeys with explicit authorization for paid calls: incomplete
   photos, unavailable view, coverage timeout, category selection, user corrections,
   condition change, photo replacement, manual-review pricing, interrupted jobs,
   provider failures, duplicate sends, concurrent devices and cross-owner attempts.
6. Release locally first. A passing first milestone creates exactly one private
   review-ready draft, resumes reliably, reports failures truthfully and never
   publishes or trades. Broader rollout requires explicit approval.

## Reference

OpenAI's [function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
describes the model request -> application execution -> tool-result continuation
loop. Use it as the transport pattern; Jouft's backend remains responsible for
permissions, durable state, business validation and asynchronous worker execution.
