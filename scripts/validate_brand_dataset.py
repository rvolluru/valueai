#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


CLASSES = {"0", "1", "2", "3", "4"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels-dir", default="data/brand_evidence/labels/train")
    args = parser.parse_args()
    labels_dir = Path(args.labels_dir)
    if not labels_dir.exists():
        raise SystemExit(f"Missing labels dir: {labels_dir}")

    total = 0
    bad = 0
    for txt in labels_dir.rglob("*.txt"):
        for line in txt.read_text(encoding="utf-8").splitlines():
            total += 1
            parts = line.strip().split()
            if len(parts) != 5 or parts[0] not in CLASSES:
                bad += 1
                print(f"Invalid label in {txt}: {line}")
    print(f"checked={total} invalid={bad}")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
