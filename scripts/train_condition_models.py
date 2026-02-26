#!/usr/bin/env python3
"""
Condition model training stub for:
  - category classifier (3-way)
  - grade classifier (5-way)
  - issue multi-label head

Dataset annotations should include:
  item_id,image_path,category,grade,issues_json
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/condition/manifest.csv")
    parser.add_argument("--task", choices=["category", "condition", "all"], default="all")
    args = parser.parse_args()
    print("Training stub only.")
    print(f"manifest={args.manifest} task={args.task}")


if __name__ == "__main__":
    main()
