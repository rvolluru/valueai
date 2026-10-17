#!/usr/bin/env python3
"""Paid, read-only model comparison using fixed identities from a prior local artifact."""
import argparse
import copy
import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/api"), str(ROOT / "packages/brand/src")]
from dotenv import load_dotenv
from app.gpt_item_profile import GptItemProfiler
from app.pricing_evidence import POLICY_VERSION, validate_valuation


def replay_results(artifact):
    """Pure local revalidation: never instantiates a provider or loads API keys."""
    results = copy.deepcopy(artifact["results"])
    for result in results:
        captured = result.get("capture") or {}
        if not all(isinstance(captured.get(k), dict) for k in ("identity", "raw_response", "pre_validation")):
            raise ValueError("Artifact lacks replay evidence; use a captured live run, not an old filtered result.")
        result["valuation"] = validate_valuation(captured["pre_validation"], captured["identity"], captured["raw_response"])
        result["replayed_policy_version"] = POLICY_VERSION
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--execute", action="store_true", help="Authorize paid provider calls")
    parser.add_argument("--replay", action="store_true", help="Revalidate captured responses locally; no network or API keys")
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("limit must be 1..50")
    source = Path(args.input)
    target = Path(args.output)
    if source.resolve() == target.resolve() or target.exists():
        parser.error("output must be a new file, different from input")
    if args.replay and args.execute:
        parser.error("--replay and --execute cannot be combined")
    def save(artifact):
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "r+" if target.exists() else "x"
        with target.open(mode) as handle:
            os.chmod(target, 0o600)
            json.dump(artifact, handle, indent=2)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    if args.replay:
        artifact = json.loads(source.read_text())
        try:
            results = replay_results(artifact)
        except (ValueError, KeyError) as exc:
            parser.error(str(exc))
        save({**artifact, "source_artifact": str(source), "results": results,
              "replayed_at": datetime.now(timezone.utc).isoformat(), "policy_version": POLICY_VERSION,
              "provider_calls": 0, "approved": False})
        print(json.dumps({"replayed": len(results), "provider_calls": 0, "output": str(target)}))
        return 0
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()][:args.limit]
    if not rows or any(not isinstance(row.get("gemini_profile"), dict) for row in rows):
        parser.error("each case needs a saved Gemini identity")
    print(json.dumps({"cases": len(rows), "calls": len(rows) * 2, "execute": args.execute}), flush=True)
    if not args.execute:
        return 0
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY required")

    def evaluate(task):
        index, row, model = task
        profiler = GptItemProfiler(enabled=True, provider_order="hybrid",
            openai_api_key=os.environ["OPENAI_API_KEY"], openai_model=model,
            gemini_api_key=None, gemini_model="gemini-3.8-flash", timeout_s=240,
            max_images=6, image_detail="auto", reasoning_effort="low", vertex_search_enabled=False)
        condition = row.get("summary", {}).get("input_condition")
        if not condition:
            condition = next((v for k, v in row.get("row", {}).items() if k.lower() == "condition"), None)
        condition = {"new": "New", "likenew": "LikeNew", "newwithtags": "NewWithTags"}.get(
            str(condition or "").replace(" ", "").lower(), condition)
        result = {"case": index, "model": model, "condition": condition}
        result["capture"] = {}
        started = time.monotonic()
        try:
            if condition not in {"New", "LikeNew", "NewWithTags"}:
                raise ValueError("Missing or unsupported user condition")
            valuation = profiler._call_openai_valuation(content=[],
                gemini_profile=copy.deepcopy(row["gemini_profile"]), condition_grade=condition,
                capture=result["capture"])
            if not isinstance(valuation, dict):
                raise ValueError("No valuation returned")
            result["valuation"] = valuation
            result["status"] = "returned"
        except Exception as exc:
            # Avoid putting provider request bodies, credentials or source URLs in console logs.
            result.update(status="failed", error_type=type(exc).__name__)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        print(json.dumps({k: result[k] for k in ("case", "model", "condition", "status", "elapsed_seconds")}), flush=True)
        return result

    tasks = [(i, row, model) for i, row in enumerate(rows, 1) for model in ["gpt-5", "gpt-6.1-sol"]]
    artifact = dict(format_version=2, source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    created_at=datetime.now(timezone.utc).isoformat(), policy_version=POLICY_VERSION,
                    results=[], complete=False, approved=False,
                    limitations="Historical identities; no human gold prices; smoke comparison only.")
    save(artifact)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(evaluate, task) for task in tasks]
        for future in as_completed(futures):
            artifact["results"].append(future.result())
            save(artifact)
    results = sorted(artifact["results"], key=lambda r: (r["case"], r["model"]))
    artifact.update(results=results, complete=True)
    save(artifact)
    return int(any(r["status"] == "failed" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
