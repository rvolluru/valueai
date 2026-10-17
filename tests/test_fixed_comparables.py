import copy
import importlib.util
from pathlib import Path

import pytest
from app.gpt_item_profile import GptItemProfiler

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fixed_eval", ROOT / "scripts/evaluate_fixed_comparables.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def artifact():
    capture = {"identity": {"candidate_brand": "Example"}, "pre_validation": {
        "pricing_comparables": [{"url": "https://example.com/item", "price": 100}]}}
    return {"results": [{"case": 1, "condition": "New", "capture": copy.deepcopy(capture)} for _ in range(2)]}


def test_union_deduplicates_same_evidence_and_keeps_original_unchanged():
    data = artifact()
    original = copy.deepcopy(data)
    evidence = module.fixed_evidence(data, 1)
    assert len(evidence["comparables"]) == 1
    assert evidence["comparables"][0]["id"] == "C1"
    assert data == original


def test_conflicting_prices_require_curation():
    data = artifact()
    data["results"][1]["capture"]["pre_validation"]["pricing_comparables"][0]["price"] = 200
    with pytest.raises(ValueError, match="Conflicting"):
        module.fixed_evidence(data, 1)


def test_fixed_payloads_only_differ_by_model_and_have_no_search():
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.reasoning_effort = "low"
    evidence = module.fixed_evidence(artifact(), 1)
    profiler.openai_model = "gpt-5"
    a = module.build_payload(profiler, evidence)
    profiler.openai_model = "gpt-6.1-sol"
    b = module.build_payload(profiler, evidence)
    assert a.pop("model") != b.pop("model")
    assert a == b
    assert a["tools"] == []
    assert "include" not in a
    assert "comparable_assessments" in a["text"]["format"]["schema"]["required"]


def weighted_evidence():
    return {"identity": {"candidate_brand": "Example"}, "user_condition": "NewWithTags",
            "comparables": [{"id": f"C{i}"} for i in range(1, 5)],
            "weights": {f"C{i}": .25 for i in range(1, 5)}}


def test_application_calculates_equal_weight_price_not_model_estimate():
    value = {"adjustments": [{"id": f"C{i}", "adjusted_price": p} for i,p in enumerate([1600,1400,2200,1300], 1)],
             "estimated_price": 9999}
    result = module.code_price(value, weighted_evidence())
    assert result["weighted_mean"] == 1625
    assert result["estimated_price"] == 1625


def test_null_adjustment_does_not_reweight_other_sources():
    value = {"adjustments": [{"id": f"C{i}", "adjusted_price": None if i==1 else 2000} for i in range(1,5)]}
    result = module.code_price(value, weighted_evidence())
    assert result["estimated_price"] is None
    assert result["weights"] == weighted_evidence()["weights"]


def test_missing_source_cannot_silently_change_fixed_set():
    with pytest.raises(ValueError, match="Missing"):
        module.code_price({"adjustments": [{"id": "C1", "adjusted_price": 1000}]}, weighted_evidence())


def test_fixed_weight_payload_has_no_model_control_over_selection_or_weights():
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.openai_model, profiler.reasoning_effort = "gpt-5", "low"
    payload = module.build_payload(profiler, weighted_evidence(), fixed_weights=True)
    schema = payload["text"]["format"]["schema"]
    fields = schema["properties"]["adjustments"]["items"]["properties"]
    assert set(fields) == {"id", "adjusted_price", "rationale"}
    assert payload["tools"] == []
    assert "25% each" in payload["instructions"]
