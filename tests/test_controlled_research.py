import copy
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("controlled_research", ROOT / "scripts/evaluate_controlled_research.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
IDENTITY = {"candidate_brand": "Louis Vuitton", "candidate_model": "Monogram Denim Workwear Jacket"}


def candidate():
    return dict(url="https://poshmark.com/listing/jacket-123", brand="Louis Vuitton",
        model="Monogram Denim Workwear Jacket", title="Louis Vuitton Monogram Denim Workwear Jacket",
        product_type="jacket", material="denim", condition="LikeNew", price=1500,
        currency="USD", price_type="asking", price_quote="Listed at $1,500", summary="Monogram denim jacket",
        variant_differences="Not established")


def test_required_site_coverage_and_real_domain_filters():
    plan = module.research_plan(IDENTITY)
    assert len(plan) == 8
    assert {p["site"] for p in plan} == {*module.SITES, "Official brand"}
    for p in plan:
        payload = module.research_payload(p, IDENTITY, "gpt-5")
        assert payload["tools"][0]["filters"]["allowed_domains"] == p["domains"]
        assert payload["tool_choice"] == "required"
        assert all(q.startswith("site:") for q in p["queries"])


def test_no_guess_for_unknown_official_site():
    assert len(module.research_plan({**IDENTITY, "candidate_brand": "Unregistered"})) == 7


def test_candidate_requires_provenance_site_and_supported_price_excerpt():
    row = candidate()
    plan = dict(domains=["poshmark.com"], role="resale")
    retrieved = {row["url"]}
    assert module.candidate_rejection(row, plan, IDENTITY, retrieved) is None
    assert module.candidate_rejection(row, plan, IDENTITY, set()) == "no_provider_retrieval_provenance"
    assert module.candidate_rejection({**row, "price": 1550}, plan, IDENTITY, retrieved) == "price_missing_from_reported_excerpt"
    assert module.candidate_rejection({**row, "price_type": "retail"}, plan, IDENTITY, retrieved) == "wrong_price_type_for_source_role"
    assert module.candidate_rejection({**row, "brand": "Gucci"}, plan, IDENTITY, retrieved) == "different_or_ambiguous_brand"


def test_research_pool_deterministic_and_does_not_add_model_adjustments():
    row = candidate()
    research = dict(status="returned", plan=dict(site="Poshmark", domains=["poshmark.com"], role="resale"),
        data=dict(candidates=[row]), raw_response=dict(output=[dict(type="web_search_call",
            action=dict(sources=[dict(url=row["url"])]))]))
    artifact = dict(identity=IDENTITY, condition="NewWithTags", research=[research])
    original = copy.deepcopy(artifact)
    evidence = module.shared_evidence(artifact)
    assert evidence["comparables"][0]["id"] == "C1"
    assert "Not yet valued" in evidence["comparables"][0]["adjustment_explanation"]
    assert artifact == original


def test_tracking_parameter_dedup_preserves_item_query():
    assert module.canonical_url("https://poshmark.com/item?id=1&utm_source=openai") == "https://poshmark.com/item?id=1"


def test_valuation_audit_rejects_new_urls_and_retail_weights():
    evidence = dict(comparables=[dict(id="C1", url="https://louisvuitton.com/item", source_role="retail")])
    result = dict(status="returned", data=dict(comparable_assessments=[dict(id="C1", used=True,
        weight=1, adjusted_price=1000)], resale_price_estimate=dict(estimated_price=1000,
        references=[dict(url="https://poshmark.com/new")])))
    audit = module.audit_valuation(result, evidence)
    assert "reference_outside_fixed_pool" in audit["errors"]
    assert "retail_has_resale_weight" in audit["errors"]


def test_arithmetic_is_calculated_in_code_not_trusted_model_rationale():
    evidence = dict(comparables=[dict(id="C1", url="https://poshmark.com/item", source_role="resale")])
    result = dict(status="returned", data=dict(comparable_assessments=[dict(id="C1", used=True,
        weight=1, adjusted_price=2080.935)], resale_price_estimate=dict(estimated_price=2100, references=[])))
    audit = module.audit_valuation(result, evidence)
    assert audit["weighted_mean"] == 2080.935
    assert audit["code_estimated_price"] == 2075
    assert "model_estimate_not_rounded_weighted_mean" in audit["errors"]


def test_app_controlled_evidence_payloads_have_no_tools_and_only_model_differs():
    from app.gpt_item_profile import GptItemProfiler
    evidence = dict(identity=IDENTITY, user_condition="NewWithTags", comparables=[])
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.openai_model, profiler.reasoning_effort = "gpt-5", "low"
    a = module.valuation_payload(profiler, evidence)
    profiler.openai_model = "gpt-6.1-sol"
    b = module.valuation_payload(profiler, evidence)
    assert a["tools"] == b["tools"] == []
    assert "NO eBay-sold-only restriction" in a["instructions"]
    assert "eBay (Sold listings ONLY)" not in str(a["input"])
    a.pop("model")
    b.pop("model")
    assert a == b


def test_retail_guidance_mode_preserves_production_rules_without_forced_retail_weight():
    from app.gpt_item_profile import GptItemProfiler
    evidence = dict(identity=IDENTITY, user_condition="NewWithTags", comparables=[])
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.openai_model, profiler.reasoning_effort = "gpt-5", "low"
    payload = module.valuation_payload(profiler, evidence, preserve_retail_guidance=True)
    assert "must have zero resale weight" not in payload["instructions"]
    assert "45%-60%" in payload["instructions"]
    assert "must NOT be capped at 60% MSRP" in payload["instructions"]
    assert "Never average raw retail sticker prices" in payload["instructions"]
    assert "Contemporary Apparel (New With Tags)" in str(payload["input"])
    assert "retail_guidance_assessment" in payload["text"]["format"]["schema"]["required"]
    assert payload["tools"] == []
    profiler.openai_model = "gpt-6.1-sol"
    other = module.valuation_payload(profiler, evidence, preserve_retail_guidance=True)
    payload.pop("model")
    other.pop("model")
    assert payload == other


def test_retail_conversion_requires_used_resale_support_and_no_false_exact_msrp():
    evidence = dict(comparables=[dict(id="C1", url="https://louisvuitton.com/item", source_role="retail",
        variant_match="unconfirmed"), dict(id="C2", url="https://poshmark.com/item", source_role="resale")])
    result = dict(status="returned", data=dict(
        comparable_assessments=[dict(id="C1", used=True, weight=.5, adjusted_price=2000),
            dict(id="C2", used=True, weight=.5, adjusted_price=2000)],
        resale_price_estimate=dict(estimated_price=2000, references=[]),
        retail_guidance_assessment=dict(retail_reference_ids=["C1"], retail_context_used=True, verified_exact_msrp_id=None),
        retail_derived_resale_anchors=[dict(id="C1", supporting_resale_ids=["C2"], conversion_rationale="Supported conversion")]))
    assert module.audit_valuation(result, evidence, True)["errors"] == []
    assert "retail_has_resale_weight" in module.audit_valuation(result, evidence)["errors"]
    result["data"]["retail_guidance_assessment"]["verified_exact_msrp_id"] = "C1"
    result["data"]["retail_derived_resale_anchors"][0]["supporting_resale_ids"] = []
    audit = module.audit_valuation(result, evidence, True)
    assert "unsupported_exact_target_msrp_claim" in audit["errors"]
    assert "unsupported_retail_to_resale_conversion" in audit["errors"]


def test_retail_context_only_can_inform_guided_valuation_without_forced_weight():
    evidence = dict(comparables=[dict(id="C1", url="https://louisvuitton.com/item", source_role="retail"),
        dict(id="C2", url="https://poshmark.com/item", source_role="resale")])
    result = dict(status="returned", data=dict(comparable_assessments=[
        dict(id="C1", used=False, weight=0, adjusted_price=None),
        dict(id="C2", used=True, weight=1, adjusted_price=2000)],
        resale_price_estimate=dict(estimated_price=2000, references=[]), retail_derived_resale_anchors=[],
        retail_guidance_assessment=dict(retail_reference_ids=["C1"], retail_context_used=True, verified_exact_msrp_id=None)))
    assert module.audit_valuation(result, evidence, True)["status"] == "passed_experimental_controls"
