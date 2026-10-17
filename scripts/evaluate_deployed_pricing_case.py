#!/usr/bin/env python3
"""Read-only pricing replay using an isolated, explicitly deployed Git revision.

Frozen saved identity, fresh independent model research. Not an end-to-end upload,
identity-registry/cache, staging, publication or database-persistence test.
"""
import argparse
import copy
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("r+" if path.exists() else "x") as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, indent=2)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Saved identity capture artifact")
    parser.add_argument("--original-case", required=True, help="Original input JSONL; first row")
    parser.add_argument("--output", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--task-definition", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("Choose a new output path")
    incoming = json.loads(Path(args.input).read_text())
    saved = next(r for r in incoming["results"] if r.get("case") == 1)["capture"]["identity"]
    original = json.loads(Path(args.original_case).read_text().splitlines()[0])
    row = {key.casefold(): value for key, value in original["row"].items()}
    condition, category, item_size = "NewWithTags", row["category"].lower(), row.get("size")
    if row["condition"].replace(" ", "").lower() != "newwithtags":
        parser.error("Expected saved NWT case")
    revision = subprocess.check_output(["git", "rev-parse", args.revision], cwd=ROOT, text=True).strip()
    definition = boto3.client("ecs", region_name="us-east-1").describe_task_definition(
        taskDefinition=args.task_definition)["taskDefinition"]
    container = definition["containerDefinitions"][0]
    if not container["image"].endswith("-" + revision):
        parser.error("Task definition image does not match requested source revision")
    env = {r["name"]: r["value"] for r in container.get("environment", []) if r["name"].startswith("GPT_ITEM_PROFILE_")}
    # No secrets or production database configuration enter the artifact.
    artifact = dict(experiment="isolated-deployed-pricing-v1", created_at=datetime.now(timezone.utc).isoformat(),
        production_revision=revision, task_definition=definition["taskDefinitionArn"], image=container["image"],
        production_profiler_environment=env, source_identity_artifact=args.input,
        input=dict(condition=condition, category=category, size=item_size, user_brand_hint="unknown"),
        results=[], complete=False, approved_for_publication=False,
        limitations="Pricing-only read-only replay with frozen saved Gemini identity. No full upload/identification, production cache or DB/staging/publication writes. Sol is a model-only candidate, not a deployed model.")
    print(json.dumps(dict(revision=revision, production_model=env["GPT_ITEM_PROFILE_MODEL"],
        models=[env["GPT_ITEM_PROFILE_MODEL"], "gpt-6.1-sol"], execute=args.execute)), flush=True)
    if not args.execute:
        return 0
    load_dotenv(ROOT / ".env")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        parser.error("OPENAI_API_KEY required")
    with tempfile.TemporaryDirectory(prefix="valueai-deployed-pricing-") as task_dir:
        task_path = Path(task_dir)
        archive = task_path / "source.tar"
        with archive.open("wb") as handle:
            subprocess.run(["git", "archive", revision, "apps/api", "packages"], cwd=ROOT, stdout=handle, check=True)
        with tarfile.open(archive) as handle:
            handle.extractall(task_path, filter="data")
        sys.path[:0] = [str(task_path / p) for p in ("apps/api", "packages/brand/src", "packages/condition/src", "packages/valuation/src")]
        # Importing production main creates a local uploads directory; contain it
        # entirely in this disposable sandbox. Do not start the API or connect DB.
        os.environ.update(DATABASE_URL="sqlite:///:memory:", STORAGE_BACKEND="local",
            LOCAL_STORAGE_DIR=str(task_path / "local-data"))
        profiler_module = importlib.import_module("app.gpt_item_profile")
        evidence_module = importlib.import_module("app.pricing_evidence")
        identity_module = importlib.import_module("app.product_identity")
        main_module = importlib.import_module("app.main")
        identity = identity_module.extract_identity(saved)
        artifact["identity"] = identity
        artifact["pricing_policy_version"] = evidence_module.POLICY_VERSION
        artifact["source_files"] = {name: hashlib.sha256((task_path / "apps/api/app" / name).read_bytes()).hexdigest()
            for name in ("gpt_item_profile.py", "pricing_evidence.py", "product_identity.py", "main.py")}
        if not all(str(module.__file__).startswith(str(task_path)) for module in
                   (profiler_module, evidence_module, identity_module, main_module)):
            raise RuntimeError("Source isolation failed")
        save(output, artifact)

        def evaluate(model):
            profiler = profiler_module.GptItemProfiler(enabled=True,
                provider_order=env["GPT_ITEM_PROFILE_PROVIDER_ORDER"], openai_api_key=key, openai_model=model,
                gemini_api_key=None, gemini_model=env["GPT_ITEM_PROFILE_GEMINI_MODEL"],
                timeout_s=float(env["GPT_ITEM_PROFILE_TIMEOUT_S"]), max_images=int(env["GPT_ITEM_PROFILE_MAX_IMAGES"]),
                image_detail=env["GPT_ITEM_PROFILE_IMAGE_DETAIL"], reasoning_effort=env["GPT_ITEM_PROFILE_REASONING_EFFORT"])
            content = profiler._build_content(images=[], brand_name="unknown", category=category,
                item_size=item_size, condition_grade=condition, condition_source="user_input", item_description=None)
            capture = {}
            result = dict(model=model, role="deployed_baseline" if model == env["GPT_ITEM_PROFILE_MODEL"] else "model_only_candidate",
                          capture=capture)
            started = time.monotonic()
            try:
                # This deployed method builds the untouched request, makes its
                # real web-search call, parses and applies the deployed validator.
                valuation = profiler._call_openai_valuation(content=content, gemini_profile=copy.deepcopy(identity),
                    condition_grade=condition, capture=capture)
                if not isinstance(valuation, dict):
                    raise ValueError("No valuation returned")
                merged = profiler._merge_gemini_identification_with_openai_valuation(
                    gemini_profile=copy.deepcopy(identity), openai_valuation=valuation)
                selected = main_module.valuation_from_gpt_item_profile(merged, default_currency="USD", condition_grade=condition)
                target_row = next((r for r in merged.get("resale_price_breakdown", []) if r.get("condition_grade") == condition), None)
                result.update(status="returned", validated_profile=merged, selected_valuation=selected,
                              exact_condition_band=target_row)
            except Exception as exc:
                result.update(status="failed", error_type=type(exc).__name__)
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            print(json.dumps(dict(model=model, status=result["status"], seconds=result["elapsed_seconds"])), flush=True)
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in as_completed([pool.submit(evaluate, model) for model in (env["GPT_ITEM_PROFILE_MODEL"], "gpt-6.1-sol")]):
                artifact["results"].append(future.result())
                save(output, artifact)
        artifact["complete"] = True
        save(output, artifact)
    return int(any(r["status"] != "returned" for r in artifact["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
