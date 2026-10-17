import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deployed_pricing_case", ROOT / "scripts/evaluate_deployed_pricing_case.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def setup_case(tmp_path, monkeypatch, image_revision="abc123"):
    source = tmp_path / "identity.json"
    source.write_text(json.dumps({"results": [{"case": 1, "capture": {"identity": {"candidate_brand": "Louis Vuitton"}}}]}))
    original = tmp_path / "case.jsonl"
    original.write_text(json.dumps({"row": {"Condition": "New With Tags", "Category": "Clothes", "Size": "54"}}))
    output = tmp_path / "result.json"
    monkeypatch.setattr("sys.argv", ["eval", "--input", str(source), "--original-case", str(original),
        "--output", str(output), "--revision", "abc123", "--task-definition", "api:171"])
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: "abc123\n")
    class Ecs:
        def describe_task_definition(self, **kwargs):
            return {"taskDefinition": {"taskDefinitionArn": "api:171", "containerDefinitions": [{
                "image": "registry/api:prod-126-" + image_revision,
                "environment": [{"name": "GPT_ITEM_PROFILE_MODEL", "value": "gpt-5"}],
                "secrets": [{"name": "OPENAI_API_KEY", "valueFrom": "secret-arn"}]}]}}
    monkeypatch.setattr(module.boto3, "client", lambda *a, **k: Ecs())
    return output


def test_dry_run_checks_revision_without_paid_calls_or_output(tmp_path, monkeypatch):
    output = setup_case(tmp_path, monkeypatch)
    assert module.main() == 0
    assert not output.exists()


def test_wrong_image_revision_rejected(tmp_path, monkeypatch):
    setup_case(tmp_path, monkeypatch, image_revision="different")
    with pytest.raises(SystemExit):
        module.main()


def test_results_saved_with_private_permissions(tmp_path):
    output = tmp_path / "result.json"
    module.save(output, {"complete": False})
    module.save(output, {"complete": True})
    assert json.loads(output.read_text()) == {"complete": True}
    assert output.stat().st_mode & 0o777 == 0o600
