from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


CATEGORIES = ["clothes", "shoes", "handbag"]


class CategoryClassifier:
    def __init__(self, weights_path: str | None = None):
        self.weights_path = weights_path
        self.available = bool(weights_path and Path(weights_path).exists())
        self._model = None
        self._torch: Any | None = None
        self._load_error: str | None = None
        self._fallback_model = None
        self._fallback_transform = None
        self._fallback_categories: list[str] = []
        if self.available:
            try:
                import timm  # type: ignore
                import torch  # type: ignore

                model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=len(CATEGORIES))
                checkpoint = torch.load(str(self.weights_path), map_location="cpu")
                state_dict = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
                if not isinstance(state_dict, dict):
                    raise RuntimeError("invalid checkpoint format")
                cleaned_state: dict[str, Any] = {}
                for key, value in state_dict.items():
                    k = key[7:] if key.startswith("module.") else key
                    cleaned_state[k] = value
                model.load_state_dict(cleaned_state, strict=False)
                model.eval()
                self._model = model
                self._torch = torch
            except Exception as exc:
                self._model = None
                self._torch = None
                self.available = False
                self._load_error = str(exc)
        if self._model is None:
            self._init_imagenet_fallback()

    def _init_imagenet_fallback(self) -> None:
        try:
            import torch  # type: ignore
            from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0  # type: ignore

            weights = EfficientNet_B0_Weights.DEFAULT
            model = efficientnet_b0(weights=weights)
            model.eval()
            self._fallback_model = model
            self._fallback_transform = weights.transforms()
            categories = weights.meta.get("categories")
            if isinstance(categories, list):
                self._fallback_categories = [str(x) for x in categories]
            self._torch = self._torch or torch
        except Exception:
            self._fallback_model = None
            self._fallback_transform = None

    @staticmethod
    def _preprocess(crop: np.ndarray) -> np.ndarray:
        if crop.ndim == 2:
            crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
        arr = resized.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
        return np.transpose(arr, (2, 0, 1))

    @staticmethod
    def _keyword_scores(labels_and_probs: list[tuple[str, float]]) -> dict[str, float]:
        keyword_map = {
            "shoes": {
                "shoe",
                "shoes",
                "sandal",
                "boot",
                "sneaker",
                "loafer",
                "slipper",
                "clog",
                "heel",
                "pumps",
            },
            "handbag": {
                "bag",
                "bags",
                "handbag",
                "purse",
                "backpack",
                "wallet",
                "briefcase",
                "satchel",
                "tote",
            },
            "clothes": {
                "coat",
                "jacket",
                "shirt",
                "jersey",
                "kimono",
                "gown",
                "dress",
                "sweater",
                "cardigan",
                "cloak",
                "trouser",
                "jean",
                "skirt",
                "blouse",
            },
        }
        scores = {k: 0.0 for k in CATEGORIES}
        for label, prob in labels_and_probs:
            norm = label.casefold()
            for category, keywords in keyword_map.items():
                if any(keyword in norm for keyword in keywords):
                    scores[category] += prob
        return scores

    def _predict_with_imagenet_fallback(self, crop: np.ndarray) -> tuple[str, float, dict] | None:
        if self._fallback_model is None or self._fallback_transform is None or self._torch is None:
            return None
        if crop.ndim == 2:
            crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        tensor = self._fallback_transform(pil).unsqueeze(0)
        with self._torch.no_grad():
            logits = self._fallback_model(tensor)
            probs = self._torch.softmax(logits, dim=1)[0]
            topk_vals, topk_idx = self._torch.topk(probs, k=5)
        labels_and_probs: list[tuple[str, float]] = []
        for i in range(topk_idx.shape[0]):
            idx = int(topk_idx[i].item())
            prob = float(topk_vals[i].item())
            label = self._fallback_categories[idx] if idx < len(self._fallback_categories) else f"class_{idx}"
            labels_and_probs.append((label, prob))

        mapped = self._keyword_scores(labels_and_probs)
        mapped_total = float(sum(mapped.values()))
        if mapped_total <= 0:
            return None
        category = max(mapped, key=mapped.get)
        confidence = mapped[category] / mapped_total
        return category, round(confidence, 3), {
            "model": "efficientnet_b0_imagenet_fallback",
            "topk_labels": [
                {"label": label, "prob": round(prob, 4)} for label, prob in labels_and_probs
            ],
            "mapped_scores": {k: round(v, 4) for k, v in mapped.items()},
        }

    def predict(self, crop: np.ndarray) -> tuple[str, float, dict]:
        if self._model is None or self._torch is None:
            fallback = self._predict_with_imagenet_fallback(crop)
            if fallback is not None:
                return fallback
            h, w = crop.shape[:2]
            ratio = w / max(h, 1)
            category = "shoes" if ratio > 1.35 else "handbag" if ratio > 0.9 else "clothes"
            meta = {"model": "stub_heuristic", "w_h_ratio": round(ratio, 3)}
            if self._load_error:
                meta["load_error"] = self._load_error
            return category, 0.42, meta

        tensor_np = self._preprocess(crop)
        tensor = self._torch.from_numpy(tensor_np).unsqueeze(0)
        with self._torch.no_grad():
            logits = self._model(tensor)
            probs = self._torch.softmax(logits, dim=1)[0].cpu().numpy()
        idx = int(np.argmax(probs))
        category = CATEGORIES[idx]
        confidence = float(probs[idx])
        return category, round(confidence, 3), {
            "model": "efficientnet_b0",
            "weights_path": self.weights_path,
            "probabilities": {label: round(float(probs[i]), 4) for i, label in enumerate(CATEGORIES)},
        }
