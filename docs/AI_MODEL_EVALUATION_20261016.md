# Initial model smoke comparison — October 16, 2026

Decision: **do not promote yet**. Production is unchanged.

## Latest 10 production listings: migration compatibility pilot

A read-only snapshot selected the ten newest listings by creation time, without
status filtering or replacement. All ten had saved identities and pricing; nine
were Review and one Active. The sample has six LikeNew and four New items and is
mostly clothing, not representative of every category or condition.

The currently deployed API/worker image and model settings were verified: production
revision `51bb1bd`, pricing `gpt-5`, low reasoning. The evaluation loaded that Git
revision's profiler, not the unreleased local prompts/validators. Each case reused
the saved identity, user condition, size and original description hints. Paired
requests were verified identical except model ID. Independent live research was
enabled to reproduce model-switch behavior. Additional include/store flags only
requested source metadata and disabled response storage. No listing was reanalyzed
in place, no values written back, and no review emails triggered.

Completed calls: 20 old/new pairs plus three additional GPT-5 repeats = 23 calls.
An initial harness preflight failed on a missing local constructor attribute before
any provider request; it is preserved separately and excluded from the results.

Provisional tolerance: ±10% on selected value AND both condition-band endpoints.

| Comparison | All three fields within tolerance | Selected value within tolerance |
| --- | --- | --- |
| Sol versus saved production | 2/10 | 2/10 |
| Sol versus fresh GPT-5 | 3/10 | 3/10 |
| Fresh GPT-5 versus saved production | 1/10 | 2/10 |

GPT-5 repeat selected-value changes on cases 1–3 were +16.7%, −28.9%, +2.3%; none
passed tolerance on all three fields. Thus existing rerun/search variability is
material and must not all be attributed to the replacement model. Nine saved
selected valuations had null endpoint fields; the report explicitly supplements
these from their exact-condition raw tables. These endpoints must not be described
as necessarily displayed UI bands. One fresh GPT-5 case lacked exact-condition
endpoints and could not pass the complete-band check.

Two RHODE examples show the behavior difference: Sol anchored near related asking
prices and returned 125, whereas GPT-5 returned 225 and 240 using more MSRP-based
reasoning. These are response-rationale findings, not an independent accuracy judgment.

Conclusion: this pilot does NOT support a transparent model-only switch with stable
existing bands. Preserve saved valuations and investigate sources/adjustments and
baseline reproducibility before tuning compatibility. Do not fit a blanket correction
to these ten cases and declare it validated on the same sample.

Local artifacts (Git-ignored, mode 0600):

- `tmp/model-evaluations/recent10-production-snapshot-20261016.json`
- `tmp/model-evaluations/production_recent10_migration_20261016_run2.json`
- `tmp/model-evaluations/production_recent10_migration_report_20261016.md`

The full artifact includes requests, original responses, source metadata, per-case
deltas, prompt/snapshot hashes and repeats for offline inspection. The temporary
export task exited successfully; the encrypted snapshot remains in private S3.
Verification: 384 tests passed. Production deployments and saved prices are unchanged.

## Fixed sources AND fixed weights: adjustment-only experiment

Saved full evidence, identical requests and provider responses:
`tmp/model-evaluations/fixed_weights_20261016.json` (local, Git-ignored, mode 0600).
Both models received exactly C3/C8/C9/C10 from the prior pool; all four tagged
resale comparables were mandatory, at 25% each. Prior suggested adjustments and
similarity narratives were removed. Tools were disabled and neither model could
return weights, source-selection flags or a final estimate in the response schema.
Code rejects missing/duplicate/unexpected source IDs and never redistributes weights.

| Source | Recorded USD | GPT-5 adjusted USD | Sol adjusted USD | Fixed weight |
| --- | --- | --- | --- | --- |
| C3: Patchwork NWT | 1,731.35 | 1,731.35 | 1,731.35 | 25% |
| C8: Pristine tagged asking | 1,392 | 1,392 | 1,392 | 25% |
| C9: Tagged sold-display | 2,231.25 | 2,231.25 | 2,231.25 | 25% |
| C10: Tagged zip-up workwear | 1,318 | 1,318 | 1,318 | 25% |

