#!/usr/bin/env python3
"""Generate a local migration compatibility report from captured results, without provider calls."""
import argparse
import json
from pathlib import Path


def money(value):
    return "unavailable" if value is None else f"${value:,.0f}"


def band_text(value):
    return f"{money(value.get('value'))} [{money(value.get('low'))}–{money(value.get('high'))}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text())
    if not data.get("complete"):
        raise SystemExit("Evaluation is incomplete; preserve missing cases rather than report a pass")
    from evaluate_production_model_migration import deltas
    lines = ["# Latest 10 production listings: model migration compatibility", "",
        "Read-only pilot; production listings and model settings were not changed.", "",
        f"Production prompt revision: `{data['production_revision']}`. Pricing uses saved identity and condition; independent live research is enabled for both models. Low reasoning. Provisional tolerance: ±10% on value and both band endpoints.", "",
        "Bands shown in brackets. Where selected endpoints were null, the exact-condition model table supplies endpoints; these are not necessarily previously displayed UI values.", "",
        "| # / Listing | Saved production | Fresh GPT-5 | Sol | Sol vs fresh GPT-5 value | All three within 10%? |",
        "| --- | --- | --- | --- | --- | --- |"]
    paired, archived, old_saved = [], [], []
    repeats = []
    for case in data["cases"]:
        runs = [r for r in data["results"] if r["case"]==case["case"] and r["status"]=="returned"]
        old = next((r for r in runs if r["model"]=="gpt-5" and r["repeat"]==1), None)
        new = next((r for r in runs if r["model"]=="gpt-6.1-sol"), None)
        repeat = next((r for r in runs if r["model"]=="gpt-5" and r["repeat"]==2), None)
        pair = deltas(old["band"],new["band"]) if old and new else None
        if pair: paired.append(pair)
        if new: archived.append(deltas(case["baseline"],new["band"]))
        if old: old_saved.append(deltas(case["baseline"],old["band"]))
        change = pair["percent_change"]["value"] if pair else None
        text_change = "unavailable" if change is None else f"{change:+.1f}%"
        title = case["title"].replace("|", "/")
        lines.append(f"| {case['case']}. {title} | {band_text(case['baseline'])} | {band_text(old['band']) if old else 'failed'} | {band_text(new['band']) if new else 'failed'} | {text_change} | {'Yes' if pair and pair['within_tolerance'] else 'No'} |")
        if old and repeat:
            comparison = deltas(old["band"],repeat["band"])
            repeats.append((case,old,repeat,comparison))
    lines += ["", "## Compatibility summary", ""]
    for label, values in [("Sol versus fresh GPT-5", paired), ("Sol versus saved production", archived), ("Fresh GPT-5 versus saved production", old_saved)]:
        passes = sum(v["within_tolerance"] for v in values)
        value_pass = sum(v["percent_change"]["value"] is not None and abs(v["percent_change"]["value"])<=10 for v in values)
        lines.append(f"- {label}: {passes}/{len(data['cases'])} pass value + both endpoints; {value_pass}/{len(data['cases'])} pass value alone. Missing calls/fields do not pass.")
    lines += ["", "## Old-model repeat variability", "",
        "| Case | GPT-5 first | GPT-5 repeat | Value change | All three within 10%? |",
        "| --- | --- | --- | --- | --- |"]
    for case,old,repeat,comparison in repeats:
        change=comparison["percent_change"]["value"]
        change_text = "unavailable" if change is None else f"{change:+.1f}%"
        lines.append(f"| {case['case']} | {band_text(old['band'])} | {band_text(repeat['band'])} | {change_text} | {'Yes' if comparison['within_tolerance'] else 'No'} |")
    lines += ["", "## Limits and next decision", "",
        "This measures backward compatibility, not valuation accuracy. It is one paired run on ten recent items and three old-model repeats, not a representative population or statistical guarantee. Saved results predate fresh research; market/source changes and existing model variation can contribute to differences. Identification/photos are frozen, so identity-model migration is not evaluated.", "",
        "Do not automatically reprice saved listings or apply a blanket correction derived from these same ten cases. Inspect large differences in the captured evidence before choosing migration rules or approving a rollout.", "",
        f"Full input/output evidence: `{args.input}`. Local only; do not publish raw listing data or provider artifacts.", ""]
    target=Path(args.output)
    with target.open("x") as handle:
        target.chmod(0o600)
        handle.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
