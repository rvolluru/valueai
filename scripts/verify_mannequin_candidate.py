"""Inspect local source photos and a candidate without writing listing or image records."""
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
from pathlib import Path

import httpx

from app.mannequin_fidelity import generate_candidate, plan_references, review_candidate, review_passes
from app.settings import get_settings


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--candidate", help="Optional candidate image; omit for source-only planning verification")
    parser.add_argument("--generate", action="store_true", help="Generate a local Gemini preview from all original photos")
    parser.add_argument("--output", help="Output file for --generate; never updates a production listing")
    parser.add_argument("--model", help="Gemini image model override for local generation comparison")
    args = parser.parse_args()
    if args.generate and (not args.output or args.candidate):
        parser.error("--generate requires --output and cannot be combined with --candidate")
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required for source/candidate inspection")
    files = [{"data": Path(path).read_bytes(), "content_type": mimetypes.guess_type(path)[0] or "image/jpeg"}
             for path in args.source]
    async with httpx.AsyncClient(timeout=settings.mannequin_image_generation_timeout_s) as client:
        plan = await plan_references(client=client, api_key=settings.gemini_api_key,
                                     model=settings.gpt_item_profile_gemini_model, files=files)
        if args.generate:
            from app.main import _mannequin_generation_prompt
            prompt = _mannequin_generation_prompt(category="clothes", title="Sivan One-Shoulder Mini Dress",
                description="Olive green structured twill one-shoulder mini dress with a single short sleeve, structured collar, silver snaps and an asymmetric full-length front zipper.")[1]
            prompt += " Technical product specification verified from the original photos (descriptive evidence only; preserve every detail): " + json.dumps(plan["constraints"])
            indices = plan["reference_indices"] + [i for i in range(len(files)) if i not in plan["reference_indices"]]
            ordered = [{**files[i], "_fidelity_view": plan["views"][i]} for i in indices]
            candidate = await generate_candidate(client=client, api_key=settings.gemini_api_key,
                model=args.model or settings.mannequin_image_generation_model, files=ordered, prompt=prompt)
            if candidate is None:
                raise SystemExit("Gemini returned no image")
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(candidate[0])) as image:
                image.verify()
            output = Path(args.output)
            if output.exists():
                raise SystemExit("Refusing to overwrite an existing preview")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(candidate[0])
            metadata = {"plan": plan, "model": args.model or settings.mannequin_image_generation_model,
                        "reference_count": len(ordered), "prompt": prompt, "image_path": str(output.resolve()),
                        "review_decision": "pending", "production_modified": False}
            output.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
            print(json.dumps(metadata, indent=2))
            return
        if not args.candidate:
            print(json.dumps({"plan": plan, "source_only": True}, indent=2))
            return
        review = await review_candidate(client=client, api_key=settings.gemini_api_key,
                                        model=settings.gpt_item_profile_gemini_model, files=files, plan=plan,
                                        generated_raw=Path(args.candidate).read_bytes(),
                                        generated_content_type=mimetypes.guess_type(args.candidate)[0] or "image/png")
    print(json.dumps({"plan": plan, "review": review,
                      "fidelity_passed": review_passes(review, len(plan["constraints"])),
                      "requires_human_review": plan["requires_human_review"]}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