Both declined unsupported numerical variant/condition adjustments and retained
the source amounts. Application arithmetic, not model arithmetic, gives:
`(1731.35 + 1392 + 2231.25 + 1318) / 4 = 1668.15`, rounded to the nearest USD 25
(half-up) = **USD 1,675 for both models**. GPT-5 took 11.3 seconds, Sol 6.2 seconds.
Requests were checked identical except model ID; both returned zero web-search calls.

This demonstrates agreement for this one constrained case, not a generally correct
market value or a guarantee of future consistency. The controlled prompt also
explicitly permits zero adjustment when unsupported, and prior adjustment narratives
were removed, so this result cannot isolate weights alone as the cause of the earlier
gap. It supports application-controlled source selection, weighting and arithmetic
as a direction to evaluate across more cases before changing production. Asking and
sold-displayed source amounts remain model-extracted, not independently verified payments.

## Fixed comparable pool experiment

Saved artifact: `tmp/model-evaluations/fixed_pool_20261016.json` (local only).
Two paid calls received the same target identity, NewWithTags condition and a
deterministic union of ten saved references: eight resale comparables and two
retail-only references. Requests were verified identical except model ID; both
had tools disabled and returned zero web-search calls. Both used low reasoning.
Full requests/responses, source evidence and its hash are retained. Recorded prices
were unchanged, including discounted prices; all facts remain model-extracted.
The pool also retains prior similarity/adjustment descriptions, not independently
curated source extracts; both models receive those same descriptions.

| Model | Estimate | Range | Confidence | Seconds |
| --- | --- | --- | --- | --- |
| GPT-5 | USD 2,050 | USD 1,700–2,400 | 55% | 65.4 |
| Sol | USD 1,675 | USD 1,300–2,250 | 46% | 57.0 |

This experiment additionally required explicit weights, adjusted target-condition
prices, and the weighted mean rounded to USD 25. It is not the production algorithm;
the change in prompt prevents a clean quantitative decomposition of earlier results.

| Comparable | Recorded USD | GPT-5 weight / adjusted USD | Sol weight / adjusted USD |
| --- | --- | --- | --- |
| Patchwork NWT | 1,731.35 | 10% / 1,601 | 20% / 1,731.35 |
| Used workwear | 2,000 | 10% / 2,300 | Excluded |
| Limited jacquard NWT | 3,500 | 15% / 2,975 | Excluded |
| Shearling-trim tagged | 2,437.50 | 15% / 2,145 | Excluded |
| Worn 2022 monogram | 906.50 | 3% / 1,586 | Excluded |
| Pristine tagged asking | 1,392 | 2% / 1,392 | 15% / 1,392 |
| Tagged sold-display | 2,231.25 | 25% / 2,231.25 | 30% / 2,231.25 |
| Tagged zip-up workwear | 1,318 | 20% / 1,318 | 35% / 1,318 |

Both assign zero weight to retail. GPT-5 uses all eight resale references, including
15% limited-edition discounts, a 12% shearling discount, a 15% used-to-NWT uplift,
and approximately 75% worn-to-NWT uplift. These are model judgments, not established
market adjustment coefficients. Sol uses four tagged references, declining numerical
adjustments for material/edition/condition differences it cannot quantify.

Arithmetic checks: GPT-5 weights sum to 1 and yield USD 2,054.9325, correctly rounded
to 2,050. Sol weights sum to 1 and yield USD 1,685.745, correctly rounded to 1,675.
As an offline diagnostic, removing GPT-5's four extra references and renormalizing
its remaining weights gives approximately USD 1,771; the reduction from USD 2,055
shows how strongly inclusion/adjustment of those references affects this output.
This is not a new model prediction or proof of a correct value.

Conclusion: even with the same evidence, comparable selection, weights and inferred
adjustments produce different values. Search differences alone do not explain the
observed disagreement. This single exploratory run does not rank accuracy or prove
cross-run stability. Implementation verification: 375 tests passed.

## Offline v4 summary-fallback replay

The same captured v3 responses were revalidated with `same-brand-comparables-v4`;
**zero model calls**. Native titles remain preferred. If absent, a model-written
source summary may support the comparable product name when the actual provider
search/open-page metadata includes that URL. This is recorded as model-reported
evidence, not independent verification of source content or payment. Generated
summaries cannot override an existing contradictory native title.

