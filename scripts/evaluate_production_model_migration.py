#!/usr/bin/env python3
"""Read-only model migration check against an explicit production listing snapshot."""
import argparse
import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps/api"), str(ROOT / "packages/brand/src"), str(ROOT / "packages/valuation/src")]


def production_profiler(revision):
    source = subprocess.check_output(["git", "show", f"{revision}:apps/api/app/gpt_item_profile.py"], cwd=ROOT, text=True)
    name = "app.production_migration_profile"
    module = types.ModuleType(name)
    module.__package__ = "app"
    sys.modules[name] = module
    exec(compile(source, f"git:{revision}:gpt_item_profile.py", "exec"), module.__dict__)
    return module.GptItemProfiler, hashlib.sha256(source.encode()).hexdigest()


def analysis(row):
    value = row.get("analysis_json")
    return json.loads(value) if isinstance(value, str) and value else value or {}


def band(profile, condition, selected=None):
    """Use the shared application selector, supplement absent endpoints from the exact-condition table."""
    from app.main import valuation_from_gpt_item_profile, _pricing_row_condition
    chosen = selected if selected is not None else valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade=condition)
    if not chosen:
        return {"value": None, "low": None, "high": None, "status": "unavailable"}
    low, high = chosen.get("range_low"), chosen.get("range_high")
    target_rows = [r for r in profile.get("resale_price_breakdown") or [] if isinstance(r, dict) and _pricing_row_condition(r) == condition]
    supplement = target_rows[0] if target_rows else {}
    return {"value": chosen.get("estimated_value"), "low": low if low is not None else supplement.get("range_low"),
            "high": high if high is not None else supplement.get("range_high"), "status": "priced",
            "endpoint_source": "exact_condition_table" if (low is None or high is None) and supplement else "selected_valuation",
            "basis": chosen.get("basis")}


def deltas(baseline, candidate, tolerance=.1):
    changes = {}
    for key in ("value", "low", "high"):
        old, new = baseline.get(key), candidate.get(key)
        if not isinstance(old, (int, float)) or isinstance(old, bool) or old <= 0 or not isinstance(new, (int, float)) or not math.isfinite(new):
            changes[key] = None
        else:
            changes[key] = round((new - old) / old * 100, 2)
    return {"percent_change": changes, "within_tolerance": all(v is not None and abs(v) <= tolerance * 100 for v in changes.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--production-revision", default="51bb1bd")
    parser.add_argument("--repeat-old", type=int, default=3)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        parser.error("Output exists; use a new artifact")
    snapshot = json.loads(Path(args.snapshot).read_text())
    rows = snapshot["listings"]
    if len(rows) != 10 or not 0 <= args.repeat_old <= 10:
        parser.error("Exactly 10 snapshot listings required; repeat-old must be 0..10")
    cls, code_hash = production_profiler(args.production_revision)
    cases = []
    for index, row in enumerate(rows, 1):
        a = analysis(row)
        identity = a.get("item_profile") or {}
        cases.append({"case": index, "listing_id": row["listing_id"], "title": row["title"],
            "condition": row["condition"], "created_at": row["created_at"],
            "baseline": band(identity, row["condition"], selected=a.get("valuation")),
            "baseline_listing_value": row["estimated_value"], "saved_identity": identity})
    print(json.dumps({"listings": len(rows), "calls": 20 + args.repeat_old, "execute": args.execute}), flush=True)
    if not args.execute:
        return 0
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY required")
    artifact = {"experiment": "production-model-migration-v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "production_revision": args.production_revision, "production_profiler_sha256": code_hash,
        "snapshot_sha256": hashlib.sha256(Path(args.snapshot).read_bytes()).hexdigest(), "cases": cases,
        "results": [], "complete": False, "tolerance_percent": 10,
        "limitations": "Pricing-only reruns with frozen saved identity and deployed prompt; fresh independent research. No production writes or automatic repricing."}
    target.parent.mkdir(parents=True, exist_ok=True)
    def save():
        with target.open("r+" if target.exists() else "x") as handle:
            os.chmod(target, 0o600)
            json.dump(artifact, handle, indent=2)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    save()
    def evaluate(task):
        index, model, repeat = task
        row, case = rows[index-1], cases[index-1]
        result = {"case": index, "listing_id": row["listing_id"], "model": model, "repeat": repeat}
        started = time.monotonic()
        try:
            if not case["saved_identity"]:
                raise ValueError("Missing saved identity")
            profiler = cls.__new__(cls)
            profiler.openai_model, profiler.reasoning_effort = model, "low"
            profiler.max_images, profiler.image_detail = 6, "auto"
            a = analysis(row)
            hints = (a.get("debug") or {}).get("input_hints") or {}
            content = profiler._build_content(images=[], brand_name=row["brand"], category=row["category"],
                item_size=row.get("size"), condition_grade=row["condition"], condition_source="user_input",
                item_description=hints.get("item_description") or None)
            payload = profiler._build_openai_valuation_payload(content=content, gemini_profile=case["saved_identity"], condition_grade=row["condition"])
            payload.update(include=["web_search_call.action.sources"], store=False)
            result["capture"] = {"request": payload, "identity": copy.deepcopy(case["saved_identity"]), "condition": row["condition"]}
            response = httpx.post("https://api.openai.com/v1/responses", json=payload,
                headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, timeout=240)
            raw = response.json()
            result["capture"]["raw_response"] = raw
            result["http_status"] = response.status_code
            response.raise_for_status()
            value = profiler._parse_json_relaxed(profiler._extract_output_text(raw))
            if not isinstance(value, dict):
                raise ValueError("No valuation returned")
            result["capture"]["pre_validation"] = value
            merged = {**case["saved_identity"], **value}
            merged.pop("pricing_evidence_policy", None)
            result.update(status="returned", band=band(merged, row["condition"]))
            result["versus_saved_production"] = deltas(case["baseline"], result["band"])
        except Exception as exc:
            result.update(status="failed", error_type=type(exc).__name__)
        result["elapsed_seconds"] = round(time.monotonic()-started, 3)
        print(json.dumps({k:result[k] for k in ("case", "model", "repeat", "status", "elapsed_seconds")}), flush=True)
        return result
    tasks = [(i, m, 1) for i in range(1, 11) for m in ("gpt-5", "gpt-6.1-sol")]
    tasks += [(i, "gpt-5", 2) for i in range(1, args.repeat_old+1)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(evaluate, t) for t in tasks]):
            artifact["results"].append(future.result())
            save()
    artifact["complete"] = True
    artifact["paired_comparisons"] = []
    for case in cases:
        runs = [r for r in artifact["results"] if r["case"] == case["case"] and r["status"] == "returned"]
        old = next((r for r in runs if r["model"] == "gpt-5" and r["repeat"] == 1), None)
        new = next((r for r in runs if r["model"] == "gpt-6.1-sol"), None)
        repeat = next((r for r in runs if r["model"] == "gpt-5" and r["repeat"] == 2), None)
        entry = {"case": case["case"], "new_vs_old_fresh": deltas(old["band"], new["band"]) if old and new else None}
        if old and repeat:
            entry["old_repeat_variation"] = deltas(old["band"], repeat["band"])
        artifact["paired_comparisons"].append(entry)
    save()
    return int(any(r["status"] == "failed" for r in artifact["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
