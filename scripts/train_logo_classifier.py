#!/usr/bin/env python3
"""
Brand logo/monogram classifier training stub.

Dataset format:
  data/logo_classifier/
    train/<brand_name>/*.jpg
    val/<brand_name>/*.jpg

TODO:
  - timm backbone loading
  - 200-way head
  - augmentation policy
  - checkpoint export to packages/brand/models/
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/logo_classifier")
    parser.add_argument("--backbone", default="convnext_tiny")
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()
    print("Training stub only.")
    print(f"data={args.data} backbone={args.backbone} epochs={args.epochs}")


if __name__ == "__main__":
    main()