| Item | GPT-5 | Sol |
| --- | --- | --- |
| Louis Vuitton | USD 2,100 — qualified; 5 accepted resale sources | USD 1,700 — qualified; 3 accepted resale sources |
| Alice Cooper x John Varvatos | Needs review | Needs review |

Varvatos remains blocked by the separate collaboration/base-brand token-equality
limitation. The original captures are unchanged. Final replay artifact:
`tmp/model-evaluations/replayed_v4_summary_20261016.json` (local, Git-ignored).
An intermediate `replayed_v4_20261016.json` remains as an audit artifact; the final
replay additionally treats patchwork as a descriptive qualifier, allowing the
source summary to omit that qualifier while still supporting its core model name.

The version descriptions below are historical, not the current policy.

Current local revision `same-brand-comparables-v3` relaxes title matching for
labelled catalog IDs/sizes, leading collection years and descriptive qualifiers,
while retaining brand and distinctive-name support. The captured v3 run below is
current; v2/strict runs remain historical. Collaboration/base-brand normalization
remains unresolved.

The older strict rerun remains below for comparison.

## Captured v3 rerun and verified offline replay

Four paid calls used the same historical identities and user conditions. Raw results
and source metadata are saved locally, not published or committed:

- `tmp/model-evaluations/captured_v3_20261016.json`: exact requests, fixed identities,
  conditions, full provider responses/search metadata/usage, pre-validation values,
  post-validation values, policy version, timestamp and input-file SHA-256.
- `tmp/model-evaluations/replayed_v3_20261016.json`: replay with current validation,
  verified to reproduce all four decisions exactly with **zero provider calls**.

| Item / model | Original estimate | After validation | Seconds |
| --- | --- | --- | --- |
| Louis Vuitton / GPT-5 | USD 2,100 (60% confidence) | Needs review | 50.3 |
| Louis Vuitton / Sol | USD 1,700 (57% confidence) | USD 1,700 | 51.3 |
| Alice Cooper x John Varvatos / GPT-5 | USD 650 (55% confidence) | Needs review | 95.5 |
| Alice Cooper x John Varvatos / Sol | USD 650 (43% confidence) | Needs review | 52.6 |

Capture distinguishes model estimates from server abstention. GPT-5's LV response
contains **no native source titles** (Sol has four), so the source-title gate blocks
it even after relaxed word matching. This corrects the earlier assumption that
wording qualifiers alone explained GPT-5's rejections; missing metadata is confirmed
for this run, not retrospectively proven for prior runs. Both Varvatos responses
still fail full collaboration-name versus base-brand equality; the original USD 650
estimates are now available for offline experiments. Do not present these rejected
values as approved listing prices.

