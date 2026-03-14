from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
try:
    import torch
    from torch import nn
except Exception:  # pragma: no cover - optional dependency in lightweight environments
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]

from .types import ConditionIssue


GRADES = ["New", "LikeNew", "Good", "Fair", "Poor"]

ISSUE_MAP = {
    "clothes": ["stains", "pilling", "fading", "holes_tears", "fraying"],
    "shoes": ["scuffs", "creasing", "outsole_wear", "missing_laces"],
    "handbag": ["corner_wear", "hardware_scratches", "handle_wear", "lining_stain", "shape_loss"],
}


def _default_issue_labels() -> list[str]:
    labels: list[str] = []
    for issues in ISSUE_MAP.values():
        for label in issues:
            if label not in labels:
                labels.append(label)
    return labels


if nn is not None and torch is not None:
    class _ConditionEfficientNet(nn.Module):
        def __init__(self, issue_labels: list[str]):
            super().__init__()
            import timm  # type: ignore

            self.backbone = timm.create_model("efficientnet_b0", pretrained=False, num_classes=0)
            feat_dim = int(getattr(self.backbone, "num_features", 1280))
            self.grade_head = nn.Linear(feat_dim, len(GRADES))
            self.issue_head = nn.Linear(feat_dim, len(issue_labels))
            self.issue_labels = issue_labels

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            feats = self.backbone(x)
            if feats.ndim > 2:
                feats = torch.flatten(feats, 1)
            return self.grade_head(feats), self.issue_head(feats)


