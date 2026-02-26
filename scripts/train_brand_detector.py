#!/usr/bin/env python3
"""
YOLOv8 brand evidence detector training skeleton.

Expected dataset layout:
  data/brand_evidence/
    images/train/*.jpg
    images/val/*.jpg
    labels/train/*.txt
    labels/val/*.txt
    data.yaml

Classes:
  0 tag_label
  1 logo_wordmark
  2 hardware_engraving
  3 monogram_pattern
  4 hangtag
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/brand_evidence/data.yaml")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=960)
    args = parser.parse_args()

    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit("Install optional dependency: pip install '.[ml]'") from exc

    if not Path(args.data).exists():
        raise SystemExit(f"Missing dataset config: {args.data}")

    model = YOLO(args.model)
    model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz, workers=2, device="cpu")


if __name__ == "__main__":
    main()
