#!/usr/bin/env python3
"""
Train a YOLO logo detector on Logos in the Wild v2.

This script will:
1) download/extract the dataset zip
2) find COCO-style annotations
3) convert to YOLO labels and build a train/val dataset
4) run Ultralytics YOLO training

Default dataset URL:
https://zenodo.org/record/5101018/files/LogosInTheWild-v2.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


DEFAULT_URL = "https://zenodo.org/record/5101018/files/LogosInTheWild-v2.zip"


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return
    with urllib.request.urlopen(url) as response, dst.open("wb") as out:
        shutil.copyfileobj(response, out)


def _extract(zip_path: Path, out_dir: Path) -> Path:
    extracted = out_dir / "extracted"
    if extracted.exists():
        return extracted
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extracted)
    return extracted


def _find_coco_annotation(root: Path) -> Path:
    for p in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and {"images", "annotations", "categories"}.issubset(payload.keys()):
            return p
    raise SystemExit("No COCO-style annotation json found in extracted dataset.")


def _find_pascal_xmls(root: Path) -> list[Path]:
    return sorted(root.rglob("*.xml"))


def _safe_symlink_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        dst.symlink_to(src.resolve())
    except Exception:
        shutil.copy2(src, dst)


def _split_for_image(file_name: str, val_ratio: float) -> str:
    seed = int(hashlib.sha256(file_name.encode("utf-8")).hexdigest()[:8], 16)
    r = random.Random(seed).random()
    return "val" if r < val_ratio else "train"


def _normalize_logo_label(raw: str, collapse_variants: bool) -> str:
    label = raw.strip().casefold()
    label = label.replace("_", "-")
    label = re.sub(r"\s+", "-", label)
    label = label.replace("schriftzug", "text").replace("schrift", "text").replace("logo", "symbol")
    label = label.replace("teilsichtbar", "").replace("partial", "")
    label = re.sub(r"[^a-z0-9+-]", "-", label)
    label = re.sub(r"-{2,}", "-", label).strip("-")
    if collapse_variants:
        label = re.sub(r"-(text|symbol)$", "", label)
        label = re.sub(r"\d+$", "", label)
        label = re.sub(r"-{2,}", "-", label).strip("-")
    return label or "unknown"


def _download_image(url: str, dst: Path, timeout_s: float) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ValueAI/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = resp.read()
        if len(data) < 1024:
            return False
        dst.write_bytes(data)
        return True
    except Exception:
        return False


def _load_urls_map(folder: Path) -> dict[str, str]:
    urls_file = folder / "urls.txt"
    if not urls_file.exists():
        return {}
    out: dict[str, str] = {}
    for line in urls_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        row = line.strip()
        if not row:
            continue
        parts = row.split("\t")
        if len(parts) < 2:
            parts = row.split(maxsplit=1)
            if len(parts) < 2:
                continue
        image_id = parts[0].strip()
        url = parts[1].strip()
        if image_id and url.startswith("http"):
            out[image_id] = url
    return out


def _resolve_image_path(extracted_root: Path, annotation_file: Path, file_name: str) -> Path | None:
    direct = extracted_root / file_name
    if direct.exists():
        return direct
    candidate = annotation_file.parent / file_name
    if candidate.exists():
        return candidate
    candidate = annotation_file.parent.parent / "images" / file_name
    if candidate.exists():
        return candidate

    basename = Path(file_name).name
    matches = list(extracted_root.rglob(basename))
    if matches:
        return matches[0]
    return None


def _convert_coco_to_yolo(
    *,
    coco_file: Path,
    extracted_root: Path,
    out_dir: Path,
    val_ratio: float,
) -> tuple[Path, int, int]:
    payload = json.loads(coco_file.read_text(encoding="utf-8"))
    images = payload["images"]
    annotations = payload["annotations"]
    categories = payload["categories"]

    cat_ids = sorted(int(c["id"]) for c in categories)
    id_to_index = {cid: idx for idx, cid in enumerate(cat_ids)}
    id_to_name = {int(c["id"]): str(c.get("name", f"class_{c['id']}")) for c in categories}

    img_by_id: dict[int, dict[str, Any]] = {int(i["id"]): i for i in images}
    ann_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ann in annotations:
        if ann.get("iscrowd", 0):
            continue
        ann_by_image[int(ann["image_id"])].append(ann)

    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    used_images = 0
    used_labels = 0

    for image_id, image in img_by_id.items():
        file_name = str(image.get("file_name", ""))
        width = float(image.get("width", 0))
        height = float(image.get("height", 0))
        if not file_name or width <= 0 or height <= 0:
            continue

        split = str(image.get("split") or "").strip().lower()
        if split not in {"train", "val"}:
            split = _split_for_image(file_name, val_ratio)

        src = _resolve_image_path(extracted_root, coco_file, file_name)
        if src is None:
            continue

        dst_img = out_dir / "images" / split / Path(file_name).name
        _safe_symlink_or_copy(src, dst_img)
        used_images += 1

        label_lines: list[str] = []
        for ann in ann_by_image.get(image_id, []):
            cat_id = int(ann["category_id"])
            if cat_id not in id_to_index:
                continue
            bbox = ann.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            x, y, w, h = [float(v) for v in bbox]
            if w <= 1 or h <= 1:
                continue
            x_c = (x + w / 2.0) / width
            y_c = (y + h / 2.0) / height
            w_n = w / width
            h_n = h / height
            if min(x_c, y_c, w_n, h_n) <= 0:
                continue
            if x_c >= 1 or y_c >= 1 or w_n >= 1.5 or h_n >= 1.5:
                continue
            label_lines.append(
                f"{id_to_index[cat_id]} {x_c:.6f} {y_c:.6f} {w_n:.6f} {h_n:.6f}"
            )

        dst_label = out_dir / "labels" / split / f"{Path(file_name).stem}.txt"
        dst_label.write_text("\n".join(label_lines), encoding="utf-8")
        if label_lines:
            used_labels += 1

    names = [id_to_name[cid] for cid in cat_ids]
    data_yaml = out_dir / "data.yaml"
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {out_dir.resolve()}",
                "train: images/train",
                "val: images/val",
                f"nc: {len(names)}",
                f"names: {json.dumps(names)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return data_yaml, used_images, used_labels


def _convert_pascal_to_yolo(
    *,
    xml_files: list[Path],
    out_dir: Path,
    val_ratio: float,
    collapse_variants: bool,
    download_missing: bool,
    download_timeout_s: float,
    max_download_attempts: int,
) -> tuple[Path, int, int]:
    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    class_names: list[str] = []
    class_to_idx: dict[str, int] = {}
    urls_cache: dict[Path, dict[str, str]] = {}
    download_attempts = 0
    used_images = 0
    used_labels = 0

    for xml_file in xml_files:
        try:
            root = ElementTree.parse(xml_file).getroot()
        except Exception:
            continue

        stem = xml_file.stem
        size_node = root.find("size")
        if size_node is None:
            continue
        try:
            width = float((size_node.findtext("width") or "0").strip())
            height = float((size_node.findtext("height") or "0").strip())
        except Exception:
            continue
        if width <= 0 or height <= 0:
            continue

        img_src = None
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            p = xml_file.with_suffix(ext)
            if p.exists():
                img_src = p
                break

        if img_src is None and download_missing:
            if max_download_attempts > 0 and download_attempts >= max_download_attempts:
                continue
            folder = xml_file.parent
            url_map = urls_cache.get(folder)
            if url_map is None:
                url_map = _load_urls_map(folder)
                urls_cache[folder] = url_map
            key = stem.replace("img", "", 1)
            url = url_map.get(key)
            if url:
                candidate = xml_file.with_suffix(".jpg")
                download_attempts += 1
                if _download_image(url, candidate, download_timeout_s):
                    img_src = candidate

        if img_src is None:
            continue

        split = _split_for_image(str(xml_file), val_ratio)
        dst_img = out_dir / "images" / split / f"{stem}{img_src.suffix.lower()}"
        _safe_symlink_or_copy(img_src, dst_img)

        lines: list[str] = []
        for obj in root.findall("object"):
            raw_name = obj.findtext("name") or ""
            label = _normalize_logo_label(raw_name, collapse_variants=collapse_variants)
            if label not in class_to_idx:
                class_to_idx[label] = len(class_names)
                class_names.append(label)
            class_idx = class_to_idx[label]

            box = obj.find("bndbox")
            if box is None:
                continue
            try:
                xmin = float((box.findtext("xmin") or "0").strip())
                ymin = float((box.findtext("ymin") or "0").strip())
                xmax = float((box.findtext("xmax") or "0").strip())
                ymax = float((box.findtext("ymax") or "0").strip())
            except Exception:
                continue
            w = xmax - xmin
            h = ymax - ymin
            if w <= 1 or h <= 1:
                continue
            x_c = (xmin + xmax) / 2.0 / width
            y_c = (ymin + ymax) / 2.0 / height
            w_n = w / width
            h_n = h / height
            if min(x_c, y_c, w_n, h_n) <= 0:
                continue
            if x_c >= 1 or y_c >= 1 or w_n >= 1.5 or h_n >= 1.5:
                continue
            lines.append(f"{class_idx} {x_c:.6f} {y_c:.6f} {w_n:.6f} {h_n:.6f}")

        dst_label = out_dir / "labels" / split / f"{stem}.txt"
        dst_label.write_text("\n".join(lines), encoding="utf-8")

        used_images += 1
        if lines:
            used_labels += 1

    if not class_names:
        raise SystemExit("No classes parsed from Pascal VOC annotations.")

    data_yaml = out_dir / "data.yaml"
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {out_dir.resolve()}",
                "train: images/train",
                "val: images/val",
                f"nc: {len(class_names)}",
                f"names: {json.dumps(class_names)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return data_yaml, used_images, used_labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--workdir", default="data/logos_in_the_wild")
    parser.add_argument("--zip-name", default="LogosInTheWild-v2.zip")
    parser.add_argument("--out", default="data/logo_yolo_litw")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--project", default="runs/logo_yolo")
    parser.add_argument("--name", default="litw_v2")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--collapse-variants", action="store_true", default=True)
    parser.add_argument("--no-collapse-variants", dest="collapse_variants", action="store_false")
    parser.add_argument("--download-missing-images", action="store_true", default=True)
    parser.add_argument("--no-download-missing-images", dest="download_missing_images", action="store_false")
    parser.add_argument("--download-timeout-s", type=float, default=8.0)
    parser.add_argument("--max-download-attempts", type=int, default=1000)
    args = parser.parse_args()

    workdir = Path(args.workdir)
    out_dir = Path(args.out)
    zip_path = workdir / args.zip_name

    print(f"[litw] download: {args.url}")
    _download(args.url, zip_path)
    print(f"[litw] extract: {zip_path}")
    extracted = _extract(zip_path, workdir)
    data_yaml: Path | None = None
    used_images = 0
    used_labels = 0
    try:
        coco_file = _find_coco_annotation(extracted)
        print(f"[litw] annotation (coco): {coco_file}")
        data_yaml, used_images, used_labels = _convert_coco_to_yolo(
            coco_file=coco_file,
            extracted_root=extracted,
            out_dir=out_dir,
            val_ratio=args.val_ratio,
        )
    except SystemExit:
        xml_files = _find_pascal_xmls(extracted)
        if not xml_files:
            raise SystemExit("No COCO json or Pascal VOC xml annotations found.")
        print(f"[litw] annotation (pascal): {len(xml_files)} xml files")
        data_yaml, used_images, used_labels = _convert_pascal_to_yolo(
            xml_files=xml_files,
            out_dir=out_dir,
            val_ratio=args.val_ratio,
            collapse_variants=args.collapse_variants,
            download_missing=args.download_missing_images,
            download_timeout_s=args.download_timeout_s,
            max_download_attempts=args.max_download_attempts,
        )
    print(f"[litw] yolo data yaml: {data_yaml}")
    print(f"[litw] images linked/copied: {used_images}, labeled images: {used_labels}")

    if args.prepare_only:
        print("[litw] prepare-only enabled, skipping training.")
        return

    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as exc:
        raise SystemExit("Install optional dependency: pip install '.[ml]'") from exc

    model = YOLO(args.model)
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        device=args.device,
        batch=args.batch,
        workers=args.workers,
        project=args.project,
        name=args.name,
    )
    print("[litw] training complete. Use best.pt as BRAND_LOGO_YOLO_WEIGHTS_PATH")


if __name__ == "__main__":
    main()
