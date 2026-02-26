from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx

from .brands import BrandRecord
from .types import BrandCandidate, ImageInput


@dataclass(slots=True)
class GptVisionResult:
    candidate: BrandCandidate | None
    raw: dict[str, Any]
    enabled: bool
    called: bool
    error: str | None = None


class GptVisionBrandClassifier:
    def __init__(self, enabled: bool, api_key: str | None, model: str, timeout_s: float = 20.0):
        self.enabled = enabled
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def classify(self, images: list[ImageInput], brands: list[BrandRecord]) -> GptVisionResult:
        if not self.enabled:
            return GptVisionResult(candidate=None, raw={}, enabled=False, called=False)
        if not self.api_key:
            return GptVisionResult(
                candidate=None,
                raw={},
                enabled=True,
                called=False,
                error="OPENAI_API_KEY missing",
            )

        try:
            payload = self._build_payload(images, brands)
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                raw = resp.json()
            parsed = self._parse_response(raw)
            return GptVisionResult(candidate=parsed, raw=raw, enabled=True, called=True)
        except Exception as exc:
            return GptVisionResult(
                candidate=None,
                raw={},
                enabled=True,
                called=True,
                error=str(exc),
            )

    def _build_payload(self, images: list[ImageInput], brands: list[BrandRecord]) -> dict[str, Any]:
        brand_names = [b.canonical for b in brands]
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    "You are a brand recognition assistant for fashion resale. "
                    "Infer brand from logo, monogram, hardware marks, wordmarks, or tag visuals. "
                    "Return unknown when uncertain. Only choose from the provided brand list."
                ),
            },
            {
                "type": "input_text",
                "text": (
                    "Brand list (canonical names): " + ", ".join(brand_names)
                ),
            },
            {
                "type": "input_text",
                "text": (
                    "Use evidence from visible logos/monograms/text only. Do not invent brands. "
                    "If image evidence is weak/blurred/partial, set unknown=true and confidence low."
                ),
            },
        ]
        for img in images[:4]:
            b64 = base64.b64encode(img.bytes_data).decode("ascii")
            media_type = img.content_type or "image/jpeg"
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{b64}",
                    "detail": "high" if (img.role_hint or "") != "full_item" else "auto",
                }
            )

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "unknown": {"type": "boolean"},
                "brand": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence_type": {
                    "type": "string",
                    "enum": ["logo", "monogram", "hardware", "wordmark", "tag", "unclear"],
                },
                "reason": {"type": "string"},
            },
            "required": ["unknown", "brand", "confidence", "evidence_type", "reason"],
        }

        return {
            "model": self.model,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "brand_vision_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

    def _parse_response(self, raw: dict[str, Any]) -> BrandCandidate | None:
        text = self._extract_output_text(raw)
        if not text:
            return None
        data = json.loads(text)
        if data.get("unknown", True):
            return None
        brand = data.get("brand")
        conf = float(data.get("confidence", 0.0))
        if not brand or conf <= 0:
            return None
        return BrandCandidate(
            name=str(brand),
            score=round(max(0.0, min(conf, 1.0)) * 100.0, 2),
            evidence="gpt_vision_logo",
            metadata={
                "confidence_01": round(max(0.0, min(conf, 1.0)), 3),
                "evidence_type": data.get("evidence_type", "unclear"),
                "reason": data.get("reason", ""),
                "source": "openai_responses_api",
                "model": raw.get("model"),
            },
        )

    def _extract_output_text(self, raw: dict[str, Any]) -> str | None:
        # Handle common response shapes from the Responses API.
        if isinstance(raw.get("output_text"), str) and raw["output_text"].strip():
            return raw["output_text"]
        for item in raw.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    txt = content["text"].strip()
                    if txt:
                        return txt
        return None
