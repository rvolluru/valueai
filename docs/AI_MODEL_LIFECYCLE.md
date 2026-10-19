# AI model upgrades and retirement policy

Updated October 18, 2026. Owner: Jouft engineering/release maintainer.
Current-model runtime changes deployed in release `635ec54` on October 16, 2026.
Release `9bbe8f5`, workflow `39193566712`, enables user-approved sticky pricing
cohorts in production: existing listings retain GPT-5; new fresh listings use Sol.
Chat candidates and application-controlled research remain unpromoted/disabled.

## Inventory and candidates

| Role | Current production model | Candidate | Decision |
| --- | --- | --- | --- |
| Pricing | gpt-5 (existing), gpt-6.1-sol (new fresh) | Further upgrades | Sticky cohorts deployed |
| OpenAI OCR fallback | gpt-5 | None | Retain |
| Application/listing chat | gpt-5-mini | gpt-6-luna, reasoning low | Evaluate before promotion |
| Identity, OCR and photo coverage | gemini-3.8-flash | Same | Retain; evaluate temperature separately |
| Mannequin images | gemini-3-pro-image | Same | Retain |

Production inventory was inspected October 16. Check both API and worker task
definitions, environment overrides and secret-backed overrides at every release;
repository defaults alone do not establish what production runs. Also search for
legacy helpers, deployment smoke-test models and evaluation-script defaults.
The candidate environment fragment is `config/ai-model-candidates.env`; it is
deliberately not loaded automatically. Existing defaults remain unchanged.

## Review cadence and retirement alerts

- Weekly: release maintainer reviews official OpenAI and Google deprecation pages,
  model pages and account notices. Record review date and findings in this file via
  PR. The scheduled GitHub workflow is a reminder, not an automated deprecation detector.
- Monthly: compare newer models for each role; newer is not automatically better.
- Before every release: verify account access, model availability, supported API,
  reasoning levels, tools, structured output, image inputs, pricing and quotas.
- When a shutdown is announced: record exact provider date and replacement here;
  start evaluation immediately. Target migration at least 30 days before shutdown,
  escalate at 14 days and treat unresolved migration at 7 days as release-critical.
  For shorter notice, escalate immediately. Never invent a retirement date from a
  deprecated label alone.

