# Listing chatbot: current flow and agent implementation plan

Mobile keyboard release verified October 24, 2026: source `b099b26` adds
keyboard avoidance around the assistant modal, retaining its safe-area boundary.
All 32 mobile tests passed. iOS build 62 (`d9c98018-8feb-4dd8-b12d-61bd30b39566`)
and App Store Connect submission `c71e9ccb-d6f9-4cc6-8819-66e9cb99169c` finished
successfully; Apple processing/TestFlight availability is not verified. Android
APK build 7 (`334ee852-3cf8-4e7f-825e-be99c4eea7e5`) finished successfully.
No web/backend rollout was needed; listing analysis and trade rules are unchanged.

Production verified October 21, 2026: release `7775fd0`, workflow `39646442566`,
passed migrations, API/worker stability and post-deploy smoke checks. Conversation
and listing-agent features are enabled in the hosted web build and API. Earlier
local-only implementation notes below are historical for those web/API features;
mobile source is not a new mobile-store binary. The deployed web bundle contains
the threaded UI, choice cards and corrected status-row layout; public health is OK
and the conversation endpoint returns 401 without sign-in. No listing reanalysis,
publication or trade send was initiated by deployment verification.

Local status-row layout fix: image-less trade/shipment results use a full-width
text column instead of placing titles in the 58px thumbnail column. Result sections
align to the conversation width; image-bearing item cards retain their thumbnail
layout. A separate `pending_trades` read returns only exact pending statuses among
the participant's 50 most recent offers, excluding accepted/declined/proposed/
completed records before pagination. Its server-saved query preserves that filter
on subsequent pages. The existing `trades` read remains all-status; neither read
changes offers, matching or ownership checks. No production deployment.

Local control styling (October 21, not deployed): listing chat uses Jouft's warm
neutral surfaces, burgundy primary/outlined secondary actions and editorial type.
Mannequin inclusion is presented as two labeled selection cards with compact native
web radios and accessible mobile radio choices. The preview/disclaimer and choices
use a two-column desktop layout that stacks on narrow screens. Upload selectors
and confirmation fact summaries are styled consistently. Keyboard focus, disabled
states, no default inclusion selection and existing version-bound approvals are
unchanged; this is presentation only, not an analysis/publication policy change.

## Chronological timeline — October 21, 2026 (local only)

Local next-step fallback: the saved session now exposes a read-only `next_step`
projection with missing required facts and the next concrete question. Reading
listing context returns that guidance, not “context loaded.” Required evidence
comes first; optional views do not block condition/size collection. A child turn
that pauses on a status/read tool without setting a question uses existing bounded
recovery with saved evidence, without another provider call outside the turn's
timeout or inferred approval. If no recovery is safe, it still reports the specific
missing inputs/check rather than “continue with remaining details.” Condition
buttons also recognize this next-step question for older sessions lacking pending
state. No pricing, size allowlist or publication/analysis approval changes.

This supersedes the earlier panel-position fixes below. Web/mobile render a shared
timeline of messages, saved photo sets, coverage results, review/confirmation states,
and result cards. Listing session JSON retains up to 80 timestamped presentation
snapshots; repeated reads do not add duplicates. Photo changes preserve earlier
snapshots and append coverage invalidation/reassessment events. Parent assistant
replies retain their own result sets rather than moving one global result block
below later turns. User messages are stamped when received, not after model work.

Historical review/trade snapshots contain only allowlisted display fields and are
read-only. Only the latest action event renders existing live guarded controls;
approval tokens are never copied into presentation history. Photos/coverage do not
move to the bottom when the item becomes analyzed or published. The child controller
still owns uploads, polling and confirmation; no business authorization changes.

For legacy sessions, missing event times are inferred from saved message anchors
and marked `inferred_time`; exact old chronology cannot be reconstructed where no
clock exists. Untimed messages retain stable relative order without preventing
new timestamped events from sorting. Old result sets that were never saved in a
reply cannot be recovered; the currently available legacy set is shown at the last
assistant reply. Both histories remain owner/session scoped, with existing bounded
message retention. No production deployment or data migrations are included.

## Additional read tools — October 21, 2026 (local only)

- `more`: pages a server-saved result set for closet, named lookup, Marketplace
  search, per-source matches, trade status or shipment status. Clients/models pass
  a result-set ID, not an offset or replacement query. The server reloads inventory,
  reruns the original query and rechecks ownership/eligibility/preferences. Web/mobile
  show absolute page ranges and number the current page consistently. Inventory
  changes may move results between pages; this is live offset paging, not a frozen
  inventory snapshot. Missing/stale result sets require refresh, and empty shifted
  pages offer a query reset. Retry replays the committed page exactly.
- Matching pages remain three targets per source using the normal matching service;
  a More action preserves that source ID and fixed rules. Initial all-source matching
  still covers up to 12 recent eligible sources; paging does not expand that source
  cohort. Closet/lookup/search inspect at most 5,000 recent records. No hidden rule
  broadening or new research/model analysis is performed.
