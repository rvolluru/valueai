from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
try:
    import torch
except Exception:  # pragma: no cover - optional dependency in lightweight environments
    torch = None  # type: ignore[assignment]
from PIL import Image

from .brands import load_brands
from .matcher import BrandMatcher
from .types import BrandCandidate, ImageInput


@dataclass(slots=True)
class LogoClassifierOutput:
    candidates: list[BrandCandidate]
    model_available: bool


class LogoClassifier:
    def __init__(
        self,
        enabled: bool = False,
        weights_path: str | None = None,
        model_type: str = "efficientnet",
        yolo_weights_path: str | None = None,
        yolo_confidence: float = 0.35,
    ):
        self.enabled = enabled
        self.weights_path = weights_path
        self.model_type = (model_type or "efficientnet").strip().casefold()
        self.yolo_weights_path = yolo_weights_path
        self.yolo_confidence = yolo_confidence
        self._model = None
        self._yolo_model = None
        self._records = load_brands()
        self._matcher = BrandMatcher(self._records)
        self._class_names = [r.canonical for r in self._records]
        self._load_error: str | None = None
        self._fallback_model = None
        self._fallback_transform = None
        self._fallback_categories: list[str] = []
        if torch is None:
            self._load_error = "torch_not_installed"
            return
        if enabled and self.model_type == "yolo":
            self._init_yolo()
        if enabled and self.model_type != "yolo" and weights_path and Path(weights_path).exists():
            try:
                import timm  # type: ignore

                checkpoint = torch.load(str(weights_path), map_location="cpu")
                state = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
                if isinstance(checkpoint, dict):
                    classes = checkpoint.get("class_names")
                    if isinstance(classes, list) and classes:
                        self._class_names = [str(x) for x in classes]
                if not isinstance(state, dict):
                    raise RuntimeError("invalid checkpoint format")
                model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=len(self._class_names))
                cleaned: dict[str, Any] = {}
                for k, v in state.items():
                    cleaned[k[7:] if k.startswith("module.") else k] = v
                model.load_state_dict(cleaned, strict=False)
                model.eval()
                self._model = model
            except Exception as exc:
                self._model = None
                self._load_error = str(exc)
        if enabled and self._model is None:
            self._init_imagenet_fallback()

    def _init_yolo(self) -> None:
        if not self.yolo_weights_path or not Path(self.yolo_weights_path).exists():
            self._load_error = "yolo_weights_missing"
            return
        try:
            from ultralytics import YOLO  # type: ignore

            self._yolo_model = YOLO(self.yolo_weights_path)
        except Exception as exc:
            self._yolo_model = None
            self._load_error = str(exc)

    def _init_imagenet_fallback(self) -> None:
        try:
            from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0  # type: ignore

            weights = EfficientNet_B0_Weights.DEFAULT
            model = efficientnet_b0(weights=weights)
            model.eval()
            self._fallback_model = model
            self._fallback_transform = weights.transforms()
            categories = weights.meta.get("categories")
            if isinstance(categories, list):
                self._fallback_categories = [str(x) for x in categories]
        except Exception as exc:
            self._fallback_model = None
            self._fallback_transform = None
            self._load_error = self._load_error or str(exc)

    @staticmethod
    def _preprocess(image: np.ndarray) -> torch.Tensor:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
        arr = resized.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
        arr = np.transpose(arr, (2, 0, 1))
        return torch.from_numpy(arr).unsqueeze(0)  # type: ignore[union-attr]

    def predict(self, images: list[ImageInput]) -> LogoClassifierOutput:
        if torch is None:
            return LogoClassifierOutput(candidates=[], model_available=False)
        if not self.enabled:
            return LogoClassifierOutput(candidates=[], model_available=False)
        if self._yolo_model is not None:
            return self._predict_with_yolo(images)
        if self._model is None:
            if not self.enabled or self._fallback_model is None or self._fallback_transform is None:
                return LogoClassifierOutput(candidates=[], model_available=False)
            return self._predict_with_imagenet_fallback(images)

        candidates: list[BrandCandidate] = []
        for image in images:
            arr = np.frombuffer(image.bytes_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue
            x = self._preprocess(frame)
            with torch.no_grad():
                logits = self._model(x)
                probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
            top_idx = int(np.argmax(probs))
            top_prob = float(probs[top_idx])
            if top_prob < 0.45:
                continue
            name = self._class_names[top_idx] if top_idx < len(self._class_names) else "unknown"
            if name == "unknown":
                continue
            candidates.append(
                BrandCandidate(
                    name=name,
                    score=round(top_prob * 100.0, 2),
                    evidence="logo_classifier",
                    metadata={
                        "image_id": image.image_id,
                        "model": "efficientnet_b0_logo",
                        "weights_path": self.weights_path,
                        "confidence_01": round(top_prob, 4),
                    },
                )
            )
        return LogoClassifierOutput(candidates=candidates, model_available=True)

    def _predict_with_yolo(self, images: list[ImageInput]) -> LogoClassifierOutput:
        candidates: list[BrandCandidate] = []
        for image in images:
            arr = np.frombuffer(image.bytes_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue
            try:
                results = self._yolo_model.predict(source=frame, conf=self.yolo_confidence, verbose=False)
            except Exception:
                continue
            if not results:
                continue
            result = results[0]

            probs = getattr(result, "probs", None)
            if probs is not None and getattr(probs, "top1", None) is not None:
                idx = int(probs.top1)
                top1_conf = probs.top1conf
                conf = float(top1_conf.item() if hasattr(top1_conf, "item") else top1_conf)
                label = self._class_label_from_result(result, idx)
                mapped = self._map_label_to_brand(label)
                if mapped is None:
                    continue
                brand_name, label_match_score, label_method = mapped
                score = max(35.0, min(96.0, conf * 88.0 + label_match_score * 0.12))
                candidates.append(
                    BrandCandidate(
                        name=brand_name,
                        score=round(score, 2),
                        evidence="logo_classifier",
                        metadata={
                            "image_id": image.image_id,
                            "model": "yolov8_logo",
                            "weights_path": self.yolo_weights_path,
                            "source_label": label,
                            "source_prob": round(conf, 4),
                            "label_match_score": round(label_match_score, 2),
                            "label_method": label_method,
                        },
                    )
                )
                continue

            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            names = getattr(result, "names", {})
            try:
                box_list = list(boxes)
            except Exception:
                box_list = []
            for box in box_list[:5]:
                try:
                    cls_v = box.cls[0]
                    conf_v = box.conf[0]
                    cls_idx = int(cls_v.item() if hasattr(cls_v, "item") else cls_v)
                    conf = float(conf_v.item() if hasattr(conf_v, "item") else conf_v)
                except Exception:
                    continue
                label = names.get(cls_idx, str(cls_idx)) if isinstance(names, dict) else str(cls_idx)
                mapped = self._map_label_to_brand(label)
                if mapped is None:
                    continue
                brand_name, label_match_score, label_method = mapped
                score = max(30.0, min(94.0, conf * 85.0 + label_match_score * 0.15))
                candidates.append(
                    BrandCandidate(
                        name=brand_name,
                        score=round(score, 2),
                        evidence="logo_classifier",
                        metadata={
                            "image_id": image.image_id,
                            "model": "yolov8_logo",
                            "weights_path": self.yolo_weights_path,
                            "source_label": label,
                            "source_prob": round(conf, 4),
                            "label_match_score": round(label_match_score, 2),
                            "label_method": label_method,
                        },
                    )
                )

        return LogoClassifierOutput(candidates=candidates, model_available=True)

    @staticmethod
    def _class_label_from_result(result: Any, idx: int) -> str:
        names = getattr(result, "names", {})
        if isinstance(names, dict):
            return str(names.get(idx, idx))
        if isinstance(names, list) and idx < len(names):
            return str(names[idx])
        return str(idx)

    def _map_label_to_brand(self, label: str) -> tuple[str, float, str] | None:
        matches = self._matcher.match_text(label)
        if not matches:
            return None
        top = matches[0]
        if top.method != "alias_exact" and top.score < 55.0:
            return None
        return top.candidate, float(top.score), top.method

    def _predict_with_imagenet_fallback(self, images: list[ImageInput]) -> LogoClassifierOutput:
        candidates: list[BrandCandidate] = []
        for image in images:
            arr = np.frombuffer(image.bytes_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue
            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            x = self._fallback_transform(pil).unsqueeze(0)
            with torch.no_grad():
                logits = self._fallback_model(x)
                probs = torch.softmax(logits, dim=1)[0]
                top_vals, top_idx = torch.topk(probs, k=5)

            for i in range(top_idx.shape[0]):
                idx = int(top_idx[i].item())
                prob = float(top_vals[i].item())
                if prob < 0.05:
                    continue
                label = (
                    self._fallback_categories[idx]
                    if idx < len(self._fallback_categories)
                    else f"class_{idx}"
                )
                matches = self._matcher.match_text(label)
                if not matches:
                    continue
                top = matches[0]
                score = min(40.0, prob * max(top.score, 1.0) * 0.4)
                candidates.append(
                    BrandCandidate(
                        name=top.candidate,
                        score=round(score, 2),
                        evidence="logo_classifier",
                        metadata={
                            "image_id": image.image_id,
                            "model": "efficientnet_b0_imagenet_fallback",
                            "source_label": label,
                            "source_prob": round(prob, 4),
                            "label_match_score": round(top.score, 2),
                            "load_error": self._load_error,
                        },
                    )
                )
        return LogoClassifierOutput(candidates=candidates, model_available=True)
