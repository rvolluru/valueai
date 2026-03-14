from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx

from brand.types import ImageInput


@dataclass(slots=True)
class GptItemProfileResult:
    profile: dict[str, Any] | None
    enabled: bool
    called: bool
    error: str | None = None


class GptItemProfiler:
    def __init__(
        self,
        *,
        enabled: bool,
        api_key: str | None,
        model: str,
        timeout_s: float,
    ):
        self.enabled = enabled
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def profile_item(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
    ) -> GptItemProfileResult:
        if not self.enabled:
            return GptItemProfileResult(profile=None, enabled=False, called=False)
        if not self.api_key:
            return GptItemProfileResult(
                profile=None,
                enabled=True,
                called=False,
                error="OPENAI_API_KEY missing",
            )
        try:
            payload = self._build_payload(
                images=images,
                brand_name=brand_name,
                category=category,
                item_size=item_size,
                condition_grade=condition_grade,
                condition_source=condition_source,
                item_description=item_description,
            )
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
            return GptItemProfileResult(profile=parsed, enabled=True, called=True)
        except Exception as exc:
            return GptItemProfileResult(profile=None, enabled=True, called=True, error=str(exc))

    def _build_payload(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                "You are a fashion resale analyst. Determine probable exact product model, "
                    "perform authenticity screening, and estimate both retail and resale price."
                ),
            },
            {
                "type": "input_text",
                "text": (
                    f"Known context: brand={brand_name}; category={category}; "
                    f"size={item_size or ''}; "
                    f"condition={condition_grade}; condition_source={condition_source}; "
                    f"user_description={item_description or ''}"
                ),
            },
            {
                "type": "input_text",
                "text": (
                    "Important: authenticity output is only a screening signal, never a definitive authentication."
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
                "model_identification": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "attributes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "confidence", "attributes"],
                },
                "authenticity_screen": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "verdict": {
                            "type": "string",
                            "enum": ["likely_authentic", "inconclusive", "likely_counterfeit"],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reasons": {"type": "array", "items": {"type": "string"}},
                        "required_checks": {"type": "array", "items": {"type": "string"}},
                        "disclaimer": {"type": "string"},
                    },
                    "required": ["verdict", "confidence", "reasons", "required_checks", "disclaimer"],
                },
                "retail_price_estimate": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "estimated_price": {"type": ["number", "null"]},
                        "currency": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                        "references": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "source": {"type": "string"},
                                    "url": {"type": ["string", "null"]},
                                },
                                "required": ["source", "url"],
                            },
                        },
                    },
                    "required": ["estimated_price", "currency", "confidence", "rationale", "references"],
                },
                "resale_price_estimate": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "estimated_price": {"type": ["number", "null"]},
                        "currency": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                        "condition_assumption": {"type": "string"},
                        "references": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "source": {"type": "string"},
                                    "url": {"type": ["string", "null"]},
                                },
                                "required": ["source", "url"],
                            },
                        },
                    },
                    "required": [
                        "estimated_price",
                        "currency",
                        "confidence",
                        "rationale",
                        "condition_assumption",
                        "references",
                    ],
                },
            },
            "required": [
                "model_identification",
                "authenticity_screen",
                "retail_price_estimate",
                "resale_price_estimate",
            ],
        }

        return {
            "model": self.model,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "item_profile_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

    def _parse_response(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        text = self._extract_output_text(raw)
        if not text:
            return None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return data

    @staticmethod
    def _extract_output_text(raw: dict[str, Any]) -> str | None:
        if isinstance(raw.get("output_text"), str) and raw["output_text"].strip():
            return raw["output_text"]
        for item in raw.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    txt = content["text"].strip()
                    if txt:
                        return txt
        return None