- `preferences`: reads only saved categories and tops/dresses/bottoms/shoes sizes.
  It cannot write preferences. Contact, demographic, address, subscription and
  payment data are excluded before any result is sent to the model or client.
- `trades`: up to 50 recent offers for the current participant, or one authorized
  offer ID. Projection includes only reference, item title and status, never offer
  messages, participant addresses or billing data. No send/accept/decline operation.
- `shipping`: saved carrier/status/ETA/update time for the caller's authorized
  shipments within those recent offers, or one authorized offer. Both offer and
  shipment participation are verified. No carrier polling, tracking-number/address
  disclosure, label purchase, payment or shipment mutation. Displayed data is saved
  status, not a live carrier lookup.

The shared catalog, typed arguments/outcomes, server next-action buttons, parent
thread replay and existing local flags apply to all these reads. The model may
read trade results then inspect a specific shipment; ownership checks always run
again. Tests use stubbed model/domain data, including foreign records, paging,
unchanged query/source constraints, safe projection and retries. No production
deployment or real trade/shipping writes are part of this extension.

## Consolidation architecture review — October 20, 2026

Status: reviewed design, **not implemented or activated**. This section supersedes
the older proposed architecture below; the local pilot remains as described in
Implemented local pilot. No model switch, production change, or analysis change
is part of this review.

### Findings from the current code

| Evidence | Consequence | Consolidation decision |
| --- | --- | --- |
| `main.py:app_assistant_chat` asks for one intent and branches before returning | Multi-step requests cannot naturally inspect results and choose the next operation | Replace the routing decision with a bounded tool loop, not a larger intent enum |
| `listing_agent.py:ListingAgent.turn` already persists state, serializes turns and records tools | Good durability exists, but it is scoped to one listing | Reuse the durability pattern; retain listing sessions as child workflows |
| `AppAssistantRequest` accepts client history/context while listing-agent sessions are server-owned | Switching modes loses a single authoritative conversation and reference history | One owner-scoped parent conversation and transcript, with explicit workflow links |
| Context exposes source, focus and flat result IDs | A target may match several owned items; a flat target list loses the relationship | Store result sets with source/target pairs and a stable result-set ID |
| Photo/plural matching regex overrides compensate for wrong model intents | Individual phrases pass while equivalent new phrasing can still fail | Replace routing overrides after semantic-tool evaluation passes, retaining deterministic authorization checks |
| General Yes/No uses a signed pending action, listing tools use distinct revision-bound tokens | Two confirmation protocols must not be accidentally interchangeable | Normalize the UI action envelope; preserve each domain's exact validation/token boundary |
| Shared capabilities are prose separate from tools | Described abilities can drift from executable abilities | Generate capability descriptions from the registered tool catalog |

### Target flow

    Web / mobile: message, attachments or explicit action + request ID
      -> owner-scoped conversation, revision and durable replay lookup
      -> load authoritative resource state + linked listing workflow
      -> bounded model/tool loop with shared capability catalog
      -> authorized domain services -> persisted factual outcomes
      -> one response: messages, grouped cards, gallery, question or confirmation

The parent conversation is not a new pricing engine. Listing creation, evidence,
Gemini identification, pricing model assignments/reuse, workers and mannequin
generation continue through the existing listing services. Ordinary form-based
creation/evaluation must never depend on the conversation service.

### State and tool contracts

- Parent conversation: owner, revision, transcript, active workflow ID, pending
  question/action, focus and ordered result sets. Explicit new-draft intent creates
  a child workflow; it never resumes an unrelated published item automatically.
- Result set: ID, domain, query/scope, source IDs, ordered entries and pagination.
  Each match entry contains source and target IDs. Ordinals resolve against that
  set, not an unrelated previous closet list. Public target IDs are revalidated.
- Goal scope: tools explicitly support `one`, `selected` and `all_eligible` where
  meaningful. The model interprets language; the server validates scope and bounds
  work. Do not require an extra model-generated planning artifact before every tool.
- Read tools: list owned listings, search Marketplace, find matches with explicit
  scope/filter/pagination, read saved listing details/gallery, read authorized
  trade/shipping status. Results include outcome and freshness; current matches
  are not described as historical/new-since-last-visit without stored evidence.
- Workflow tools: start/resume a listing workflow and invoke existing evidence,
  fact, analysis/status, correction and review operations through guarded adapters.
- Mutation tools: prepare publication/trade, confirm exact action or cancel it.
  Confirmation ID binds owner, operation, arguments, resource snapshot/revision
  and expiry. Changing source, target, photos or relevant fields invalidates it.
  A model tool argument is never itself human approval.
- Presentation envelope: typed question choices (including Yes/No), confirmation
  actions, grouped listing cards, gallery and job status. Both clients render
  these identically; do not infer buttons by searching assistant prose.
- Unsupported features return a truthful limitation/navigation response, not an
  invented account/payment/notification tool or broad database access.

### Migration slices and release gates