Local replay can isolate changes to metadata requirements, title matching and brand
normalization without rerunning models. It cannot emulate new prompts or research.
See [offline replay instructions](AI_MODEL_LIFECYCLE.md#offline-rule-replay).
Capture/replay implementation verification: 367 tests passed; artifacts use file
permissions 0600 and their directory is Git-ignored. Production is unchanged.

## Relaxed same-brand rerun

Four calls used the same saved identities, normalized conditions and low reasoning,
with `same-brand-comparables-v2`. No production data or configuration was changed.

| Case | GPT-5 | Sol |
| --- | --- | --- |
| Louis Vuitton / NewWithTags | Needs review; 125.9 sec | USD 1,700; confidence 55%; 53.5 sec |
| Alice Cooper x John Varvatos / LikeNew | Needs review; 82.4 sec | Needs review; 56.2 sec |

Sol's accepted LV estimate infers a USD 1,350–2,200 range from same-brand monogram
denim jackets: one advertised at USD 1,392 and another sold page displaying
USD 2,231.25. Those are model-extracted prices, not independently verified payments.
It explicitly describes variant uncertainty and does not apply an MSRP percentage.

The run exposed remaining validator limitations rather than demonstrating that
both models could apply the relaxed policy successfully:

- GPT-5 LV: every candidate was rejected for `no_independent_search_title_support`.
  Its generated model names include item IDs, sizes and descriptive qualifiers;
  the all-token source-title check can reject such names. The artifact does not
  retain original search titles, so missing metadata versus wording differences
  cannot be distinguished retrospectively for every URL.
- Both Varvatos calls: every candidate was rejected for
  `identity_mismatch_or_ambiguous_model`. Saved identity brand is
  `Alice Cooper x John Varvatos`, but source brands are `John Varvatos`; strict brand
  token equality incorrectly blocks the base brand of the collaboration.
- The validator clears rejected prices/rationales and this harness does not retain
  pre-validation outputs. No numeric prices can responsibly be reported for those
  three rejected calls.

Before treating this policy as ready, fix collaboration/base-brand normalization
with evidence-backed brand aliases (without merging unrelated brands or diffusion
lines), make title matching resilient to non-model qualifiers, and retain provider
metadata plus pre-validation outputs in local evaluation artifacts. These follow-up
fixes are not implemented by this rerun. Raw results:
`tmp/model_upgrade_same_brand_20261016.json` (local only).

## Strict exact-model rerun

After the initial comparison, `exact-model-v1` added mandatory structured
comparables and server-side source-title checks. Both models were rerun on the
same two saved identities and canonical user conditions, without production writes.

| Case | GPT-5 result / seconds | Sol result / seconds |
| --- | --- | --- |
| Louis Vuitton / NewWithTags | Needs review / 78.3 | Needs review / 32.8 |
| Alice Cooper x John Varvatos / LikeNew | Needs review / 37.8 | Needs review / 29.2 |

Neither supplied a qualified exact-model, confirmed-variant resale anchor. No
numeric price survives the policy, avoiding the earlier guesses from related items.
For LV, Sol specifically recognized that the official $3,300 retail reference has a
zipper/ribbed collar while the supplied identity describes button-front construction;
that reference is not confirmed as the subject variant. GPT-5 listed related
resale variants but no exact resale evidence. For Varvatos, GPT-5 found generic or
different-edition references; Sol treated the Otrium collaboration listing as
unconfirmed for the numbered special edition. Retail-only evidence cannot establish
a resale value under this policy.

This is conservative abstention, not proof that either model is more accurate.
Search-title checks are an additional safeguard, not verification of page content,
condition or paid transaction prices. Raw rerun results are local only at
`tmp/model_upgrade_strict_20261016.json`. Existing manual-review/admin-alert handling
is used by the application; this read-only benchmark did not create reviews or emails.

Regression verification after implementation: 350 tests passed.

## Initial comparison (before strict policy)

Account access checks succeeded for gpt-5, gpt-5-mini, gpt-6.1-sol and gpt-6-luna.
Four paid pricing calls compared two saved historical identities. Both models used
the same identity, condition, current pricing prompt, web_search tool and low
reasoning effort. Calls ran with concurrency two; these are single-run timings,
not controlled latency percentiles. No listings or persisted identities were written.

| Case / user condition | GPT-5 price / seconds | Sol price / seconds | Difference |
| --- | --- | --- | --- |
| 1 / NewWithTags | USD 2,000 / 69.8 | USD 1,550 / 42.6 | −22.5% |
| 2 / LikeNew | USD 550 / 82.9 | USD 650 / 47.6 | +18.2% |

All four calls returned parseable valuation objects and primary estimates matching
the requested condition. The application selected each primary estimate without a
condition mismatch. Source counts were 7 versus 3 and 5 versus 3 respectively;
counts do not establish relevance, reliability or independent evidence.

A synthetic Luna chat call returned strict structured JSON in 1.71 seconds and
requested missing photos without inventing an item. Usage: 61 input and 45 output
tokens. This did not exercise the full application prompt, workflow or tool safety.

The first local harness attempt rejected historical display labels ("New With Tags"
and "Like New") before provider calls. Normalizing those labels fixed the harness;
the successful run used canonical NewWithTags and LikeNew conditions.

## Limits and remaining gates

- Only two historical cases; no New case, human-reviewed price truth or representative
  category coverage. Price differences cannot be labeled accuracy improvements.
- Identity was reused from an earlier artifact, not re-verified against current photos.
- No repeated-run variance, token-cost comparison, independent source audit or full
  chat evaluation yet. The pricing wrapper does not retain response token usage.
- Raw results remain in ignored local `tmp/model_upgrade_smoke_20261016_run2.json`;
  do not publish source photos, identity data or user information in GitHub artifacts.
- Next: curate 30–50 permissioned examples with human reference bands, review actual
  comparables for these two divergences, then run repeated pricing and full chat tests.
  Follow [the lifecycle policy](AI_MODEL_LIFECYCLE.md) before approval/deployment.