class ConditionModel:
    def __init__(self, weights_path: str | None = None, force_efficientnet: bool = False):
        self.weights_path = weights_path
        self.force_efficientnet = force_efficientnet
        self.available = bool(weights_path and Path(weights_path).exists())
        self._model = None
        self._issue_labels: list[str] = _default_issue_labels()
        self._load_error: str | None = None
        self._fallback_model = None
        self._fallback_transform = None
        self._fallback_categories: list[str] = []
        if self.available:
            try:
                if torch is None:
                    raise RuntimeError("torch_not_installed")
                checkpoint = torch.load(str(self.weights_path), map_location="cpu")
                if isinstance(checkpoint, dict):
                    state = checkpoint.get("state_dict", checkpoint)
                    labels = checkpoint.get("issue_labels")
                    if isinstance(labels, list) and labels:
                        self._issue_labels = [str(x) for x in labels]
                else:
                    state = checkpoint
                if not isinstance(state, dict):
                    raise RuntimeError("invalid checkpoint format")
                cleaned: dict[str, Any] = {}
                for k, v in state.items():
                    cleaned[k[7:] if k.startswith("module.") else k] = v
                model = _ConditionEfficientNet(self._issue_labels)
                model.load_state_dict(cleaned, strict=False)
                model.eval()
                self._model = model
            except Exception as exc:
                self._model = None
                self.available = False
                self._load_error = str(exc)
        if self._model is None and torch is not None and self.force_efficientnet:
            self._init_imagenet_fallback()

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
    def _preprocess(crop: np.ndarray):
        if crop.ndim == 2:
            crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA)
        arr = resized.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
        arr = np.transpose(arr, (2, 0, 1))
        return torch.from_numpy(arr).unsqueeze(0) if torch is not None else arr

    @staticmethod
    def _severity_from_prob(prob: float) -> str:
        if prob >= 0.8:
            return "heavy"
        if prob >= 0.6:
            return "moderate"
        return "light"

    def _predict_with_imagenet_fallback(self, crop: np.ndarray, category: str) -> tuple[str, float, list[ConditionIssue], dict] | None:
        if torch is None or self._fallback_model is None or self._fallback_transform is None:
            return None
        if crop.ndim == 2:
            crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        x = self._fallback_transform(pil).unsqueeze(0)
        with torch.no_grad():
            logits = self._fallback_model(x)
            probs = torch.softmax(logits, dim=1)[0]
            top_vals, top_idx = torch.topk(probs, k=5)

        labels_and_probs: list[tuple[str, float]] = []
        for i in range(top_idx.shape[0]):
            idx = int(top_idx[i].item())
            prob = float(top_vals[i].item())
            label = self._fallback_categories[idx] if idx < len(self._fallback_categories) else f"class_{idx}"
            labels_and_probs.append((label, prob))

        worn_terms = {"worn", "old", "dirty", "damaged", "scratch", "scuffed", "torn", "hole", "stain", "frayed"}
        fresh_terms = {"new", "clean", "polished", "pristine", "mint"}
        wear_signal = 0.0
        fresh_signal = 0.0
        for label, prob in labels_and_probs:
            norm = label.casefold()
            if any(t in norm for t in worn_terms):
                wear_signal += prob
            if any(t in norm for t in fresh_terms):
                fresh_signal += prob
        score = fresh_signal - wear_signal

        if score >= 0.45:
            grade = "New"
        elif score >= 0.2:
            grade = "LikeNew"
        elif score >= -0.1:
            grade = "Good"
        elif score >= -0.35:
            grade = "Fair"
        else:
            grade = "Poor"

        top1 = labels_and_probs[0][1] if labels_and_probs else 0.0
        conf = min(0.7, max(0.35, 0.3 + abs(score) + top1 * 0.3))
        issues: list[ConditionIssue] = []
        if grade in {"Fair", "Poor"}:
            if category == "shoes":
                issues = [ConditionIssue(type="scuffs", severity="moderate" if grade == "Fair" else "heavy")]
            elif category == "handbag":
                issues = [ConditionIssue(type="corner_wear", severity="moderate" if grade == "Fair" else "heavy")]
            elif category == "clothes":
                issues = [ConditionIssue(type="pilling", severity="moderate" if grade == "Fair" else "heavy")]

        return grade, round(float(conf), 3), issues, {
            "model": "efficientnet_b0_imagenet_fallback",
            "forced": True,
            "topk_labels": [{"label": l, "prob": round(p, 4)} for l, p in labels_and_probs],
            "signals": {"fresh": round(fresh_signal, 4), "wear": round(wear_signal, 4), "score": round(score, 4)},
        }

    def predict(self, crop: np.ndarray, category: str) -> tuple[str, float, list[ConditionIssue], dict]:
        if self._model is None or torch is None:
            if self.force_efficientnet:
                fallback = self._predict_with_imagenet_fallback(crop, category)
                if fallback is not None:
                    return fallback
            gray = crop.mean(axis=2) if crop.ndim == 3 else crop
            contrast = float(np.std(gray) / 255.0)
            grade = "Good"
            conf = 0.55 if contrast < 0.2 else 0.45
            issues: list[ConditionIssue] = []
            if category == "shoes":
                issues = [ConditionIssue(type="scuffs", severity="light")]
            elif category == "handbag":
                issues = [ConditionIssue(type="hardware_scratches", severity="light")]
            elif category == "clothes":
                issues = [ConditionIssue(type="pilling", severity="light")]
            meta = {
                "model": "stub_default",
                "contrast_estimate": round(contrast, 3),
                "probabilities": {
                    "New": 0.08,
                    "LikeNew": 0.18,
                    "Good": 0.46,
                    "Fair": 0.2,
                    "Poor": 0.08,
                },
            }
            if self._load_error:
                meta["load_error"] = self._load_error
            return grade, round(conf, 3), issues, meta

        x = self._preprocess(crop)
        with torch.no_grad():
            grade_logits, issue_logits = self._model(x)
            grade_probs = torch.softmax(grade_logits, dim=1)[0].cpu().numpy()
            issue_probs = torch.sigmoid(issue_logits)[0].cpu().numpy()

        grade_idx = int(np.argmax(grade_probs))
        grade = GRADES[grade_idx]
        conf = float(grade_probs[grade_idx])

        issues: list[ConditionIssue] = []
        allowed = set(ISSUE_MAP.get(category, []))
        for i, label in enumerate(self._issue_labels):
            if label not in allowed:
                continue
            prob = float(issue_probs[i])
            if prob < 0.5:
                continue
            issues.append(
                ConditionIssue(
                    type=label,
                    severity=self._severity_from_prob(prob),
                )
            )

        return grade, round(conf, 3), issues, {
            "model": "efficientnet_b0_multitask",
            "weights_path": self.weights_path,
            "probabilities": {label: round(float(grade_probs[i]), 4) for i, label in enumerate(GRADES)},
            "issue_probabilities": {
                label: round(float(issue_probs[i]), 4) for i, label in enumerate(self._issue_labels)
            },
        }