1. **Extract domain adapters and contract tests.** Move general-chat reads and
   matching behind typed services shared with listing tools. Preserve eligibility,
   preferences, ownership and duplicate-offer exclusions. No orchestration switch.
2. **Durable parent conversation.** Add an explicit migration, revision checks,
   request replay and result-set storage; link existing listing sessions without
   copying approval tokens into general context. Resume/restart/two-device tests.
3. **Read-only tool-loop pilot behind a separate default-off flag.** Replace
   general read intents with the catalog, keeping the configured model. Test
   plurals, pronouns, ordinals, topic changes and follow-ups without regex routing.
   Keep old routing available for rollback; do not silently replay failed writes.
4. **Single transcript and child-workflow integration.** Web/mobile render the
   parent response envelope; draft/review is a workflow in the same conversation,
   not a second nested chat. Existing uploads, full-screen gallery and valid-size
   rules stay intact. Cover explicit new draft versus resume.
5. **Confirmed writes.** Connect existing publication/trade adapters only after
   stale approval, double-click, lost response, concurrent update, cross-owner and
   token-type isolation tests pass. No automatic acceptance, payments or shipping
   purchase is added.
6. **Evaluate, then remove compatibility patches.** Keep regression journeys, but
   remove phrase overrides only when the new path passes their semantic variants.
   Local rollout first; production rollout remains separately authorized.

### Evaluation requirements

Build table-driven multi-turn journeys, not one assertion per screenshot. Each
journey includes paraphrases, expected tool(s)/scope, actual authorized resources,
forbidden mutations, expected clarification and next-turn behavior. Cover:

- One item / selected items / all eligible items, no matches, pagination and one
  target matching multiple sources; selecting a target must not guess the offer.
- Matches -> photos -> second item -> details -> prepare trade -> No; separately
  Yes sends exactly once. Asking a question while approval is pending sends nothing.
- Create -> missing evidence -> add photo -> valid condition/size -> analysis ->
  correction -> separate publish -> matches, with interruptions and retries.
- Prompt injection in titles/descriptions, foreign/private IDs, stale result sets,
  deleted/inactive targets, changed preferences and unsupported capabilities.

Stubbed tests verify contracts/replay/safety, not model comprehension. A separate
explicitly authorized live evaluation must measure tool/scope selection, needless
clarification, factual replies, latency and cost on held-out paraphrases. No paid
calls are required for this design review. Release requires all safety cases to
pass and no regression against the existing deterministic workflow contracts;
record quality thresholds and the actual live sample before enabling the pilot.

