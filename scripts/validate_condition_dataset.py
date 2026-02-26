#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


VALID_CATEGORIES = {"clothes", "shoes", "handbag"}
VALID_GRADES = {"New", "LikeNew", "Good", "Fair", "Poor"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/condition/manifest.csv")
    args = parser.parse_args()

    path = Path(args.manifest)
    if not path.exists():
        raise SystemExit(f"Missing manifest: {path}")

    errors = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("category") not in VALID_CATEGORIES:
                print(f"Invalid category for {row.get('item_id')}: {row.get('category')}")
                errors += 1
            if row.get("grade") not in VALID_GRADES:
                print(f"Invalid grade for {row.get('item_id')}: {row.get('grade')}")
                errors += 1
            try:
                json.loads(row.get("issues_json") or "[]")
            except json.JSONDecodeError:
                print(f"Invalid issues_json for {row.get('item_id')}")
                errors += 1
    print(f"errors={errors}")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