Verified October 16: OpenAI's June 11 notice schedules
`gpt-5-2025-08-07`, `gpt-5-mini-2025-08-07` and `gpt-5-nano-2025-08-07` for shutdown
on **December 11, 2026**. Saved pricing responses confirm the `gpt-5` alias currently
resolves to the listed GPT-5 snapshot. Do not assume aliases avoid retirement.
Target a validated migration by November 11 (30-day buffer); the candidate models
remain unapproved because the latest-ten compatibility pilot failed its provisional
tolerance. See [the official notice](https://developers.openai.com/api/docs/deprecations#2026-06-11-gpt-5-and-o3-model-deprecations).

Next manual review: October 23, 2026. Git history versions all decisions.

## Evaluation gate

October 18 production rollout: user-approved sticky pricing cohorts keep existing
listings on GPT-5, allow genuinely new listings requiring fresh pricing to use
`gpt-6.1-sol`, and retain that assignment for later reanalysis. Eligible duplicates
reuse existing evidence/model rather than forcing a new Sol call. The default
application feature flag defaults off, but production API and workers explicitly
enable it. Migration 0008 grandfathered existing listings before rollout. Deployed
settings, Sol access, service stability and public health checks passed. This limited
cohort rollout does not remove the
evaluation/migration requirements below. See the canonical process guide for the
assignment, provenance and retry rules.

Use 30–50 permissioned examples spanning categories, all three conditions,
missing evidence, weak identity, manual-review cases and prior failures. Keep
photos, identity, condition, prompts and reasoning fixed when comparing pricing
models. Run separate prompt experiments; do not conflate model and prompt changes.

The existing comparison script now supports a separate candidate profiler, passes
the user condition to both calls, refuses incomplete evidence for model comparisons,
and records both model IDs. It does not write listings or reuse production pricing.
It makes paid provider calls and writes sensitive source data locally; never commit
the input CSV or result files. Obtain a curated dataset before running:

```sh
.venv/bin/python scripts/ab_test_openai_valuation.py --csv /private/tmp/model-eval.csv --limit 30 --openai-model gpt-5 --model-b gpt-6.1-sol --reasoning-effort low
```

Supply provider API keys through the environment, never command arguments. Gemini
identity is computed once per case and shared between A/B calls. The report is a
comparison artifact, not an automatic approval. Human reviewers must check:

- No schema failures or condition mismatch; no silent LikeNew substitution for New.
- No changed identity or invented attributes; manual-review behavior preserved.
- Comparable relevance, cited source quality and price error against human-approved
  reference bands are no worse than baseline. A smaller A/B price delta alone is
  not proof of accuracy.
- Record per-role latency, token cost, timeout rate and repeated-run variation;
  pricing must fit its 240-second provider budget and chat its 30-second budget.
- Chat: test ambiguous goals, missing evidence and hostile inputs; no unauthorized
  listing, trade or payment actions, and required confirmations remain intact.
- Gemini experiments: separately evaluate the recommended temperature 1.0 against
  the current lower-temperature extraction calls before changing production.

Account access was verified October 16 for all four OpenAI baseline/candidate
model IDs. A synthetic Luna structured-output smoke test completed in 1.71 seconds
and correctly requested missing photos (61 input / 45 output tokens). This is not
an end-to-end chat safety evaluation or promotion approval.

`scripts/evaluate_saved_valuation_models.py` supports paid read-only smoke
comparisons from historical local identity artifacts. It defaults to dry-run,
requires `--execute` for calls, uses two concurrent requests, normalizes user
condition labels and refuses to overwrite existing output. Historical cases have
no human gold prices and must not be treated as a representative benchmark.
No production model promotion has been completed.

### Offline rule replay

For a controlled valuation-only experiment, `scripts/evaluate_fixed_comparables.py`
builds a deterministic URL-deduplicated union of saved comparable facts for a case,
refusing conflicting facts or identities. Both models get identical evidence,
prompt, schema and low reasoning; tools are disabled. Each model reports which
sources it uses, normalized weights and adjusted target-condition prices; the
prompt requires the estimate to follow their weighted mean, rounded to USD 25.
This additional explicit aggregation instruction differs from the earlier free-search
experiment, so the comparison is exploratory, not a precise causal decomposition.
No production settings or listings are modified. Full requests/responses and the
fixed evidence hash are checkpointed locally with permissions 0600. The script
defaults to dry-run; `--execute` authorizes two paid calls. Saved prices are held
constant, including markdowns; source facts are model-extracted, not independently
verified. Experimental outputs are not automatically approved by production rules.

For the stricter adjustment-only comparison, add
`--fixed-weights --ids C3,C8,C9,C10` to the runner with a new output path. These
IDs identify the four tagged resale sources in the recorded LV union. Code fixes
weights at 25% each, removes prior adjustment recommendations from evidence, and
rejects missing/duplicate/extra IDs in the returned adjustments. Models cannot
select sources or supply weights/final estimates in this mode. Code computes the
arithmetic mean and rounds to USD 25, half-up. Any null adjustment leaves the final
price unavailable; weights are not redistributed. Source facts remain historical
model extractions, not verified final payments.

Captured evaluations are kept under Git-ignored `tmp/model-evaluations/`, with
file permissions 0600. Requests exclude authorization headers; artifacts still
contain potentially sensitive item/source data and should not be published.
Each successful call preserves request, identity, condition, full response/search
metadata, usage, parsed pre-validation prices and filtered results. Results are
checkpointed as calls complete. Input artifacts and replay outputs are kept separate;
existing output paths cannot be overwritten by a new run.

```sh
.venv/bin/python scripts/evaluate_saved_valuation_models.py --input tmp/model-evaluations/captured_v3_20261016.json --output tmp/model-evaluations/replayed_v3_20261016.json --replay
```

Replay performs zero provider calls and does not load credentials. Change validation
rules, run tests, then replay the same evidence to isolate the rule's effect. Prompt,
model or search-strategy changes still require new live runs. Older artifacts that
lack original provider responses/pre-validation valuations cannot be replayed.
See [the October 16 smoke report](AI_MODEL_EVALUATION_20261016.md) for measured
timings, pricing differences and the remaining evaluation gates.

## Promotion and rollback

### Migration compatibility with existing user values

Accuracy and backward compatibility are separate gates. Use the current deployed
profiler source/prompt for paired old/new pricing calls with the same frozen listing
identity, input hints, condition and reasoning. Do not simultaneously apply experimental
prompt/eligibility changes. Compare selected value AND both exact-condition endpoints
against the saved production result and against a fresh old-model run. Repeat some
old-model cases to distinguish existing variability from model-switch drift.

`scripts/evaluate_production_model_migration.py` implements a bounded 10-listing
read-only evaluation with 20 paired calls plus up to 10 optional old-model repeats.
It retains requests, full responses, source metadata, input and profiler hashes,
per-field percentage changes and errors locally. The initial tolerance is a
provisional 10% on all three metrics, not an approved production rule. Missing
endpoints are never counted as a pass. When selected endpoint fields are null,
exact-condition table endpoints are reported with explicit provenance; they must
not be described as values already displayed to users.

The latest-10 production snapshot is selected by created_at DESC/listing_id DESC,
without replacing failed or unanalyzed cases with older ones. The export uses a
temporary ECS task and a database connection with enforced read-only transactions;
it saves only listing analysis fields, not owner contact details, to encrypted
private S3 and a Git-ignored local artifact. No listing values are written back.

Do not auto-reprice existing listings on a model switch. Retain saved valuations;
large unexplained differences on reanalysis should be investigated rather than
silently published. Material evidence/condition/identity changes require separate
treatment. Compatibility results on ten cases are a pilot, not proof across all
inventory or a basis to fit a blanket correction on the same ten cases.

1. Attach reviewed metrics and failing-case resolutions to the PR. Keep pricing
   and chat promotions separate so failures are attributable.
2. Run staging/internal tests, including existing API and worker integration tests.
3. Set explicit model environment overrides in both relevant deployment surfaces;
   record exact model IDs, prompts/policy versions and release SHA here. If a stable
   snapshot is available and verified, prefer it to a moving alias.
4. Deploy only with approval; monitor errors, timeouts, manual-review volume,
   pricing distribution and cost before broad use. No percentage routing is
   implemented by this policy.
5. Roll back environment overrides to the previous available, non-retired model
   and redeploy. Preserve existing listing data. Do not mass-reanalyze old listings.

Saved identities include the Gemini model and identity-policy version in their
fingerprint. Changing identity models must invalidate incompatible identities;
changing pricing models must not change or cross-link listing ownership. Evaluation
calls bypass full-analysis reuse. Production cached analyses are not automatically
recomputed by selecting a new model: explicitly request fresh pricing when needed.

## Official sources

- [OpenAI deprecations](https://developers.openai.com/api/docs/deprecations)
- [OpenAI migration guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
- [Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Google deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- [Gemini 3 guidance](https://ai.google.dev/gemini-api/docs/gemini-3)
