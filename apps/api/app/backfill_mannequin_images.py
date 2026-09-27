from __future__ import annotations

import argparse
import asyncio
import copy
import json

from .db import Database
from .main import (
    _generate_mannequin_listing_asset,
    _mannequin_generation_prompt,
    _read_storage_uri_bytes,
)
from .settings import get_settings
from .storage import build_storage


def _has_synthetic_asset(listing: dict) -> bool:
    analysis = listing.get("analysis")
    if not isinstance(analysis, dict):
        return False
    return any(
        isinstance(asset, dict) and asset.get("synthetic") and asset.get("image_url")
        for asset in analysis.get("generated_assets") or []
    )


def _eligible(listing: dict) -> bool:
    return bool(
        _mannequin_generation_prompt(
            category=str(listing.get("category") or ""),
            title=str(listing.get("title") or ""),
            description=str(listing.get("description") or ""),
        )
    ) and not _has_synthetic_asset(listing)


def _reference_files(db: Database, listing: dict, settings) -> list[dict[str, object]]:
    item_id = str(listing.get("source_item_id") or "").strip()
    if not item_id:
        return []
    files: list[dict[str, object]] = []
    for record in db.list_image_records_for_item(item_id, limit=20):
        if str(record.get("role_hint") or "").strip() == "ai_mannequin":
            continue
        storage_uri = str(record.get("storage_uri") or "").strip()
        if not storage_uri:
            continue
        try:
            data, content_type = _read_storage_uri_bytes(storage_uri, settings)
        except Exception as exc:
            print(json.dumps({"event": "reference_read_failed", "listing_id": listing["listing_id"], "error": str(exc)}))
            continue
        files.append(
            {
                "filename": str(record.get("filename") or "reference-image"),
                "content_type": content_type,
                "data": data,
                "source_url": f"/v1/images/{record['image_id']}",
            }
        )
        if len(files) == 3:
            break
    return files


async def backfill(limit: int, scan_limit: int, dry_run: bool) -> int:
    settings = get_settings()
    db = Database(settings.database_url)
    db.initialize()
    storage = build_storage(settings)
    candidates = [listing for listing in db.list_recent_listings(limit=scan_limit) if _eligible(listing)][:limit]
    print(json.dumps({"event": "backfill_selected", "requested": limit, "selected": len(candidates), "dry_run": dry_run}))
    if dry_run:
        for listing in candidates:
            print(json.dumps({"listing_id": listing["listing_id"], "title": listing.get("title"), "category": listing.get("category")}))
        return 0

    generated = 0
    for listing in candidates:
        listing_id = str(listing["listing_id"])
        item_id = str(listing.get("source_item_id") or "").strip() or f"item-{listing_id}"
        db.insert_item(item_id)
        files = _reference_files(db, listing, settings)
        if not files:
            print(json.dumps({"event": "backfill_skipped", "listing_id": listing_id, "reason": "no_original_images"}))
            continue
        asset = await _generate_mannequin_listing_asset(
            files=files,
            category=str(listing.get("category") or ""),
            title=str(listing.get("title") or ""),
            description=str(listing.get("description") or ""),
            item_id=item_id,
            settings=settings,
            db=db,
            storage=storage,
        )
        if not asset:
            print(json.dumps({"event": "backfill_failed", "listing_id": listing_id, "reason": "generation_failed"}))
            continue

        analysis = copy.deepcopy(listing.get("analysis")) if isinstance(listing.get("analysis"), dict) else {}
        generated_assets = [entry for entry in analysis.get("generated_assets") or [] if isinstance(entry, dict)]
        generated_assets.append(asset)
        analysis["generated_assets"] = generated_assets
        listed_images = copy.deepcopy(listing.get("listed_images") or listing.get("images") or [])
        generated_url = str(asset["image_url"])
        listed_images.append({"p_img": generated_url, "d_img": generated_url, "is_hero": False})
        updated = db.update_listing(
            listing_id=listing_id,
            owner_subject=str(listing["owner_subject"]),
            title=str(listing.get("title") or "New listing"),
            mode=str(listing.get("mode") or "trade"),
            category=str(listing.get("category") or "handbag"),
            brand=str(listing.get("brand") or "unknown"),
            condition=str(listing.get("condition") or "LikeNew"),
            size=listing.get("size"),
            estimated_value=float(listing.get("estimated_value") or 0),
            city=str(listing.get("city") or "Your area"),
            image=str(listing.get("image") or "") or None,
            images=listed_images,
            description=str(listing.get("description") or ""),
            wants=str(listing.get("wants") or "Open to similar-value offers"),
            tags=list(listing.get("tags") or []),
            source_item_id=item_id,
            analysis=analysis,
            status=str(listing.get("status") or "Review"),
        )
        if not updated:
            print(json.dumps({"event": "backfill_failed", "listing_id": listing_id, "reason": "listing_update_failed"}))
            continue
        generated += 1
        print(json.dumps({"event": "backfill_completed", "listing_id": listing_id, "image_id": asset["image_id"], "title": listing.get("title")}))

    print(json.dumps({"event": "backfill_summary", "requested": limit, "selected": len(candidates), "generated": generated}))
    return 0 if generated == len(candidates) and generated == limit else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Append mannequin images to recent eligible listings.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--scan-limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(backfill(max(1, args.limit), max(args.limit, args.scan_limit), args.dry_run)))


if __name__ == "__main__":
    main()
