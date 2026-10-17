import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.settings import Settings
from app.gpt_item_profile import GptItemProfiler

ROOT = Path(__file__).resolve().parents[1]


def test_production_defaults_not_silently_promoted():
    settings = Settings(_env_file=None)
    assert settings.gpt_item_profile_model == "gpt-5"
    assert settings.listing_assistant_model == "gpt-5-mini"
    assert settings.listing_assistant_reasoning_effort == "low"


def test_candidate_configuration_separate():
    text = (ROOT / "config/ai-model-candidates.env").read_text()
    assert "GPT_ITEM_PROFILE_MODEL=gpt-6.1-sol" in text
    assert "LISTING_ASSISTANT_MODEL=gpt-6-luna" in text


def test_model_comparison_accepts_same_prompt(monkeypatch):
    spec = importlib.util.spec_from_file_location("valuation_ab", ROOT / "scripts/ab_test_openai_valuation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("sys.argv", ["eval", "--csv", "cases.csv", "--model-b", "gpt-6.1-sol", "--limit", "30"])
    args = module.parse_args()
    assert args.prompt_b_file is None
    assert args.model_b == "gpt-6.1-sol"


def test_valuation_uses_supported_search_tool():
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.openai_model = "gpt-6.1-sol"
    profiler.reasoning_effort = "low"
    payload = profiler._build_openai_valuation_payload(content=[], gemini_profile={}, condition_grade="New")
    assert payload["tools"] == [{"type": "web_search"}]
    assert payload["reasoning"] == {"effort": "low"}


def test_saved_identity_eval_defaults_to_no_provider_calls(tmp_path):
    source = tmp_path / "cases.jsonl"
    output = tmp_path / "results.json"
    source.write_text(json.dumps({"gemini_profile": {"candidate_brand": "Example"}}) + "\n")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_saved_valuation_models.py"),
                             "--input", str(source), "--output", str(output)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["execute"] is False
    assert not output.exists()


def test_replay_revalidates_original_output_without_provider(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("saved_eval", ROOT / "scripts/evaluate_saved_valuation_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def forbid(*args, **kwargs):
        raise AssertionError("Replay must not create a provider or load credentials")
    monkeypatch.setattr(module, "GptItemProfiler", forbid)
    monkeypatch.setattr(module, "load_dotenv", forbid)
    source = tmp_path / "original.json"
    output = tmp_path / "replayed.json"
    original = {"results": [{"capture": {"identity": {"candidate_brand": "Example"},
        "raw_response": {"output": []}, "pre_validation": {"resale_price_estimate": {"estimated_price": 123},
        "pricing_comparables": []}}, "valuation": {"stale": True}}]}
    source.write_text(json.dumps(original))
    monkeypatch.setattr(sys, "argv", ["eval", "--input", str(source), "--output", str(output), "--replay"])
    assert module.main() == 0
    replayed = json.loads(output.read_text())
    assert replayed["provider_calls"] == 0
    assert replayed["results"][0]["valuation"]["pricing_evidence_policy"]["status"] == "needs_review"
    assert json.loads(source.read_text()) == original
    assert replayed["results"][0]["capture"]["pre_validation"]["resale_price_estimate"]["estimated_price"] == 123


def test_capture_preserves_provider_output_before_validation(monkeypatch):
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.timeout_s = 10
    profiler.openai_api_key = "not-saved"
    monkeypatch.setattr(profiler, "_build_openai_valuation_payload", lambda **kwargs: {"model": "test-model"})
    value = {"resale_price_estimate": {"estimated_price": 999}, "resale_price_breakdown": [], "pricing_comparables": []}
    raw = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(value), "annotations": []}]}], "usage": {"input_tokens": 12}}
    class Response:
        status_code = 200
        def json(self):
            return raw
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.gpt_item_profile.httpx.Client", Client)
    captured = {}
    result = profiler._call_openai_valuation(content=[], gemini_profile={"candidate_brand": "Example"}, condition_grade="New", capture=captured)
    assert result["resale_price_estimate"]["estimated_price"] is None
    assert captured["pre_validation"]["resale_price_estimate"]["estimated_price"] == 999
    assert captured["raw_response"] == raw
    assert "not-saved" not in json.dumps(captured)
