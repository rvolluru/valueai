from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from dataclasses import dataclass
from typing import Any

import httpx
from PIL import Image

from brand.types import ImageInput


@dataclass(slots=True)
class GptItemProfileResult:
    profile: dict[str, Any] | None
    enabled: bool
    called: bool
    error: str | None = None


class GptItemProfiler:
    TRUSTED_PRICING_DOMAINS = (
        "rebag.com",
        "poshmark.com",
        "therealreal.com",
        "vestiairecollective.com",
        "fashionphile.com",
        "1stdibs.com",
        "theoutnet.com",
        "net-a-porter.com",
    )
    def __init__(
        self,
        *,
        enabled: bool,
        provider_order: str,
        openai_api_key: str | None,
        openai_model: str,
        gemini_api_key: str | None,
        gemini_model: str,
        timeout_s: float,
        max_images: int,
        image_detail: str,
        reasoning_effort: str,
    ):
        self.enabled = enabled
        self.provider_order = [p.strip().lower() for p in provider_order.split(",") if p.strip()] or ["gemini", "openai"]
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.timeout_s = timeout_s
        self.max_images = max(1, min(max_images, 4))
        self.image_detail = image_detail if image_detail in {"low", "high", "auto"} else "auto"
        self.reasoning_effort = reasoning_effort.strip().lower() if reasoning_effort else ""

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
        schema = self._build_schema()
        provider_errors: list[str] = []
        called = False
        best_partial_profile: dict[str, Any] | None = None
        best_partial_provider: str | None = None
        for provider in self.provider_order:
            if provider == "gemini":
                if not self.gemini_api_key:
                    provider_errors.append("gemini: GEMINI_API_KEY missing")
                    continue
                called = True
                try:
                    parsed = self._call_gemini(
                        images=images,
                        brand_name=brand_name,
                        category=category,
                        item_size=item_size,
                        condition_grade=condition_grade,
                        condition_source=condition_source,
                        item_description=item_description,
                        schema=schema,
                    )
                    if parsed is not None:
                        parsed.setdefault("_provider", "gemini")
                        if not self._has_usable_profile_data(parsed):
                            best_partial_profile = parsed
                            best_partial_provider = "gemini"
                            provider_errors.append("gemini: profile_data_missing_trying_openai")
                            continue
                        if self._has_usable_pricing(parsed):
                            return GptItemProfileResult(profile=parsed, enabled=True, called=True)
                        best_partial_profile = parsed
                        best_partial_provider = "gemini"
                        provider_errors.append("gemini: pricing_missing_trying_openai")
                        continue
                    provider_errors.append("gemini: empty_response")
                except httpx.ReadTimeout:
                    provider_errors.append(f"gemini: timeout after {self.timeout_s:.0f}s")
                except Exception as exc:
                    provider_errors.append(f"gemini: {exc}")
                continue

            if provider == "openai":
                if not self.openai_api_key:
                    provider_errors.append("openai: OPENAI_API_KEY missing")
                    continue
                called = True
                try:
                    parsed = self._call_openai(
                        images=images,
                        brand_name=brand_name,
                        category=category,
                        item_size=item_size,
                        condition_grade=condition_grade,
                        condition_source=condition_source,
                        item_description=item_description,
                        schema=schema,
                    )
                    if parsed is not None:
                        parsed.setdefault("_provider", "openai")
                        if self._has_usable_pricing(parsed):
                            return GptItemProfileResult(profile=parsed, enabled=True, called=True)
                        if best_partial_profile is None:
                            best_partial_profile = parsed
                            best_partial_provider = "openai"
                        provider_errors.append("openai: pricing_missing")
                        continue
                    provider_errors.append("openai: empty_response")
                except httpx.ReadTimeout:
                    provider_errors.append(f"openai: timeout after {self.timeout_s:.0f}s")
                except Exception as exc:
                    provider_errors.append(f"openai: {exc}")
                continue

        if best_partial_profile is not None:
            best_partial_profile.setdefault("_provider", best_partial_provider or "unknown")
            return GptItemProfileResult(
                profile=best_partial_profile,
                enabled=True,
                called=True,
                error="; ".join(provider_errors) if provider_errors else None,
            )
        if not called:
            return GptItemProfileResult(profile=None, enabled=True, called=False, error="; ".join(provider_errors))
        return GptItemProfileResult(profile=None, enabled=True, called=True, error="; ".join(provider_errors))

    @staticmethod
    def _has_usable_pricing(profile: dict[str, Any]) -> bool:
        resale = profile.get("resale_price_estimate")
        if isinstance(resale, dict):
            if isinstance(resale.get("estimated_price"), (int, float)) and float(resale.get("estimated_price")) > 0:
                return True
        breakdown = profile.get("resale_price_breakdown")
        if isinstance(breakdown, list):
            for row in breakdown:
                if not isinstance(row, dict):
                    continue
                price = row.get("estimated_price")
                if isinstance(price, (int, float)) and float(price) > 0:
                    return True
        return False

    @staticmethod
    def _has_usable_profile_data(profile: dict[str, Any]) -> bool:
        candidate_brand = profile.get("candidate_brand")
        if isinstance(candidate_brand, str) and candidate_brand.strip():
            return True
        candidate_model = profile.get("candidate_model")
        if isinstance(candidate_model, str) and candidate_model.strip():
            return True
        model_identification = profile.get("model_identification")
        if isinstance(model_identification, dict):
            model_name = model_identification.get("name")
            if isinstance(model_name, str) and model_name.strip():
                return True
        visual_signatures = profile.get("visual_signatures")
        if isinstance(visual_signatures, list) and any(isinstance(v, str) and v.strip() for v in visual_signatures):
            return True
        return GptItemProfiler._has_usable_pricing(profile)

    def _build_content(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    "Role: You are a Luxury Market Analyst specializing in authenticated luxury fashion pricing and model identification. "
                    "Prioritize precision, evidence-backed conclusions, and market-based valuation language."
                ),
            },
            {
                "type": "input_text",
                "text": (
                    "Identify the specific brand and model of this item by searching Google."
                ),
            },
            {
                "type": "input_text",
                "text": (
                    "Also classify the item category and return exactly one of: clothes, shoes, handbag."
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
        for img in images[: self.max_images]:
            media_type, image_bytes = self._prepare_image_for_llm(img.content_type or "image/jpeg", img.bytes_data)
            b64 = base64.b64encode(image_bytes).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{b64}",
                    "detail": self.image_detail,
                }
            )

        return content

    @staticmethod
    def _prepare_image_for_llm(content_type: str, image_bytes: bytes) -> tuple[str, bytes]:
        normalized_type = (content_type or "").strip().lower()
        should_convert = (
            "webp" in normalized_type
            or normalized_type == ""
            or normalized_type == "application/octet-stream"
        )
        if not should_convert:
            return content_type, image_bytes
        try:
            with Image.open(BytesIO(image_bytes)) as im:
                converted = im.convert("RGB")
                buf = BytesIO()
                converted.save(buf, format="JPEG", quality=92)
                return "image/jpeg", buf.getvalue()
        except Exception:
            return content_type, image_bytes

    @staticmethod
    def _build_schema() -> dict[str, Any]:
        return {
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
                "category": {
                    "type": "string",
                    "enum": ["clothes", "shoes", "handbag"],
                },
                "candidate_brand": {"type": ["string", "null"]},
                "candidate_model": {"type": ["string", "null"]},
                "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "visual_signatures": {"type": "array", "items": {"type": "string"}},
                "grounding_sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "domain": {"type": "string"},
                            "url": {"type": ["string", "null"]},
                            "snippet": {"type": ["string", "null"]},
                        },
                        "required": ["domain", "url", "snippet"],
                    },
                },
                "dupe_risk_assessment": {"type": ["string", "null"]},
                "why_not_fast_fashion": {"type": ["string", "null"]},
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
                "resale_price_breakdown": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "estimated_price": {"type": ["number", "null"]},
                            "range_low": {"type": ["number", "null"]},
                            "range_high": {"type": ["number", "null"]},
                            "currency": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "rationale": {"type": "string"},
                        },
                        "required": [
                            "label",
                            "estimated_price",
                            "range_low",
                            "range_high",
                            "currency",
                            "confidence",
                            "rationale",
                        ],
                    },
                    "minItems": 1,
                },
                "receipt_present": {
                    "type": ["string", "null"],
                    "enum": ["yes", "no", "unclear", None],
                },
                "expected_auth_docs": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "usually_provided": {
                            "type": "string",
                            "enum": ["yes", "no", "mixed", "unknown"],
                        },
                        "typical_documents": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "notes": {"type": "string"},
                    },
                    "required": ["usually_provided", "typical_documents", "confidence", "notes"],
                },
            },
            "required": [
                "model_identification",
                "category",
                "candidate_brand",
                "candidate_model",
                "confidence",
                "visual_signatures",
                "grounding_sources",
                "dupe_risk_assessment",
                "why_not_fast_fashion",
                "authenticity_screen",
                "retail_price_estimate",
                "resale_price_estimate",
                "resale_price_breakdown",
                "receipt_present",
                "expected_auth_docs",
            ],
        }

    def _build_openai_payload(self, *, content: list[dict[str, Any]], schema: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.openai_model,
            "input": [{"role": "user", "content": content}],
            "tools": [{"type": "web_search_preview"}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "item_profile_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        return payload

    def _build_gemini_parts(self, *, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        gemini_parts: list[dict[str, Any]] = []
        for entry in content:
            etype = entry.get("type")
            if etype == "input_text":
                gemini_parts.append({"text": str(entry.get("text") or "")})
            elif etype == "input_image":
                image_url = str(entry.get("image_url") or "")
                if not image_url.startswith("data:") or ";base64," not in image_url:
                    continue
                head, b64 = image_url.split(";base64,", 1)
                mime_type = head.replace("data:", "", 1) or "image/jpeg"
                gemini_parts.append(
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64,
                        }
                    }
                )
        return gemini_parts

    def _build_gemini_feature_payload(self, *, content: list[dict[str, Any]]) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Stage 1/4 - Visual Feature Extraction. "
                    "Analyze this luxury item and list specific unlabeled visual signatures: "
                    "hardware shape, stitching patterns, logo placement (even if blurred), "
                    "and unique design motifs (textures, flames, quilting, etc). "
                    "Output concise bullet points only."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "generationConfig": {"temperature": 0.2},
        }

    def _build_gemini_single_call_payload(self, *, content: list[dict[str, Any]]) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Single-call task: identify exact luxury item model and produce grounded pricing in one response.\n"
                    "Constraints:\n"
                    "1) Identify exact category, brand, and model from the image.\n"
                    "2) Use Google grounding and prioritize: Rebag, Poshmark, The RealReal, Vestiaire Collective, "
                    "1stdibs, Fashionphile. De-prioritize eBay unless needed.\n"
                    "3) Compute resale pricing specifically for the identified category/model and current item condition.\n"
                    "4) Provide a resale breakdown including median and range by condition when available.\n"
                    "5) Return ONLY JSON. No prose.\n\n"
                    "JSON keys required:\n"
                    "category, candidate_brand, candidate_model, confidence, visual_signatures, grounding_sources, "
                    "dupe_risk_assessment, why_not_fast_fashion, model_identification, authenticity_screen, "
                    "retail_price_estimate, resale_price_estimate, resale_price_breakdown, receipt_present, expected_auth_docs.\n"
                    "For resale_price_breakdown include rows close to: Good/Pre-owned Condition, "
                    "High-End/Excellent Condition, Original Retail Value (or closest equivalent labels).\n"
                    "Use numeric prices whenever possible; include rationale and confidence."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.2,
            },
        }

    def _build_gemini_grounded_search_payload(self, *, content: list[dict[str, Any]]) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Step 1/2 - Grounded Evidence Collection.\n"
                    "Identify the exact category, brand, and model from the image. "
                    "Use Google grounding and ONLY use these websites, in this strict priority order:\n"
                    "Tier 1: 1) The RealReal, 2) Vestiaire Collective, 3) Fashionphile, 4) Rebag.\n"
                    "Tier 2: 5) eBay, 6) Poshmark.\n"
                    "Tier 3: 7) Depop, 8) Vinted.\n"
                    "Prefer higher tiers first; only use lower tiers when higher-tier evidence is insufficient.\n"
                    "Collect pricing evidence relevant to the identified model and current condition, including "
                    "median-like central value and condition-based ranges when available.\n"
                    "Return concise evidence text with sources and numeric price mentions."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.3},
        }

    def _build_gemini_formatter_payload(self, *, content: list[dict[str, Any]], grounded_text: str) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Step 2/2 - Structured JSON Formatter.\n"
                    "Use the grounded evidence below to produce final structured output.\n\n"
                    f"Grounded evidence:\n{grounded_text}\n\n"
                    "Return ONLY a JSON object with keys exactly:\n"
                    "category, candidate_brand, candidate_model, confidence, visual_signatures, grounding_sources, "
                    "dupe_risk_assessment, why_not_fast_fashion, model_identification, authenticity_screen, "
                    "retail_price_estimate, resale_price_estimate, resale_price_breakdown, receipt_present, expected_auth_docs.\n"
                    "Use numeric values for estimated_price/ranges whenever possible. No markdown, no prose."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0,
            },
        }

    def _build_gemini_search_payload(self, *, content: list[dict[str, Any]], visual_signatures: str) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Stage 2/4 - High-Precision Grounded Search. "
                    f"Search for the item described by these visual signatures:\n{visual_signatures}\n\n"
                    "Prioritize results from: Rebag, Poshmark, The RealReal, Vestiaire Collective, 1stdibs, Fashionphile. "
                    "De-prioritize eBay unless no strong matches are found on the preferred domains. "
                    "Identify likely Maison (brand) and specific collection/model candidates with evidence and URLs. "
                    "Provide a breakdown including the median price and price ranges based on condition."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 1.0},
        }

    def _build_gemini_conflict_payload(self, *, content: list[dict[str, Any]], identification_text: str) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Stage 3/4 - Conflict Resolution.\n"
                    "Using this identification evidence, compare the likely luxury match against common dupes or fast-fashion alternatives.\n"
                    f"{identification_text}\n\n"
                    "Explain why non-luxury alternatives are less likely based on construction quality, materials, and hardware."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "generationConfig": {"temperature": 0.2},
        }

    def _build_gemini_format_payload(
        self,
        *,
        content: list[dict[str, Any]],
        search_text: str,
        conflict_text: str,
    ) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Stage 4/4 - Structured Formatter.\n"
                    "Use these contexts to produce final output.\n\n"
                    "Grounded identification context:\n"
                    f"{search_text}\n\n"
                    "Conflict resolution context:\n"
                    f"{conflict_text}\n\n"
                    "Now return ONLY a strict JSON object with keys exactly: "
                    "category, candidate_brand, candidate_model, confidence, visual_signatures, grounding_sources, "
                    "dupe_risk_assessment, why_not_fast_fashion, model_identification, authenticity_screen, "
                    "retail_price_estimate, resale_price_estimate, resale_price_breakdown, receipt_present, expected_auth_docs. "
                    "For resale_price_breakdown, include these rows when available from sources: "
                    "'Good/Pre-owned Condition', 'High-End/Excellent Condition', and 'Original Retail Value'. "
                    "If an exact row is unavailable, include the closest equivalent label and provide rationale. "
                    "No markdown, no prose."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0,
            },
        }

    def _call_openai(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
        schema: dict[str, Any],
    ) -> dict[str, Any] | None:
        content = self._build_content(
            images=images,
            brand_name=brand_name,
            category=category,
            item_size=item_size,
            condition_grade=condition_grade,
            condition_source=condition_source,
            item_description=item_description,
        )
        payload = self._build_openai_payload(content=content, schema=schema)
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"openai_http_{resp.status_code}: {resp.text[:600]}")
            raw = resp.json()
        return self._parse_response(raw)

    def _call_gemini(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
        schema: dict[str, Any],
    ) -> dict[str, Any] | None:
        content = self._build_content(
            images=images,
            brand_name=brand_name,
            category=category,
            item_size=item_size,
            condition_grade=condition_grade,
            condition_source=condition_source,
            item_description=item_description,
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        grounding_metadata: dict[str, Any] | None = None
        workflow: dict[str, Any] = {}
        with httpx.Client(timeout=self.timeout_s) as client:
            # Step 1/2: grounded search with tool-use.
            search_resp = client.post(
                url,
                params={"key": self.gemini_api_key},
                headers={"Content-Type": "application/json"},
                json=self._build_gemini_grounded_search_payload(content=content),
            )
            if search_resp.status_code >= 400:
                raise RuntimeError(f"gemini_http_{search_resp.status_code}: {search_resp.text[:600]}")
            search_raw = search_resp.json()
            grounding_metadata = self._extract_gemini_grounding_metadata(search_raw)
            grounded_text = self._extract_gemini_text(search_raw) or ""
            workflow["grounded_search"] = grounded_text

            # Step 2/2: strict JSON formatting without tools.
            format_resp = client.post(
                url,
                params={"key": self.gemini_api_key},
                headers={"Content-Type": "application/json"},
                json=self._build_gemini_formatter_payload(content=content, grounded_text=grounded_text),
            )
            if format_resp.status_code >= 400:
                raise RuntimeError(f"gemini_http_{format_resp.status_code}: {format_resp.text[:600]}")
            format_raw = format_resp.json()
        parsed_single = self._parse_gemini_response(format_raw)
        if not isinstance(parsed_single, dict):
            raise RuntimeError("gemini_two_step_parse_failed")
        if isinstance(grounding_metadata, dict):
            grounding_sources = self._grounding_sources_from_metadata(grounding_metadata)
            if grounding_sources:
                parsed_single["grounding_sources"] = grounding_sources
            parsed_single["_grounding_metadata"] = grounding_metadata
        parsed_single["_workflow"] = workflow
        return parsed_single

    def _parse_response(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        text = self._extract_output_text(raw)
        if not text:
            return None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return self._normalize_profile_shape(data)

    def _parse_gemini_response(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        text = self._extract_gemini_text(raw)
        if not text:
            return None
        data = self._parse_json_relaxed(text)
        if not isinstance(data, dict):
            return None
        return self._normalize_profile_shape(data)

    def _normalize_profile_shape(self, data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(data)
        normalized["category"] = self._normalize_category(normalized.get("category"))
        normalized["candidate_brand"] = self._as_nullable_str(normalized.get("candidate_brand"))
        normalized["candidate_model"] = self._as_nullable_str(normalized.get("candidate_model"))
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        normalized["visual_signatures"] = self._as_str_list(normalized.get("visual_signatures"))
        normalized["grounding_sources"] = self._normalize_grounding_sources(normalized.get("grounding_sources"))
        normalized["dupe_risk_assessment"] = self._as_nullable_str(normalized.get("dupe_risk_assessment"))
        normalized["why_not_fast_fashion"] = self._as_nullable_str(normalized.get("why_not_fast_fashion"))
        normalized["model_identification"] = self._normalize_model_identification(
            normalized.get("model_identification"),
            candidate_model=normalized.get("candidate_model"),
            candidate_brand=normalized.get("candidate_brand"),
            visual_signatures=normalized.get("visual_signatures"),
        )
        normalized["authenticity_screen"] = self._normalize_authenticity_screen(normalized.get("authenticity_screen"))
        normalized["retail_price_estimate"] = self._normalize_price_estimate(normalized.get("retail_price_estimate"))
        normalized["resale_price_estimate"] = self._normalize_price_estimate(normalized.get("resale_price_estimate"))
        normalized["resale_price_breakdown"] = self._normalize_resale_price_breakdown(
            normalized.get("resale_price_breakdown"),
            fallback=normalized.get("resale_price_estimate"),
        )
        normalized["receipt_present"] = self._normalize_receipt_present(normalized.get("receipt_present"))
        normalized["expected_auth_docs"] = self._normalize_expected_auth_docs(normalized.get("expected_auth_docs"))
        return normalized

    @staticmethod
    def _as_nullable_str(value: Any) -> str | None:
        if isinstance(value, str):
            txt = value.strip()
            return txt or None
        return None

    @staticmethod
    def _normalize_category(value: Any) -> str:
        if isinstance(value, str):
            norm = value.strip().casefold()
            if norm == "handbags":
                return "handbag"
            if norm in {"clothes", "shoes", "handbag"}:
                return norm
        return "clothes"

    @staticmethod
    def _normalize_confidence(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        if isinstance(value, str):
            txt = value.strip().lower()
            label_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
            if txt in label_map:
                return label_map[txt]
            try:
                return max(0.0, min(float(txt), 1.0))
            except Exception:
                return None
        return None

    @staticmethod
    def _as_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
        if isinstance(value, str):
            split_parts = re.split(r"[\n,;]+", value)
            return [p.strip("- ").strip() for p in split_parts if p and p.strip("- ").strip()]
        return []

    def _normalize_grounding_sources(self, value: Any) -> list[dict[str, str | None]]:
        sources: list[dict[str, str | None]] = []
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    domain = self._as_nullable_str(entry.get("domain")) or ""
                    url = self._as_nullable_str(entry.get("url"))
                    snippet = self._as_nullable_str(entry.get("snippet"))
                    if not domain and url:
                        domain = self._extract_domain(url)
                    if domain or url or snippet:
                        sources.append({"domain": domain or "unknown", "url": url, "snippet": snippet})
                elif isinstance(entry, str):
                    text = entry.strip()
                    if text:
                        sources.append({"domain": self._extract_domain(text), "url": text, "snippet": None})
        elif isinstance(value, str):
            text = value.strip()
            if text:
                sources.append({"domain": self._extract_domain(text), "url": text, "snippet": None})
        return sources

    def _normalize_model_identification(
        self,
        value: Any,
        *,
        candidate_model: Any,
        candidate_brand: Any,
        visual_signatures: Any,
    ) -> dict[str, Any]:
        model_name = None
        confidence = None
        attributes: list[str] = []

        if isinstance(value, dict):
            model_name = self._as_nullable_str(value.get("name"))
            confidence = self._normalize_confidence(value.get("confidence"))
            attributes = self._as_str_list(value.get("attributes"))
        elif isinstance(value, str):
            model_name = value.strip() or None

        if not model_name and isinstance(candidate_model, str) and candidate_model.strip():
            model_name = candidate_model.strip()
        if not attributes:
            attributes = self._as_str_list(visual_signatures)
        if not model_name and isinstance(candidate_brand, str) and candidate_brand.strip():
            model_name = f"{candidate_brand.strip()} item"
        model_name = self._sanitize_model_name(
            model_name,
            candidate_brand=self._as_nullable_str(candidate_brand),
            candidate_model=self._as_nullable_str(candidate_model),
        )
        if confidence is None:
            confidence = 0.5

        return {"name": model_name, "confidence": confidence, "attributes": attributes}

    def _normalize_authenticity_screen(self, value: Any) -> dict[str, Any]:
        fallback = {
            "verdict": "inconclusive",
            "confidence": 0.5,
            "reasons": [],
            "required_checks": [],
            "disclaimer": "Screening signal only; not definitive authentication.",
        }
        if isinstance(value, dict):
            verdict = self._as_nullable_str(value.get("verdict")) or "inconclusive"
            if verdict not in {"likely_authentic", "inconclusive", "likely_counterfeit"}:
                verdict = "inconclusive"
            return {
                "verdict": verdict,
                "confidence": self._normalize_confidence(value.get("confidence")) or 0.5,
                "reasons": self._as_str_list(value.get("reasons")),
                "required_checks": self._as_str_list(value.get("required_checks")),
                "disclaimer": self._as_nullable_str(value.get("disclaimer")) or fallback["disclaimer"],
            }
        if isinstance(value, str) and value.strip():
            fallback["reasons"] = [value.strip()]
        return fallback

    def _normalize_price_estimate(self, value: Any) -> dict[str, Any]:
        fallback = {
            "estimated_price": None,
            "currency": "USD",
            "confidence": 0.5,
            "rationale": "",
            "references": [],
        }
        if isinstance(value, dict):
            refs: list[dict[str, str | None]] = []
            raw_refs = value.get("references")
            if isinstance(raw_refs, list):
                for ref in raw_refs:
                    if not isinstance(ref, dict):
                        continue
                    source = self._as_nullable_str(ref.get("source"))
                    url = self._as_nullable_str(ref.get("url"))
                    if source or url:
                        refs.append({"source": source or "unknown", "url": url})
            refs = self._filter_pricing_references(refs)
            rationale = self._as_nullable_str(value.get("rationale")) or ""
            estimated_price = self._coerce_price(value.get("estimated_price"))
            parsed_range = self._extract_price_range_from_text(rationale) if rationale else None
            if estimated_price is None:
                range_candidates = [
                    self._coerce_price(value.get("range_low")),
                    self._coerce_price(value.get("range_high")),
                    self._coerce_price(value.get("low")),
                    self._coerce_price(value.get("high")),
                    self._coerce_price(value.get("min")),
                    self._coerce_price(value.get("max")),
                ]
                nums = [n for n in range_candidates if isinstance(n, (int, float))]
                if len(nums) == 1:
                    estimated_price = round(float(nums[0]), 2)
                elif len(nums) >= 2:
                    estimated_price = round((float(nums[0]) + float(nums[1])) / 2.0, 2)
            if estimated_price is None and parsed_range is not None:
                estimated_price = round((parsed_range[0] + parsed_range[1]) / 2.0, 2)
            if estimated_price is None and rationale:
                estimated_price = self._extract_price_from_text(rationale)
            if estimated_price is not None and parsed_range is not None:
                low, high = parsed_range
                # Correct clearly inconsistent estimates against explicit rationale ranges.
                if estimated_price < low or estimated_price > high:
                    estimated_price = round((low + high) / 2.0, 2)
            base_confidence = self._normalize_confidence(value.get("confidence")) or 0.5
            trusted_ref_count = sum(1 for r in refs if self._is_trusted_pricing_ref(r))
            if trusted_ref_count == 0:
                base_confidence = min(base_confidence, 0.35)
            elif trusted_ref_count == 1:
                base_confidence = min(base_confidence, 0.5)
            else:
                base_confidence = min(max(base_confidence, 0.55), 0.95)
            return {
                **fallback,
                "estimated_price": estimated_price,
                "currency": self._as_nullable_str(value.get("currency")) or "USD",
                "confidence": base_confidence,
                "rationale": rationale,
                "references": refs,
                **(
                    {
                        "condition_assumption": self._as_nullable_str(value.get("condition_assumption")) or "",
                    }
                    if "condition_assumption" in value
                    else {}
                ),
            }
        if isinstance(value, str):
            rationale = value.strip()
            return {**fallback, "estimated_price": self._extract_price_from_text(rationale), "rationale": rationale}
        return fallback

    def _filter_pricing_references(self, refs: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
        if not refs:
            return refs
        trusted = [r for r in refs if self._is_trusted_pricing_ref(r)]
        if trusted:
            return trusted[:8]
        cleaned: list[dict[str, str | None]] = []
        seen: set[tuple[str | None, str | None]] = set()
        for ref in refs:
            key = (ref.get("source"), ref.get("url"))
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(ref)
        return cleaned[:8]

    def _is_trusted_pricing_ref(self, ref: dict[str, str | None]) -> bool:
        source = (ref.get("source") or "").casefold()
        url = (ref.get("url") or "").casefold()
        domains = [self._extract_domain(url)] if url else []
        domains.append(source)
        for dom in domains:
            for trusted in self.TRUSTED_PRICING_DOMAINS:
                if trusted in dom:
                    return True
        return False

    @staticmethod
    def _normalize_receipt_present(value: Any) -> str:
        if isinstance(value, str):
            norm = value.strip().casefold()
            if norm in {"yes", "no", "unclear"}:
                return norm
        return "unclear"

    def _normalize_expected_auth_docs(self, value: Any) -> dict[str, Any]:
        fallback = {
            "usually_provided": "unknown",
            "typical_documents": [],
            "confidence": 0.5,
            "notes": "",
        }
        if not isinstance(value, dict):
            return fallback
        usually = self._as_nullable_str(value.get("usually_provided")) or "unknown"
        if usually not in {"yes", "no", "mixed", "unknown"}:
            usually = "unknown"
        return {
            "usually_provided": usually,
            "typical_documents": self._as_str_list(value.get("typical_documents")),
            "confidence": self._normalize_confidence(value.get("confidence")) or 0.5,
            "notes": self._as_nullable_str(value.get("notes")) or "",
        }

    def _normalize_resale_price_breakdown(self, value: Any, *, fallback: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                label = self._as_nullable_str(entry.get("label")) or "default"
                est = self._coerce_price(entry.get("estimated_price"))
                low = self._coerce_price(entry.get("range_low"))
                high = self._coerce_price(entry.get("range_high"))
                rationale = self._as_nullable_str(entry.get("rationale")) or ""
                if est is None and rationale:
                    est = self._extract_price_from_text(rationale)
                if est is None and low is not None and high is not None:
                    est = round((low + high) / 2.0, 2)
                rows.append(
                    {
                        "label": label,
                        "estimated_price": est,
                        "range_low": low,
                        "range_high": high,
                        "currency": self._as_nullable_str(entry.get("currency")) or "USD",
                        "confidence": self._normalize_confidence(entry.get("confidence")) or 0.5,
                        "rationale": rationale,
                    }
                )
        elif isinstance(value, dict):
            for label, entry in value.items():
                if not isinstance(entry, dict):
                    continue
                est = self._coerce_price(entry.get("estimated_price"))
                low = self._coerce_price(entry.get("range_low") or entry.get("low"))
                high = self._coerce_price(entry.get("range_high") or entry.get("high"))
                rationale = self._as_nullable_str(entry.get("rationale")) or ""
                if est is None and rationale:
                    est = self._extract_price_from_text(rationale)
                rows.append(
                    {
                        "label": str(label),
                        "estimated_price": est,
                        "range_low": low,
                        "range_high": high,
                        "currency": self._as_nullable_str(entry.get("currency")) or "USD",
                        "confidence": self._normalize_confidence(entry.get("confidence")) or 0.5,
                        "rationale": rationale,
                    }
                )
        if rows:
            return rows

        # Fallback: derive one default row from normalized resale_price_estimate
        if isinstance(fallback, dict):
            return [
                {
                    "label": "default",
                    "estimated_price": self._coerce_price(fallback.get("estimated_price")),
                    "range_low": self._coerce_price(fallback.get("range_low")),
                    "range_high": self._coerce_price(fallback.get("range_high")),
                    "currency": self._as_nullable_str(fallback.get("currency")) or "USD",
                    "confidence": self._normalize_confidence(fallback.get("confidence")) or 0.5,
                    "rationale": self._as_nullable_str(fallback.get("rationale")) or "",
                }
            ]
        return []

    @staticmethod
    def _coerce_price(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return round(float(value), 2)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            try:
                return round(float(cleaned), 2)
            except Exception:
                return None
        return None

    @staticmethod
    def _extract_price_from_text(text: str) -> float | None:
        txt = text.strip()
        if not txt:
            return None
        txt = re.sub(r"(?i)\busd\b", "$", txt)
        compact = re.sub(r"\s+", " ", txt)

        # Prefer currency-denominated ranges first (avoids treating percentage bands like 50-60 as prices).
        parsed_range = GptItemProfiler._extract_price_range_from_text(compact, require_currency=True)
        if parsed_range is not None:
            return round((parsed_range[0] + parsed_range[1]) / 2.0, 2)

        # Prefer explicit currency-denominated scalar values (e.g., "$950", "$1,699").
        dollar_numbers = re.findall(r"\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)", compact)
        if dollar_numbers:
            vals: list[float] = []
            for n in dollar_numbers:
                try:
                    vals.append(float(n.replace(",", "")))
                except Exception:
                    continue
            if vals:
                if len(vals) == 1:
                    return round(vals[0], 2)
                return round(sum(vals) / len(vals), 2)

        # e.g. "1.2k", "2k"
        k_vals = re.findall(r"(?i)\$?\s*(\d+(?:\.\d+)?)\s*k\b", compact)
        if k_vals:
            vals: list[float] = []
            for kv in k_vals:
                try:
                    vals.append(float(kv) * 1000.0)
                except Exception:
                    continue
            if vals:
                return round(sum(vals) / len(vals), 2)

        # e.g. "$400 - $700", "400 to 700", "between 400 and 700"
        parsed_range = GptItemProfiler._extract_price_range_from_text(compact, require_currency=False)
        if parsed_range is not None:
            return round((parsed_range[0] + parsed_range[1]) / 2.0, 2)

        numbers = re.findall(r"\$?\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)", compact)
        vals: list[float] = []
        for n in numbers:
            try:
                vals.append(float(n.replace(",", "")))
            except Exception:
                continue
        if not vals:
            return None
        if len(vals) == 1:
            return round(vals[0], 2)
        return round(sum(vals) / len(vals), 2)

    @staticmethod
    def _extract_price_range_from_text(text: str, *, require_currency: bool = False) -> tuple[float, float] | None:
        compact = re.sub(r"\s+", " ", text.strip())
        if require_currency:
            range_pattern = r"(?i)(?:between\s*)?\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(?:-|to|and)\s*\$?\s*(\d{1,6}(?:,\d{3})*(?:\.\d+)?)"
        else:
            range_pattern = r"(?i)(?:between\s*)?\$?\s*(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(?:-|to|and)\s*\$?\s*(\d{1,6}(?:,\d{3})*(?:\.\d+)?)"
        range_match = re.search(range_pattern, compact)
        if not range_match:
            return None
        try:
            a = float(range_match.group(1).replace(",", ""))
            b = float(range_match.group(2).replace(",", ""))
            low, high = (a, b) if a <= b else (b, a)
            return (round(low, 2), round(high, 2))
        except Exception:
            return None

    @staticmethod
    def _extract_domain(value: str) -> str:
        txt = value.strip()
        m = re.search(r"https?://([^/\s]+)", txt, flags=re.IGNORECASE)
        if m:
            return m.group(1).lower()
        m2 = re.search(r"\b([a-z0-9.-]+\.[a-z]{2,})\b", txt, flags=re.IGNORECASE)
        return m2.group(1).lower() if m2 else "unknown"

    @staticmethod
    def _sanitize_model_name(model_name: str | None, *, candidate_brand: str | None, candidate_model: str | None) -> str | None:
        if not model_name:
            if candidate_brand and candidate_model:
                return f"{candidate_brand} {candidate_model}"
            return candidate_model or model_name
        txt = model_name.strip()
        txt = re.sub(r"(?i)^the item is identified as\s*", "", txt).strip(" .:-")
        txt = re.sub(r"(?i)^the model is identified as\s*", "", txt).strip(" .:-")
        txt = re.sub(r"(?i)^this item is\s*", "", txt).strip(" .:-")
        txt = re.sub(r"(?i)^identified as\s*", "", txt).strip(" .:-")
        txt = re.sub(r"(?i)^(the|a|an)\s+", "", txt).strip(" .:-")
        if candidate_brand and candidate_model:
            lower = txt.casefold()
            if (
                len(txt) < 6
                or len(txt) > 90
                or lower in {"identified", "item", "model", "unknown"}
                or "characteristic of" in lower
                or "branding on the insole" in lower
                or "confirms the brand" in lower
                or "identified as" in lower
                or "is a" in lower
                or "is the" in lower
            ):
                return f"{candidate_brand} {candidate_model}"
        return txt or (f"{candidate_brand} {candidate_model}" if candidate_brand and candidate_model else candidate_model)

    def _grounding_sources_from_metadata(self, metadata: dict[str, Any]) -> list[dict[str, str | None]]:
        chunks = metadata.get("groundingChunks")
        if not isinstance(chunks, list):
            return []
        results: list[dict[str, str | None]] = []
        seen: set[tuple[str, str | None]] = set()
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            web = chunk.get("web")
            if not isinstance(web, dict):
                continue
            url = self._as_nullable_str(web.get("uri"))
            title = self._as_nullable_str(web.get("title"))
            if not url:
                continue
            domain = self._extract_domain(url)
            key = (domain, url)
            if key in seen:
                continue
            seen.add(key)
            results.append({"domain": domain, "url": url, "snippet": title})
        return results

    @staticmethod
    def _parse_json_relaxed(text: str) -> dict[str, Any] | None:
        txt = text.strip()
        try:
            parsed = json.loads(txt)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", txt, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            try:
                parsed = json.loads(fence.group(1))
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                pass

        start = txt.find("{")
        end = txt.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = txt[start : end + 1]
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
        return None

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

    @staticmethod
    def _extract_gemini_text(raw: dict[str, Any]) -> str | None:
        candidates = raw.get("candidates")
        if not isinstance(candidates, list):
            return None
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None

    @staticmethod
    def _extract_gemini_grounding_metadata(raw: dict[str, Any]) -> dict[str, Any] | None:
        candidates = raw.get("candidates")
        if not isinstance(candidates, list):
            return None
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            metadata = candidate.get("groundingMetadata")
            if isinstance(metadata, dict):
                return metadata
        return None