The target uses the application-executed tool-result continuation pattern in the
[official OpenAI function-calling guide](https://developers.openai.com/api/docs/guides/function-calling).
Keeping Jouft's database as the authoritative state is an application design
decision, not a requirement imposed by that API.

Step 1 started locally: `assistant_reads.py` now holds the authoritative
read-only Marketplace matching adapter. The existing HTTP route delegates to it,
so general chat and listing-agent reads share the same owner, preference, value,
sent-offer, media-hydration and pagination policies. Typed `MatchRead` scopes and
grouped results preserve source/target relationships for plural matching.
Contract tests cover scope, ownership, exclusions, pagination and the same target
matching multiple owned sources. Table-driven photo-follow-up variants exercise
the existing two-turn regression with deliberately wrong model intents.
Step 1 read extraction is now complete locally: Marketplace term filtering and
safe listing-card/gallery projection are shared adapters too. Both chat paths
reload saved detail/gallery records through an owner-or-public-Active visibility
check at read time, so stale displayed IDs do not retain private access. Listing
workflow context and matching eligibility remain additional restrictions, not
replacements for visibility. Tests cover search parity, gallery deduplication,
private-field exclusion and inactive foreign records. No new loop, parent
conversation, model switch or flag activation has been implemented. Next: step 2,
durable parent conversation storage and replay contracts.

Step 2 storage foundation implemented locally (inactive): explicit migration
`0010_assistant_conversations` adds owner-scoped parent snapshots and committed
turn replay records. `assistant_conversations.ConversationStore` provides stable
creation IDs, owner-checked loads, optimistic revisions, per-conversation locking,
and atomic transcript/result-set/workflow-link plus response commits. Reusing a
request ID with different user input is rejected; a completed retry returns the
original response even if its expected revision is now old. Child listing-workflow
links must belong to the same owner. Result entries can preserve multiple sources
for one target. No approval tokens are imported into the parent state.

Tests cover restart, replay, stale turns, foreign owners/workflows and rollback
after simulated interruption before the replay insert. Operations require their
own Database connection. This is committed-turn storage, not an in-progress tool
ledger: future provider/tool orchestration must still use durable domain keys and
existing listing-agent recovery for side effects. Result-set payloads are currently
internal server-produced JSON; typed envelopes and size/history retention limits
remain required before exposing a public endpoint.

No parent-conversation routes or client switch are active. The migration was
tested in temporary databases only; run the explicit normal migration before
starting a backend on this revision. No request-time schema changes were added.
Read-action API implemented locally under default-off
`ASSISTANT_CONVERSATIONS_ENABLED`: create/load and `/turns` under
`/v1/assistant-conversations`. Strict requests permit only closet/search/details/
matches; clients cannot submit approval or mutation fields. Typed result sets
carry domain, source link, count and bounded cards. Saved history keeps the latest
40 messages; replay responses remain stored separately. Dedicated connections
close after each request. Reads interrupted before commit can be safely retried;
committed retries return the exact stored result and reject changed input.

The explicit `/turns` endpoint remains available for read-action contracts.
Natural-language `/messages` is now implemented behind the same default-off flag:
`assistant_read_agent.py` runs a Responses tool loop using the existing configured
chat model. Its strict `read_listings` catalog supports closet/search/details/
matches, including single/all-eligible source scope. Server execution uses the
same guarded adapters. Full response output and actual tool results are replayed
within the loop; no legacy regex intent overrides are used. The model may ask a
clarification without a tool. It cannot dispatch publication, edits or trades.

Execution is bounded to four model calls / 45 seconds, disallows tool batches,
stops identical repeated reads and reports unavailable records as tool errors.
Committed retries reuse the response without a provider call; provider failure
leaves no committed turn. Interrupted uncommitted read runs may repeat provider
calls (and incur cost); durable in-progress model/tool checkpoints and usage traces
remain unfinished. Concurrent reads may both run but only one revision can commit.
No side-effect tools may be added under this incomplete recovery contract.
Only stubbed providers have been tested; no live quality evaluation or client
switch is introduced. Typed question/gallery presentation and live privacy-safe
result refresh remain next steps.
Stored result snapshots are historical (including media URLs that may expire),
not an assertion of current availability. No publication/trade execution exists
on this endpoint. Existing listing forms, evaluation and pricing are unchanged.

### Read-only UI integration (activated locally October 20)

### Capability grounding and outcome controls (local, not production)

### Parent-to-listing workflow bridge (implemented locally)

When both pilot and listing-agent flags are enabled, `listing_workflow` is an
additional tool: start an explicit new photo-first workflow, resume the exact
child linked to this thread, or reopen review for an actual owned private listing.
New sessions use an ID derived from parent conversation + request ID, so a lost
parent checkpoint/retry cannot create duplicate children. No parent turn creates
a listing record, starts analysis, publishes or sends an offer. Parent state stores
only the owner-checked child session ID, never analysis/publication/trade tokens.
Resume without a linked child asks which listing rather than adopting a global
latest session. New chat starts clean; explicit new listing starts a fresh child.

Web/mobile render the existing guarded ListingAgentChat inside the current thread
and load by exact child session ID. While open, its composer replaces the parent
composer; Back to conversation retains the linked child and Continue listing
workflow reopens it. Child photos, valid fact/size collection, analysis confirmation,
polling, correction, publication and trade controls are reused unchanged. Thread
switching is disabled while the child reports an operation in flight. Starting
another child must go through the parent, not an unlinked child New draft button.

This is workflow integration, not a merged transcript/tool engine: the child keeps
its own durable conversation and approval ledger. The next parent message reloads
only owner-checked child listing ID/stage/job ID so follow-up reads can identify
the linked item; it does not copy tokens, claims of job success or the full child
transcript. Mobile uses workflow-local photo
selection (camera/library) rather than the regular form's staging state, preventing
photos selected for another form/thread from being uploaded to the linked child.
No live provider, browser or device acceptance is claimed for this bridge. Tests
cover start/resume, checkpoint recovery, exact child loading, foreign ownership,
and no implicit listing/job/offer creation. Standard form evaluation is unchanged.

Outcome taxonomy follow-up: typed read outcomes expose `category` independently
of detailed status. Clarifications/invalid arguments are `unclear`; absent
capabilities are `unsupported`; ineligible/unavailable/access failures are
`blocked`; temporary provider/read failures are `tool_failure`. Empty/no-match
results remain normal results, not errors. Only actual backend evidence can
establish a block or failure; the model's request_input tool can ask for an item,
search terms, the overall task, or explain an unsupported capability.

HTTP 5xx/429 and timeouts are no longer reworded as unavailable items. They return
a sanitized retryable 503 with no committed turn, so Retry saved request keeps its
original ID/revision. Web/mobile distinguish temporary failures from access or
revision blocks and do not offer blind retries for permanent 4xx errors. A 409
still reloads saved state without silently resending. No outcome authorizes a
write or relaxes a business rule. This applies to the parent read-only pilot;
regular listing creation/evaluation and the dedicated listing agent are unchanged.

Named-reference follow-up: the read catalog includes `lookup`, an owned-inventory
brand/title/category/size search. A unique match returns saved details immediately;
multiple matches show only relevant choices and leave focus unset; no match asks
for a refined reference. Lookup searches up to 5,000 owned records rather than
only the latest displayed page. It does not modify Marketplace matching criteria.
Premature choose-listing tool calls receive a tool-level instruction to attempt
targeted lookup before surfacing a clarification. No user-message phrase parser
or Chanel-specific rule is introduced. Regression coverage includes unique,
ambiguous, nonexistent and foreign-owner lookalikes plus model recovery.

All five grounding improvements are implemented for the parent read-only pilot:

1. `assistant_capabilities.py` is the authoritative catalog. Tool descriptions
   and model capability context are generated from the actual registered reads.
   Shared argument validation prohibits match-search terms, invented price-range
   filters, extra policy fields and mutations. Matching rules remain in existing
   backend services; none are changed by this work.
2. Read results include typed outcomes: available, empty, no_matches, ineligible,
   more_available, no_photos, unavailable, invalid_arguments, clarification or
   unsupported. Eligibility uses the same published/positive-value source gate;
   normal match service still enforces preferences/value/size/sent-offer rules.
   Extra results are reported honestly; no unsupported pagination action is offered.
3. The model interprets scope/references and chooses tools. The backend supplies
   user-visible factual summaries and terminal match/detail/gallery replies.
   A completed match read stops the loop, rather than automatically substituting
   broader search. Keyword browsing explicitly says it is not qualified matching.
4. Only validated server-produced next actions become web/mobile buttons.
   Actions are restricted to executable read arguments and current outcome;
   ineligible sources do not offer Refresh matches. Clicks use the ordinary
   authenticated read endpoint with current revision and stable retry IDs.
   The model can use a constrained request_input reason (choose listing, search
   terms, unsupported). Free-form model output cannot add promises, policy changes,
   follow-up options or success claims; unsupported prose gets a truthful scope
   response. This deliberately trades conversational variety for reliable result
   presentation while the read-only pilot matures.
5. Regression coverage includes multi-turn source-details -> matches, empty,
   ineligible and more-results outcomes, unchanged revisions after rejected policy
   inputs, gallery/retry flow, paraphrase fixtures, unavailable/private records,
   injected capability suggestions, fixed tool scopes and executable UI choices.
   Providers are stubbed; these tests establish contracts, not real model semantic
   accuracy. Live quality evaluation remains a separate release gate.

These controls apply to the parent pilot only, not the retained legacy general
router or dedicated listing-agent engine. Existing pricing, identification,
analysis, regular form creation and publication/trade approvals are unchanged.

Dedicated chat/thread UI (local): the web launcher navigates to `?tab=assistant`,
a responsive full-page workspace with a thread sidebar and composer, instead of
the floating pilot panel. Mobile's full-screen chat includes New chat and a
horizontal thread picker. GET `/v1/assistant-conversations` lists only the caller's
50 most recently updated threads with titles saved from the first user message
(older threads fall back to retained history). New chat uses a distinct retry-stable creation key and clean state;
switching loads the selected saved transcript/results/focus. Opening chat resumes
the most recent thread rather than a single fixed thread. Busy/failed pending
operations block switching until completed/retried; no duplicate sends or implicit
approval transfer. No thread deletion, rename or search is provided yet. Existing
read-only capability limits and default-off production flag are unchanged.

Gallery follow-up fix (local): `read_listings(action="photos")` is distinct from
details. It reloads an authorized saved item (or current focus), returns the full
gallery and a request-bound presentation event, and stops the model loop without
repeating the details summary. Web/mobile open the existing full-screen carousel
once per event. The committed response replays the event after a lost response,
but loading/resuming conversation state does not reopen it. Thumbnail clicks use
the same photos action. Ambiguous/no-focus reads ask for selection; no media yields
an explicit no-photos reply. No analysis or listing changes are made.

Response-formatting follow-up (local): web/mobile render text as paragraph,
heading and bullet blocks with safe bold spans, never raw HTML. Older saved
listing-ID/image-path dumps are cleaned for display. A successful details read
uses the server's line-separated saved-field summary rather than the model's
free-form re-enumeration of transport metadata; cards retain clickable galleries.
This changes presentation only, not listing analysis, valuation or publication.

Web `AssistantConversation.jsx` and mobile counterpart render the parent snapshot
through shared `createConversationController`. Separate opt-ins
`VITE_ASSISTANT_CONVERSATIONS_ENABLED=true` and
`EXPO_PUBLIC_ASSISTANT_CONVERSATIONS_ENABLED=true` replace only the general
assistant panel with this read-only pilot. API requires
`ASSISTANT_CONVERSATIONS_ENABLED=true` and explicit migration 0010. All three
flags default off in code; local ignored environment files now enable them.
Migration 0010 was applied to the local database. Production is unchanged.

Opening resumes the same owner-scoped `read-pilot-v1` creation request, including
after panel close/reopen. Account identity keys reset client state. Messages and
grouped source-title results come from the server, not legacy context. Composer
and cards disable while sending; errors expose Retry saved request using the same
request ID/revision. Stale revisions reload rather than silently resend. Photo
clicks reread the item, persist focus and open the existing full-screen gallery.
Normal listing creation/evaluation and the existing dedicated listing agent are
unchanged; the pilot explicitly describes its read-only scope. Legacy general
chat remains the default/fallback by disabling the UI flag, not automatic rerouting
of failed requests. Live local API smoke checks passed with the configured model:
Marketplace read, identical committed retry/resume, and correct resolution of the
second displayed item (12 actual results). These checks used local API-key test
conversations, not the signed-in browser owner's workflow. Chrome automation
became unavailable, so authenticated visual walkthrough remains unverified.
Mobile's local flag is set but requires app/Metro reload; no native-device
walkthrough is claimed. API health returned 200 and Vite served the enabled flag.

This completes UI wiring for the read-only slice, not full workflow consolidation:
creation/review/publication/trades still need child-workflow integration before the
pilot can replace the full assistant. Resume shows saved snapshots; automatic
privacy-safe refresh of all historical results and in-progress model checkpointing
remain release gates. Retry after a lost photo-read response restores the snapshot
and replays its request-bound gallery event without a second read.

Local plural matching: requests for matches for “my items/listings” check up to
12 recent active, positively valued owned listings, returning up to 3 current
eligible Marketplace matches per source with source-title headings on web/mobile.
Existing match rules and sent-offer exclusions apply; no offers are sent.

Local confirmation UX: general-chat trade and publication confirmation prompts
offer Yes/No buttons on the latest pending action. These send ordinary chat replies;
signed action validation and ownership checks remain required. Historical prompts
cannot be clicked again, and buttons are disabled while a reply is in flight.

Updated October 21, 2026. First bounded implementation is now present locally,
behind default-off flags. No production rollout or paid model evaluation has been
performed for this agent. The current-flow table below describes the retained
legacy path; the new path is described in the implementation status section.

## Implemented local pilot

- Shared intelligence layer (local): `assistant_context.py` supplies one capability
  guide to both model paths and an explicit source/display/focus/stage/pending-operation
  context contract. Web/mobile retain this context when leaving listing chat, but
  clear legacy pending-action approvals; metadata never authorizes a mutation.
  Server-owned session metadata is owner-checked and referenced records are hydrated
  only if owned or currently public Active items. General matching uses the normal
  matching service instead of a second value-only implementation.
- Dedicated read actions: general chat has `view_photos` / `view_item`; listing
  agent has `view_listing_photos` / `view_listing_details`. Requests for pictures
  of an already displayed match no longer run reverse matching. Photo reads return
  a full-screen gallery action, save item focus, and never rerun pricing, publish
  or send offers. Multiple unselected items require clarification. Thumbnail clicks
  in both chats open galleries and retain focus; retry responses open at most once.
- This unifies context and capability knowledge, not the two orchestration engines
  or transcript stores: general chat retains its structured-intent router and
  client transcript, while listing chat retains its persisted function-tool loop.
  Unsupported account/notification/payment writes are not newly enabled. Automated
  multi-turn tests use provider stubs, including a deliberately wrong old intent.

- Final trade-request step: Request trade on a current match (or a chat selection)
  prepares an exact source/target summary. Confirm and send trade request uses a
  separate proposal token; publication approval and ordinary prose cannot send.
  Both items, current preferences and matching eligibility are checked again.
  Cancellation sends nothing. Normal offer/subscription/duplicate/notification
  rules are reused; a stable internal offer ID recovers a committed send after a
  lost response without creating another offer. Success points to Trade Inbox.
  This sends an ordinary pending offer of the user's item, not final acceptance,
  shipping purchase or payment. Local only; real user offers were not sent in tests.

- Match photos open the existing full-screen viewer directly from chat, with the
  thumbnail image first and all available listing photos in the carousel. Closing
  returns to the existing conversation; no listing navigation or mutation is needed.

- Invalid saved sizes now prompt for a correction in chat, list canonical allowed
  sizes and give a “Change size to …” example, rather than redirecting to My Closet.
  Publication remains blocked until corrected; size-only edits retain value.

- Review lookup ignores conversational command words such as “review” in title
  references. Ambiguous requests show actual candidate cards; unmatched titles show
  recent owned drafts or an explicit no-listing message, never an empty chooser.

- Read-only Marketplace matching after publication: `find_marketplace_matches`
  reuses the normal closet matching service (value tolerance, current preferences,
  target-category sizes, other-owner Active listings, already-sent offer exclusions).
  Users can ask in chat or use Find matching items / Refresh matches. Web/mobile
  show the first 12 actual results, total/empty state and links to item details.
  Session reload refreshes matches against current availability/preferences.
  Private drafts must first be explicitly published; finding matches never publishes
  or sends offers. Sending a request is the separate, confirmed final step described above.

- Condition questions offer New with tags / New / Like new quick-reply buttons on
  web and mobile. They send ordinary chat answers through existing validation;
  typing remains available. Buttons appear only for the current condition question.

- Explicit create requests now start a fresh, retry-safe session instead of loading
  the previous conversation. Web/mobile pass one stable creation request ID per
  new-listing intent; default resume and listing-specific review remain separate.

- Simplified local review presentation: one contextual assistant header; web hides
  the duplicate general-chat handoff while in listing mode (Back restores it).
  Review photos, description and history expand on demand; saved/proposed values
  and message-based save/discard instructions stay together. Publish appears only when eligible.
  Outstanding proposals use a deterministic save/cancel reply, not an extra question.

- Review confirmation recovery (local): pending questions no longer hide saved
  edit proposals. Staged proposals remain visible and can be saved/discarded by
  message; the shared controller retains legacy durable-token support.
  Regression coverage includes a size proposal followed by a pending question.

- Message-first corrections: no embedded Edit details form. Explicit correction
  requests save validated fields directly; size/title/description-only changes keep
  the value, while brand/category/condition/photo changes require normal analysis.
  Questions and hypothetical changes never auto-save; publication remains separate.
- Pricing parser fix (local): currency ranges normalize Unicode dashes and exclude
  URLs. Rationale normalization no longer overwrites a model price using a size,
  delivery window or numeric product-ID range from a comparable URL.

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
After a draft is created, explicit validated corrections are saved from chat messages
without an edit form or redundant confirmation. The agent supports explicit reviewed-version publication,
and now supports separately confirmed trade requests. A new
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
Publication was outside the first tool set and is now implemented locally below.
Marketplace matching and confirmed trade requests are now implemented locally below; accepting trades and payments remain outside this delivery. Keep the existing chat path available behind a feature
flag while evaluating the replacement. Retain the configured chat model initially;
this is an orchestration change, not a model migration.

## Review and publish extension (local only, not deployed)

When the saved analysis job succeeds, the web/mobile review card displays actual
title, brand, condition, size, description, value and current saved gallery.
Corrections now use the tools and edit form below, with My Closet retained as an
alternative. A different external analysis job or non-draft status closes the old
workflow; explicitly reopen review to adopt the current saved listing.

The public session includes a publication-review token bound to the persisted
listing snapshot and job. Publication uses a distinct `publication_token`, not
the earlier analysis `confirmation_token`. The explicit “Confirm and publish to
Marketplace” control submits it with the current session revision and an optional
explicit mannequin `include`/`exclude` choice. Synthetic previews carry the existing
AI disclaimer; a choice is required when generated assets exist. There is no
default choice and no publication based on prose, model inference or a timer.

The guarded `publish_listing` tool rechecks owner, current successful analysis,
valid size, positive valuation and pending pricing review. It calls the normal
listing update/publication path, retaining subscription, media-review, mannequin
rejection and publication-email behavior. Snapshot validation plus an atomic
`expected_updated_at`/latest-analysis-job write conditions reject a concurrent edit or reanalysis without
overwriting it. Ordinary updates that omit this optional condition are unchanged.
The session persists separate publication approval before the write; replay and
post-write recovery recognize the already-active listing without publishing again.
The session then reports `published`. No trade is submitted. Production flags and
pricing/evaluation are unchanged; no real user listing was published during tests.

Verification: 542 Python tests and 42 JavaScript tests passed, along with the web
build and offline iOS JavaScript export. Publication tests cover prose refusal,
separate approval, include/exclude choices, stale snapshots, atomic concurrent-edit
and reanalysis conflicts, manual review/subscription/ownership checks, replay and
recovery after the listing write but before the tool checkpoint.

## Existing-listing review handoff and corrections (local only)

The general assistant now has a `review_listing` intent for review/edit/correct
requests. It resolves an owned listing by exact model-selected ID, title, or the
numbered closet results (including “review first one”), then returns
`review_listing_id`. With the agent enabled, publication requests also enter review
instead of bypassing it through the older general-assistant publication action.
Both clients pass this target to `POST /v1/listing-agent/sessions/review`, rather
than loading an unrelated latest session. Ambiguous references show candidates.
The default-off legacy publication path remains available when the flag is off.

Review sessions are owner-scoped and stable per listing; opening one creates no
new listing or analysis job. It adopts the current latest job. Legacy drafts with
saved analysis but no job use that persisted result, not a fabricated analysis job;
drafts without completed/saved analysis cannot publish. Existing gallery originals
are loaded and hash-checked for staging; generated previews are not evidence.

The model chooses `propose_listing_changes` for explicit corrections to title,
description, brand, category, condition or category-valid size; price/admin fields
are rejected. A clear correction request saves directly after server validation.
Hypothetical questions and photo staging do not auto-save. Legacy/staged proposals
use exact-token controls or the “Save changes” message; snapshot and latest-job/
update-time write checks reject stale proposals. Publication approval is separate.

| Confirmed change | Behavior |
| --- | --- |
| Title, description or size only | Save private metadata; retain analysis/value |
| Brand, category, condition or photos | Queue ordinary reanalysis; publication waits |
| Price/admin/unsupported fields | Reject |
| Keep as draft | Remain private; do not silently save or discard proposals |

Photo additions/removals during review change only session evidence until confirmed.
Saved listing images remain untouched; changes block publication and invalidate old
approval. Earlier proposed text corrections survive subsequent photo staging.
`discard_listing_changes` requires an explicit cancellation and restores staged
photos without modifying the saved listing. Confirmed changes call the normal
listing update path (same model routing, identity/reuse, condition pricing, media
normalization, quota and manual-review rules). After saving, a fresh review and
separate publication approval are needed. There is no automatic publication or
trade. Back to assistant permits selecting another listing.

Normal network retries reuse the same operation/proposal IDs. A write that succeeds
before the session checkpoint is interrupted is protected from being applied a
second time by snapshot/write checks; an external-change conflict requires
reopening review rather than silently reapplying a stale edit.

Verification: the full Python suite passed (551 tests), with a subsequent targeted
API/agent regression run passing (178 tests). Shared-client/web tests passed (44),
as did the web build and offline iOS JavaScript export. Tests cover named/ordinal
handoff, owner boundaries, natural tool proposals, edit-form proposals, separate
edit approval, metadata retention, reanalysis, staged-photo cancellation/merging,
stale edits, and rejection of price fields. A live local browser request to review
the Chanel loafers opened the correct listing's review/edit controls, including
saved `US 10`. Opening/cancelling its edit form left the real listing unchanged;
no real edit, analysis rerun or publication was performed in that browser check.

## Historical legacy implementation map (not the current local agent)

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

The two legacy chat endpoints use Responses API structured JSON output; neither
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
# Direct parent listing adapters — October 21, 2026 (implemented locally, not deployed)

The parent tool catalog now includes guarded child operations for saved context,
photo coverage/removal, intake facts and unavailable evidence, analysis preparation/
creation/start/status, review/corrections, keeping a draft, matches and trade
preparation/cancellation. Operations resolve only this thread's owner-checked child;
the model cannot pass a session ID, approval token or client revision. Strict schemas
reuse the child fact models. Child request fingerprints include selected operation
and arguments; existing child tool ledgers and domain services perform the writes.
One parent turn may read context then dispatch one guarded action. It does not run
a second child-model loop. Existing bounded child recovery can assess evidence or
advance already-approved analysis; it never supplies a new approval.

Photo uploads remain real multipart uploads through the existing child control;
text is not evidence. Removal detaches one saved photo via the existing route and
invalidates coverage/approval while preserving others. Context sent to the parent
model contains facts, saved photos, evidence, stage and listing/job IDs, not approval
tokens. Final analysis/edit/publication/trade confirmation controls remain in the
embedded review UI. `publish_listing`, `send_trade_request` and
`apply_listing_changes` are not model-selectable parent tools. Cancelling a trade
discards preparation only, not a sent offer.

Web/mobile threaded chat use the parent composer while the embedded child displays
upload/review/approval controls. Child state reloads after a parent turn. Child
control events still have their own durable transcript, so this is not yet a fully
merged event history. Standalone listing-agent and regular listing forms are unchanged.

Local transcript presentation fix (October 21): embedded child messages are now
projected into the main web/mobile transcript, not a nested Conversation history.
Shared turns are woven/deduplicated in sequence; new messages carry timestamps,
while legacy records use shared-message anchors. Synthetic upload messages display
as “Added photos.” Current condition quick replies appear in the main chat and
send ordinary parent messages. Child snapshots are scoped to the linked session;
approval tokens are not copied into the parent transcript. The underlying ledgers
remain separate, and standalone listing chat retains its history controls.
Intake photo controls are anchored immediately after the latest upload message,
before the next question; review/approval controls remain at the current end.
Condition buttons render inside their matching question bubble, and embedded chat
does not repeat the initial “Add photos” introduction below the question.

Local photo-coverage presentation: both clients show persisted assessment status,
detected category and per-photo primary/additional roles, missing required views,
explicit unavailable-view waivers, optional recommendations and assessment warnings
below the photos, before intake questions. Missing/invalidated evidence is shown as
not assessed; timeout/unavailable results explicitly say coverage was not verified.
Coverage is distinguished from the subsequent full item/pricing analysis. This is
a read-only projection, with no extra model call or change to evidence requirements.

Local confirmation-placement fix: photo/coverage content and current action controls
are separate render slots backed by one child controller. Only the photo slot is
anchored to the upload event; draft confirmation, publication and trade controls
render after the latest message, never above the user's condition/size answers.
Both slots are linked-session scoped and disabled while their parent/child is busy.
Web message rows span the transcript width so short user replies do not collapse
into single-character columns. Approval contracts and backend behavior are unchanged.

Local correction validation fix: removed the universal US shoe-size correction
example, which was misleading for clothing. Correction sizes use the existing
category size allowlist before saving. Domain rejection from a parent-selected
listing operation is returned as a saved blocked reply with its real validation
message, not a fake stale-conversation error. Genuine revision conflicts still
use conflict/reload handling. No saved listing or value is changed by rejection.
Published-item correction rejections now explicitly say the change was not saved,
report the current saved size, and distinguish published status from an unfinished
analysis. Invalid requested sizes list valid category options. Successful direct
private-draft corrections report the saved fields/values instead of only “Changes
saved.” This does not enable published-listing chat edits or new size options.
