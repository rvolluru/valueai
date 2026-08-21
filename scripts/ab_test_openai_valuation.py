#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "apps/api"),
    str(ROOT / "packages/brand/src"),
]

from app.gpt_item_profile import GptItemProfiler  # noqa: E402
from brand.types import ImageInput  # noqa: E402


IMAGE_URL_COLUMNS = (
    "image_urls",
    "image url",
    "image_url",
    "images",
    "photo_urls",
    "photo urls",
    "photos",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run current OpenAI valuation prompt versus a candidate prompt against listings "
            "from a Google Sheet CSV export or local CSV. Gemini identification is run once per row."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sheet-url", help="Google Sheets URL. The sheet must be accessible to this process.")
    source.add_argument("--csv", help="Local CSV path.")
    parser.add_argument("--prompt-b-file", required=True, help="Text file containing the candidate valuation prompt.")
    parser.add_argument("--out-csv", default="tmp/openai_valuation_ab_results.csv")
    parser.add_argument("--out-jsonl", default="tmp/openai_valuation_ab_results.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to run. 0 means all rows.")
    parser.add_argument("--max-images", type=int, default=6)
    parser.add_argument("--timeout-s", type=float, default=float(os.getenv("GPT_ITEM_PROFILE_TIMEOUT_S", "120")))
    parser.add_argument("--openai-model", default=os.getenv("GPT_ITEM_PROFILE_MODEL", "gpt-5"))
    parser.add_argument("--gemini-model", default=os.getenv("GPT_ITEM_PROFILE_GEMINI_MODEL", "gemini-2.5-flash"))
    parser.add_argument("--reasoning-effort", default=os.getenv("GPT_ITEM_PROFILE_REASONING_EFFORT", "low"))
    parser.add_argument("--image-detail", default=os.getenv("GPT_ITEM_PROFILE_IMAGE_DETAIL", "auto"))
    parser.add_argument("--skip-image-errors", action="store_true", help="Continue rows that have some failed image downloads.")
    return parser.parse_args()


def google_sheet_csv_url(sheet_url: str) -> str:
    parsed = urlparse(sheet_url)
    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        raise ValueError("Could not parse spreadsheet id from Google Sheet URL.")
    sheet_id = match.group(1)
    query = parse_qs(parsed.query)
    gid = (query.get("gid") or ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def read_rows(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.csv:
        with open(args.csv, newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    csv_url = google_sheet_csv_url(args.sheet_url)
    with httpx.Client(timeout=args.timeout_s, follow_redirects=True) as client:
        response = client.get(csv_url)
        response.raise_for_status()
    decoded = response.content.decode("utf-8-sig")
    return list(csv.DictReader(decoded.splitlines()))


def normalized_row(row: dict[str, str]) -> dict[str, str]:
    return {str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()}


def first_present(row: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = row.get(name.strip().lower())
        if value:
            return value
    return default


def extract_image_urls(row: dict[str, str]) -> list[str]:
    urls: list[str] = []
    for column in IMAGE_URL_COLUMNS:
        value = row.get(column)
        if value:
            urls.extend(re.split(r"[\n,|]+", value))
    for idx in range(1, 7):
        for column in (
            f"image_url_{idx}",
            f"image {idx}",
            f"image{idx}",
            f"photo_url_{idx}",
            f"photo {idx}",
            f"photo{idx}",
            f"url{idx}",
            f"url {idx}",
        ):
            value = row.get(column)
            if value:
                urls.append(value)
    seen = set()
    clean: list[str] = []
    for url in urls:
        candidate = str(url or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            clean.append(candidate)
    return clean


def download_images(urls: list[str], *, timeout_s: float, max_images: int, skip_errors: bool) -> list[ImageInput]:
    images: list[ImageInput] = []
    with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
        for idx, url in enumerate(urls[:max_images], start=1):
            try:
                response = client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if not content_type or not content_type.startswith("image/"):
                    guessed, _ = mimetypes.guess_type(urlparse(url).path)
                    content_type = guessed or "image/jpeg"
                images.append(
                    ImageInput(
                        image_id=f"sheet-image-{idx}",
                        filename=Path(urlparse(url).path).name or f"image-{idx}.jpg",
                        content_type=content_type,
                        bytes_data=response.content,
                    )
                )
            except Exception:
                if not skip_errors:
                    raise
    return images


def estimate_from_valuation(valuation: dict[str, Any] | None) -> dict[str, Any]:
    valuation = valuation if isinstance(valuation, dict) else {}
    resale = valuation.get("resale_price_estimate") if isinstance(valuation.get("resale_price_estimate"), dict) else {}
    return {
        "estimated_price": resale.get("estimated_price"),
        "range_low": resale.get("range_low"),
        "range_high": resale.get("range_high"),
        "currency": resale.get("currency"),
        "confidence": resale.get("confidence"),
        "rationale": resale.get("rationale"),
        "source_count": len(valuation.get("grounding_sources") or []),
    }


def make_profiler(args: argparse.Namespace) -> GptItemProfiler:
    return GptItemProfiler(
        enabled=True,
        provider_order="hybrid",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=args.openai_model,
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=args.gemini_model,
        timeout_s=args.timeout_s,
        max_images=args.max_images,
        image_detail=args.image_detail,
        reasoning_effort=args.reasoning_effort,
        vertex_search_enabled=False,
    )


def main() -> int:
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required.")
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is required.")

    prompt_b = Path(args.prompt_b_file).read_text(encoding="utf-8").strip()
    if not prompt_b:
        raise SystemExit("--prompt-b-file is empty.")

    rows = read_rows(args)
    if args.limit > 0:
        rows = rows[: args.limit]
    profiler = make_profiler(args)

    out_csv = ROOT / args.out_csv
    out_jsonl = ROOT / args.out_jsonl
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "row_number",
        "input_title",
        "input_brand",
        "input_category",
        "input_condition",
        "input_size",
        "gemini_brand",
        "gemini_model",
        "gemini_category",
        "a_estimated_price",
        "a_range_low",
        "a_range_high",
        "a_confidence",
        "a_source_count",
        "b_estimated_price",
        "b_range_low",
        "b_range_high",
        "b_confidence",
        "b_source_count",
        "delta_b_minus_a",
        "error",
    ]

    with out_csv.open("w", newline="", encoding="utf-8") as csv_handle, out_jsonl.open("w", encoding="utf-8") as jsonl_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=fieldnames)
        writer.writeheader()

        for row_number, raw_row in enumerate(rows, start=1):
            row = normalized_row(raw_row)
            title = first_present(row, "title", "item_title", "listing_title", "name")
            brand = first_present(row, "brand", "candidate_brand")
            category = first_present(row, "category", "item_category", default="unknown")
            condition = first_present(row, "condition", "user_condition", "condition_grade", default="New")
            size = first_present(row, "size", "item_size")
            description = first_present(row, "description", "item_description", "listing_description", "notes", default=title)

            summary: dict[str, Any] = {
                "row_number": row_number,
                "input_title": title,
                "input_brand": brand,
                "input_category": category,
                "input_condition": condition,
                "input_size": size,
                "error": "",
            }
            detail: dict[str, Any] = {"row": raw_row, "summary": summary}
            try:
                image_urls = extract_image_urls(row)
                if not image_urls:
                    raise RuntimeError("No image URLs found in row.")
                images = download_images(
                    image_urls,
                    timeout_s=args.timeout_s,
                    max_images=args.max_images,
                    skip_errors=args.skip_image_errors,
                )
                if not images:
                    raise RuntimeError("No images could be downloaded.")
                content = profiler._build_content(
                    images=images,
                    brand_name=brand,
                    category=category,
                    item_size=size,
                    condition_grade=condition,
                    condition_source="sheet",
                    item_description=description,
                )
                gemini_profile = profiler._call_gemini(
                    images=images,
                    brand_name=brand,
                    category=category,
                    item_size=size,
                    condition_grade=condition,
                    condition_source="sheet",
                    item_description=description,
                    schema=profiler._build_schema(),
                )
                if not isinstance(gemini_profile, dict):
                    raise RuntimeError("Gemini returned no profile.")

                valuation_a = profiler._call_openai_valuation(content=content, gemini_profile=gemini_profile)
                valuation_b = profiler._call_openai_valuation(
                    content=content,
                    gemini_profile=gemini_profile,
                    valuation_prompt_override=prompt_b,
                )
                estimate_a = estimate_from_valuation(valuation_a)
                estimate_b = estimate_from_valuation(valuation_b)
                price_a = estimate_a.get("estimated_price")
                price_b = estimate_b.get("estimated_price")
                delta = None
                if isinstance(price_a, (int, float)) and isinstance(price_b, (int, float)):
                    delta = round(float(price_b) - float(price_a), 2)

                model_id = gemini_profile.get("model_identification") if isinstance(gemini_profile.get("model_identification"), dict) else {}
                summary.update(
                    {
                        "gemini_brand": gemini_profile.get("candidate_brand"),
                        "gemini_model": model_id.get("name") or gemini_profile.get("candidate_model"),
                        "gemini_category": gemini_profile.get("category"),
                        "a_estimated_price": estimate_a.get("estimated_price"),
                        "a_range_low": estimate_a.get("range_low"),
                        "a_range_high": estimate_a.get("range_high"),
                        "a_confidence": estimate_a.get("confidence"),
                        "a_source_count": estimate_a.get("source_count"),
                        "b_estimated_price": estimate_b.get("estimated_price"),
                        "b_range_low": estimate_b.get("range_low"),
                        "b_range_high": estimate_b.get("range_high"),
                        "b_confidence": estimate_b.get("confidence"),
                        "b_source_count": estimate_b.get("source_count"),
                        "delta_b_minus_a": delta,
                    }
                )
                detail.update(
                    {
                        "image_urls": image_urls[: args.max_images],
                        "gemini_profile": gemini_profile,
                        "valuation_a_current_prompt": valuation_a,
                        "valuation_b_candidate_prompt": valuation_b,
                    }
                )
            except Exception as exc:
                summary["error"] = str(exc)
                detail["error"] = str(exc)

            writer.writerow({key: summary.get(key, "") for key in fieldnames})
            jsonl_handle.write(json.dumps(detail, ensure_ascii=True) + "\n")
            jsonl_handle.flush()
            csv_handle.flush()
            print(f"row {row_number}: {summary.get('input_title') or '(untitled)'} {summary.get('error') or 'ok'}")

    print(f"Wrote {out_csv}")
    print(f"Wrote {out_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
