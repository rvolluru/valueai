#!/usr/bin/env python3
"""Evaluation only: app-scheduled per-site research, then shared no-search valuation.

Hosted search may rewrite the requested queries. The application enforces site
coverage/domain filters and records actual searches, not the internal query planner.
Extracted page facts are model-reported, not independently verified transactions.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/api"), str(ROOT / "packages/brand/src"), str(ROOT / "scripts")]
from app.gpt_item_profile import GptItemProfiler
from evaluate_fixed_comparables import build_payload
from app.controlled_research import (
    SITES, research_plan, research_payload, canonical_url, candidate_rejection, shared_evidence,
)

VERSION = "application-controlled-research-eval-v1"
VALUATION_POLICY = "shared-research-source-neutral-v2"
RETAIL_VALUATION_POLICY = "shared-research-production-retail-guidance-v3"


def request(payload, key):
    started = time.monotonic()
    result = dict(request=payload)
    try:
        with httpx.Client(timeout=240) as client:
            response = client.post("https://api.openai.com/v1/responses", json=payload,
                                   headers={"Authorization": "Bearer " + key})
        result.update(http_status=response.status_code, raw_response=response.json())
        response.raise_for_status()
        value = GptItemProfiler._parse_json_relaxed(GptItemProfiler._extract_output_text(result["raw_response"]))
        if not isinstance(value, dict):
            raise ValueError("No structured response")
        result.update(status="returned", data=value)
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def audit_valuation(result, evidence, preserve_retail_guidance=False):
    if result.get("status") != "returned":
        return dict(status="request_failed")
    data = result["data"]
    expected = {r["id"]: r for r in evidence["comparables"]}
    assessments = data.get("comparable_assessments") or []
    errors = []
    ids = [r.get("id") for r in assessments]
    if len(ids) != len(expected) or set(ids) != set(expected):
        errors.append("missing_duplicate_or_unknown_assessment_ids")
    allowed = {canonical_url(r["url"]) for r in evidence["comparables"]}
    for name in ("resale_price_estimate", "retail_price_estimate"):
        for ref in (data.get(name) or {}).get("references") or []:
            if canonical_url(ref.get("url")) not in allowed:
                errors.append("reference_outside_fixed_pool")
    for row in data.get("pricing_comparables") or []:
        original = next((v for v in expected.values() if canonical_url(v["url"]) == canonical_url(row.get("url"))), None)
        if not original or any(row.get(k) != original.get(k) for k in ("price", "currency", "price_type")):
            errors.append("changed_or_invented_comparable_facts")
    used = [r for r in assessments if r.get("used")]
    if not preserve_retail_guidance and any(expected.get(r.get("id"), {}).get("source_role") != "resale" and r.get("weight", 0) != 0 for r in assessments):
        errors.append("retail_has_resale_weight")
    if preserve_retail_guidance:
        retail_usage = data.get("retail_guidance_assessment") or {}
        context_ids = retail_usage.get("retail_reference_ids") or []
        if any(expected.get(key, {}).get("source_role") != "retail" for key in context_ids):
            errors.append("invalid_retail_context_ids")
        exact_id = retail_usage.get("verified_exact_msrp_id")
        if exact_id and (exact_id not in context_ids or expected.get(exact_id, {}).get("variant_match") != "confirmed"):
            errors.append("unsupported_exact_target_msrp_claim")
        if retail_usage.get("retail_context_used") and not context_ids:
            errors.append("retail_context_claim_without_references")
        conversions = data.get("retail_derived_resale_anchors") or []
        conversion_ids = [row.get("id") for row in conversions]
        retail_used = {r.get("id") for r in used if expected.get(r.get("id"), {}).get("source_role") == "retail"}
        if len(conversion_ids) != len(set(conversion_ids)) or set(conversion_ids) != retail_used:
            errors.append("missing_or_unexpected_retail_conversion")
        resale_used = {r.get("id") for r in used if expected.get(r.get("id"), {}).get("source_role") == "resale"}
        for conversion in conversions:
            support = conversion.get("supporting_resale_ids") or []
            if not support or not set(support) <= resale_used or not str(conversion.get("conversion_rationale") or "").strip():
                errors.append("unsupported_retail_to_resale_conversion")
    if any(not r.get("used") and (r.get("weight") != 0 or r.get("adjusted_price") is not None) for r in assessments):
        errors.append("unused_comparable_has_weight_or_price")
    valid_numbers = all(isinstance(r.get("weight"), (int, float)) and not isinstance(r.get("weight"), bool)
        and math.isfinite(r["weight"]) and 0 <= r["weight"] <= 1
        and isinstance(r.get("adjusted_price"), (int, float)) and not isinstance(r.get("adjusted_price"), bool)
        and math.isfinite(r["adjusted_price"]) and r["adjusted_price"] > 0 for r in used)
    mean, calculated_price = None, None
    if used:
        if not valid_numbers or abs(sum(r["weight"] for r in used) - 1) > .001:
            errors.append("invalid_weights_or_adjusted_prices")
        else:
            exact_mean = sum(Decimal(str(r["weight"])) * Decimal(str(r["adjusted_price"])) for r in used)
            mean = float(exact_mean)
            calculated_price = float((exact_mean / Decimal(25)).quantize(Decimal(1), rounding=ROUND_HALF_UP) * Decimal(25))
            if (data.get("resale_price_estimate") or {}).get("estimated_price") != calculated_price:
                errors.append("model_estimate_not_rounded_weighted_mean")
    elif (data.get("resale_price_estimate") or {}).get("estimated_price") is not None:
        errors.append("price_without_used_evidence")
    return dict(status="passed_experimental_controls" if not errors else "failed_experimental_controls",
                errors=sorted(set(errors)), weighted_mean=mean, code_estimated_price=calculated_price,
                approved_for_publication=False)


def valuation_payload(profiler, evidence, preserve_retail_guidance=False):
    payload = build_payload(profiler, evidence)
    # The production prompt has an older eBay-sold-only sourcing rule. This
    # experiment must not treat the same price type differently by website.
    for message in payload["input"]:
        for part in message.get("content", []):
            if part.get("type") == "input_text":
                part["text"] = part["text"].replace("eBay (Sold listings ONLY)", "eBay (asking or sold-displayed evidence)")
    payload["instructions"] += (
        " SOURCE-NEUTRAL ELIGIBILITY: All supplied resale asking and sold_displayed references are eligible regardless "
        "of website. There is NO eBay-sold-only restriction in this experiment. Do not prefer or reject a candidate merely "
        "because of its website. Judge product/variant, condition, price type and evidence quality. "
        "Do not silently treat asking as sold or infer final payments. Explain any asking-to-clearing adjustment. "
        "Original source prices must remain unchanged; adjustments are explicit model judgments."
    )
    payload["max_output_tokens"] = 10000
    if preserve_retail_guidance:
        # Preserve the production valuation rules already in the user prompt,
        # removing only the fixed-evidence experiment's extra retail prohibition.
        payload["instructions"] = payload["instructions"].replace(
            "Retail prices are MSRP context only and must have zero resale weight.",
            "Preserve the production retail/MSRP valuation guidance in the user prompt.")
        payload["instructions"] += (
            " PRODUCTION RETAIL GUIDANCE IS PRESERVED: Contemporary apparel NewWithTags uses 45%-60% of full original MSRP "
            "unless sold comparables explicitly demonstrate lower. Luxury/heritage brands, including Louis Vuitton, "
            "must NOT be capped at 60% MSRP: anchor to supported same-brand secondary-market evidence as required by "
            "the production policy. These brand-tier rules override a generic percentage rule. "
            "No unsupported MSRP-percentage fallback. Distinguish verified exact-target MSRP from related-model retail "
            "context; current supplied official variants are unconfirmed, so do not claim exact target MSRP. "
            "Do not suppress useful related retail context just because exact MSRP is unknown; explicitly report how "
            "retail evidence affects or does not affect your judgment. No forced retail weight or fixed retail share. "
            "A retail source may inform context, ranges or condition/variant interpretation without being a weighted "
            "resale anchor. Never average raw retail sticker prices into resale prices. If a retail reference is used "
            "as a weighted resale estimate, adjusted_price must be an explained retail-to-resale conversion supported "
            "by supplied resale evidence; record its ID, supporting used resale IDs and conversion rationale in "
            "retail_derived_resale_anchors. Otherwise that array is empty. For context-only retail assessments return "
            "used=false, weight=0 and adjusted_price=null; record context usage separately in retail_guidance_assessment. "
            "The weighted mean requirement applies to all used, explicitly adjusted resale-value anchors."
        )
        schema = payload["text"]["format"]["schema"]
        guidance = {
            "pricing_rule": {"type": "string", "enum": ["contemporary_nwt_msrp_range", "luxury_secondary_market", "other"]},
            "retail_context_used": {"type": "boolean"},
            "retail_reference_ids": {"type": "array", "items": {"type": "string"}},
            "verified_exact_msrp_id": {"type": ["string", "null"]},
            "explanation": {"type": "string"},
        }
        conversion = {"id": {"type": "string"},
            "supporting_resale_ids": {"type": "array", "items": {"type": "string"}},
            "conversion_rationale": {"type": "string"}}
        schema["properties"]["retail_guidance_assessment"] = {"type": "object", "additionalProperties": False,
            "properties": guidance, "required": list(guidance)}
        schema["properties"]["retail_derived_resale_anchors"] = {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "properties": conversion, "required": list(conversion)}}
        schema["required"].extend(["retail_guidance_assessment", "retail_derived_resale_anchors"])
    return payload


def save(path, artifact):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("r+" if path.exists() else "x") as handle:
        os.chmod(path, 0o600)
        json.dump(artifact, handle, indent=2)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Saved identity artifact, or controlled research artifact with --reuse-research")
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true", help="Authorize at most 8 research and 2 valuation calls")
    parser.add_argument("--research-only", action="store_true")
    parser.add_argument("--reuse-research", action="store_true", help="Use saved research; only two new valuation calls")
    parser.add_argument("--audit-only", action="store_true", help="Recheck saved results offline; no keys or provider calls")
    parser.add_argument("--preserve-retail-guidance", action="store_true", help="Use production brand-tier retail rules instead of the zero-retail-weight experiment")
    args = parser.parse_args()
    source, output = Path(args.input), Path(args.output)
    if output.exists() or source.resolve() == output.resolve():
        parser.error("Output must be a new path")
    incoming = json.loads(source.read_text())
    if args.audit_only:
        if args.execute or args.research_only or args.reuse_research:
            parser.error("--audit-only cannot be combined with execution/research flags")
        if incoming.get("experiment") != VERSION or not incoming.get("results") or not incoming.get("evidence"):
            parser.error("Expected a controlled valuation artifact with saved evidence/results")
        artifact = copy.deepcopy(incoming)
        for result in artifact["results"]:
            result["audit"] = audit_valuation(result, artifact["evidence"], artifact.get("preserve_retail_guidance", False))
        artifact.update(audited_at=datetime.now(timezone.utc).isoformat(), audit_version="decimal-arithmetic-v2",
                        audit_source=str(source), provider_calls_this_run=0)
        save(output, artifact)
        print(json.dumps(dict(audited=len(artifact["results"]), provider_calls=0)), flush=True)
        return 0
    if args.reuse_research:
        if incoming.get("experiment") != VERSION or not incoming.get("research_complete"):
            parser.error("Expected a completed controlled research artifact")
        artifact = copy.deepcopy(incoming)
        artifact.update(source=str(source), results=[], complete=False)
    else:
        run = next((r for r in incoming.get("results", []) if r.get("case") == 1), None)
        identity = incoming.get("identity") or ((run or {}).get("capture") or {}).get("identity")
        condition = incoming.get("condition") or (run or {}).get("condition")
        if not isinstance(identity, dict) or not identity.get('candidate_brand') or not identity.get('candidate_model') or not condition:
            parser.error("Input requires saved identity and condition, or a captured case-1 identity")
        artifact = dict(experiment=VERSION, source=str(source), identity=identity,
            condition=condition, research_model="gpt-5", research=[], results=[],
            research_complete=False, complete=False, approved_for_publication=False)
    artifact["created_at"] = datetime.now(timezone.utc).isoformat()
    artifact["preserve_retail_guidance"] = args.preserve_retail_guidance
    artifact["valuation_policy"] = RETAIL_VALUATION_POLICY if args.preserve_retail_guidance else VALUATION_POLICY
    plans = research_plan(artifact["identity"])
    print(json.dumps(dict(execute=args.execute, research_calls=0 if args.reuse_research else len(plans),
                         valuation_calls=0 if args.research_only else 2)), flush=True)
    if not args.execute:
        return 0
    load_dotenv(ROOT / ".env")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        parser.error("OPENAI_API_KEY required")
    save(output, artifact)
    if not args.reuse_research:
        def research(plan):
            return dict(plan=plan, **request(research_payload(plan, artifact["identity"], artifact["research_model"]), key))
        with ThreadPoolExecutor(max_workers=4) as pool:
            for future in as_completed([pool.submit(research, plan) for plan in plans]):
                result = future.result()
                artifact["research"].append(result)
                save(output, artifact)
                print(json.dumps(dict(site=result["plan"]["site"], status=result["status"],
                    candidates=len(result.get("data", {}).get("candidates", [])), seconds=result["elapsed_seconds"])), flush=True)
        artifact["research_complete"] = True
    evidence = shared_evidence(artifact)
    artifact["evidence"] = evidence
    encoded = json.dumps(evidence, sort_keys=True).encode()
    artifact["evidence_sha256"] = hashlib.sha256(encoded).hexdigest()
    save(output, artifact)
    if args.research_only:
        return 0
    if not any(r["source_role"] == "resale" for r in evidence["comparables"]):
        print("No eligible resale evidence; skipping valuation", flush=True)
        return 1
    def evaluate(model):
        profiler = GptItemProfiler.__new__(GptItemProfiler)
        profiler.openai_model, profiler.reasoning_effort = model, "low"
        payload = valuation_payload(profiler, evidence, args.preserve_retail_guidance)
        result = dict(model=model, evidence_sha256=artifact["evidence_sha256"], **request(payload, key))
        result["audit"] = audit_valuation(result, evidence, args.preserve_retail_guidance)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(evaluate, m) for m in ("gpt-5", "gpt-6.1-sol")]):
            result = future.result()
            artifact["results"].append(result)
            save(output, artifact)
            print(json.dumps(dict(model=result["model"], status=result["status"], audit=result["audit"]["status"],
                                 seconds=result["elapsed_seconds"])), flush=True)
    artifact["complete"] = True
    save(output, artifact)
    return int(any(r.get("status") != "returned" or r["audit"]["status"] != "passed_experimental_controls"
                   for r in artifact["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
