import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("migration_eval", ROOT / "scripts/evaluate_production_model_migration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_compatibility_requires_value_and_both_endpoints_within_tolerance():
    baseline = {"value": 100, "low": 80, "high": 120}
    assert module.deltas(baseline, {"value": 105, "low": 84, "high": 126})["within_tolerance"]
    result = module.deltas(baseline, {"value": 105, "low": 84, "high": 150})
    assert not result["within_tolerance"]
    assert result["percent_change"]["high"] == 25


def test_missing_band_is_not_silently_compatible():
    assert not module.deltas({"value": 100, "low": None, "high": None},
                             {"value": 100, "low": 80, "high": 120})["within_tolerance"]


def test_saved_null_selected_endpoints_use_only_exact_condition_table():
    profile = {"resale_price_breakdown": [
        {"condition_grade": "New", "estimated_price": 110, "range_low": 90, "range_high": 130},
        {"condition_grade": "LikeNew", "estimated_price": 70, "range_low": 60, "range_high": 80}]}
    result = module.band(profile, "New", selected={"estimated_value": 110, "range_low": None, "range_high": None})
    assert result["value"] == 110
    assert (result["low"], result["high"]) == (90, 130)
    assert result["endpoint_source"] == "exact_condition_table"


def test_production_prompt_builds_without_images_and_only_model_changes():
    cls, sha = module.production_profiler("51bb1bd")
    profiler = cls.__new__(cls)
    profiler.max_images, profiler.image_detail, profiler.reasoning_effort = 6, "auto", "low"
    content = profiler._build_content(images=[], brand_name="Example", category="clothes", item_size="M",
        condition_grade="New", condition_source="user_input", item_description=None)
    profiler.openai_model = "gpt-5"
    a = profiler._build_openai_valuation_payload(content=content, gemini_profile={"candidate_brand": "Example"}, condition_grade="New")
    profiler.openai_model = "gpt-6.1-sol"
    b = profiler._build_openai_valuation_payload(content=content, gemini_profile={"candidate_brand": "Example"}, condition_grade="New")
    assert a.pop("model") != b.pop("model")
    assert a == b
    assert len(sha) == 64


def test_report_is_offline_and_counts_all_band_fields(tmp_path):
    baseline = {"value": 100, "low": 80, "high": 120}
    case = {"case": 1, "title": "Example", "baseline": baseline}
    results = [{"case": 1, "model": model, "repeat": 1, "status": "returned", "band": baseline}
               for model in ("gpt-5", "gpt-6.1-sol")]
    source = tmp_path / "captured.json"
    source.write_text(json.dumps({"complete": True, "production_revision": "51bb1bd", "cases": [case], "results": results}))
    target = tmp_path / "report.md"
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/report_model_migration.py"),
        "--input", str(source), "--output", str(target)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "1/1 pass value + both endpoints" in target.read_text()
