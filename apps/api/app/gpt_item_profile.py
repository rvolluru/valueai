from __future__ import annotations

import base64
import hashlib
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
        "bergdorfgoodman.com",
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
        vertex_search_enabled: bool = False,
        vertex_project_id: str | None = None,
        vertex_location: str = "global",
        vertex_model: str | None = None,
        vertex_data_store: str | None = None,
        vertex_access_token: str | None = None,
        vertex_max_results: int = 10,
    ):
        self.enabled = enabled
        self.provider_order = [p.strip().lower() for p in provider_order.split(",") if p.strip()] or ["gemini", "openai"]
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.vertex_search_enabled = vertex_search_enabled
        self.vertex_project_id = vertex_project_id
        self.vertex_location = vertex_location.strip() if vertex_location else "global"
        self.vertex_model = vertex_model or gemini_model
        self.vertex_data_store = vertex_data_store
        self.vertex_access_token = vertex_access_token
        self.vertex_max_results = max(1, min(vertex_max_results, 20))
        self.timeout_s = timeout_s
        self.max_images = max(1, min(max_images, 6))
        self.image_detail = image_detail if image_detail in {"low", "high", "auto"} else "auto"
        self.reasoning_effort = reasoning_effort.strip().lower() if reasoning_effort else ""
        self._profile_cache: dict[str, dict[str, Any]] = {}

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
        cache_key = self._cache_key(
            images=images,
            brand_name=brand_name,
            category=category,
            item_size=item_size,
            condition_grade=condition_grade,
            condition_source=condition_source,
            item_description=item_description,
        )
        cached = self._profile_cache.get(cache_key)
        if isinstance(cached, dict):
            return GptItemProfileResult(profile=dict(cached), enabled=True, called=True)
        schema = self._build_schema()
        provider_errors: list[str] = []
        called = False
        best_partial_profile: dict[str, Any] | None = None
        best_partial_provider: str | None = None
        for provider in self.provider_order:
            if provider in {"hybrid", "gemini_openai", "gemini_openai_valuation"}:
                if not self.gemini_api_key:
                    provider_errors.append("hybrid: GEMINI_API_KEY missing")
                    continue
                if not self.openai_api_key:
                    provider_errors.append("hybrid: OPENAI_API_KEY missing")
                    continue
                called = True
                try:
                    parsed = self._call_gemini_openai_hybrid(
                        images=images,
                        brand_name=brand_name,
                        category=category,
                        item_size=item_size,
                        condition_grade=condition_grade,
                        condition_source=condition_source,
                        item_description=item_description,
                    )
                    if parsed is not None:
                        parsed.setdefault("_provider", "hybrid")
                        if self._has_usable_profile_data(parsed) and self._has_usable_pricing(parsed):
                            self._profile_cache[cache_key] = dict(parsed)
                            return GptItemProfileResult(profile=parsed, enabled=True, called=True)
                        best_partial_profile = parsed
                        best_partial_provider = "hybrid"
                        provider_errors.append("hybrid: weak_or_missing_data_trying_next_provider")
                        continue
                    provider_errors.append("hybrid: empty_response")
                except httpx.ReadTimeout:
                    provider_errors.append(f"hybrid: timeout after {self.timeout_s:.0f}s")
                except Exception as exc:
                    provider_errors.append(f"hybrid: {exc}")
                continue

            if provider in {"vertex", "vertexai", "vertex_ai_search"}:
                if not self.vertex_search_enabled:
                    provider_errors.append("vertex: disabled")
                    continue
                if not self.vertex_project_id or not self.vertex_data_store:
                    provider_errors.append("vertex: GCP project or Vertex AI Search datastore missing")
                    continue
                called = True
                try:
                    parsed = self._call_vertex_ai_search(
                        images=images,
                        brand_name=brand_name,
                        category=category,
                        item_size=item_size,
                        condition_grade=condition_grade,
                        condition_source=condition_source,
                        item_description=item_description,
                    )
                    if parsed is not None:
                        parsed.setdefault("_provider", "vertex")
                        if self._has_usable_pricing(parsed) and self._has_strong_pricing_evidence(parsed):
                            self._profile_cache[cache_key] = dict(parsed)
                            return GptItemProfileResult(profile=parsed, enabled=True, called=True)
                        best_partial_profile = parsed
                        best_partial_provider = "vertex"
                        provider_errors.append("vertex: weak_or_missing_pricing_trying_next_provider")
                        continue
                    provider_errors.append("vertex: empty_response")
                except httpx.ReadTimeout:
                    provider_errors.append(f"vertex: timeout after {self.timeout_s:.0f}s")
                except Exception as exc:
                    provider_errors.append(f"vertex: {exc}")
                continue

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
                        if self._has_usable_pricing(parsed) and self._has_strong_pricing_evidence(parsed):
                            self._profile_cache[cache_key] = dict(parsed)
                            return GptItemProfileResult(profile=parsed, enabled=True, called=True)
                        if self._has_usable_pricing(parsed):
                            best_partial_profile = parsed
                            best_partial_provider = "gemini"
                            provider_errors.append("gemini: weak_pricing_evidence_trying_openai")
                            continue
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
                            self._profile_cache[cache_key] = dict(parsed)
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

    @staticmethod
    def _has_strong_pricing_evidence(profile: dict[str, Any]) -> bool:
        resale = profile.get("resale_price_estimate")
        breakdown = profile.get("resale_price_breakdown")
        if not isinstance(resale, dict):
            return False

        est = resale.get("estimated_price")
        if not isinstance(est, (int, float)) or float(est) <= 0:
            return False

        refs = resale.get("references")
        trusted_refs = 0
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                src = str(ref.get("source") or "").casefold()
                url = str(ref.get("url") or "").casefold()
                if any(
                    d in src or d in url
                    for d in GptItemProfiler.TRUSTED_PRICING_DOMAINS
                ):
                    trusted_refs += 1

        priced_rows = []
        rows_with_range = 0
        if isinstance(breakdown, list):
            for row in breakdown:
                if not isinstance(row, dict):
                    continue
                row_est = row.get("estimated_price")
                low = row.get("range_low")
                high = row.get("range_high")
                if isinstance(row_est, (int, float)) and float(row_est) > 0:
                    priced_rows.append(row)
                if isinstance(low, (int, float)) and isinstance(high, (int, float)) and float(high) >= float(low):
                    rows_with_range += 1

        # Strong enough evidence if we have multiple condition rows or explicit ranges,
        # or at least two trusted references for a single-price estimate.
        if len(priced_rows) >= 2 or rows_with_range >= 1:
            return True
        return trusted_refs >= 2

    def _cache_key(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
    ) -> str:
        h = hashlib.sha256()
        h.update((brand_name or "").strip().casefold().encode("utf-8"))
        h.update(b"|")
        h.update((category or "").strip().casefold().encode("utf-8"))
        h.update(b"|")
        h.update((item_size or "").strip().casefold().encode("utf-8"))
        h.update(b"|")
        h.update((condition_grade or "").strip().casefold().encode("utf-8"))
        h.update(b"|")
        h.update((condition_source or "").strip().casefold().encode("utf-8"))
        h.update(b"|")
        h.update((item_description or "").strip().casefold().encode("utf-8"))
        for img in images[: self.max_images]:
            h.update(b"|img|")
            h.update((img.content_type or "").encode("utf-8"))
            h.update(b"|")
            h.update(img.bytes_data)
        return h.hexdigest()

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
                    "First inspect every uploaded image for readable brand labels, care tags, size tags, hang tags, "
                    "logos, embossed marks, sole stamps, hardware engravings, dust bags, boxes, receipts, or other text. "
                    "Extract exact visible label/OCR text and identify which image contains it. Treat readable brand-label "
                    "text as primary brand evidence before doing any style-based or web-search identification. "
                    "Then identify the specific brand and model of this item by searching Google."
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
                    "Inspect every image for visible condition and accessory signals. Populate visual_condition_assessment "
                    "from visible evidence plus the provided user condition, and keep those two concepts separate in the rationale. "
                    "Look specifically for original tags attached, box, dust bag, authenticity card, receipt, branded packaging, "
                    "sole wear, scuffs, stains, fading, pilling, creasing, scratches, hardware wear, structure/shape loss, and "
                    "whether the item appears unworn, pristine, lightly used, or visibly worn. For NewWithTags, identify visible "
                    "tag evidence when present. For New or LikeNew, explain whether the photos support or contradict that condition. "
                    "Do not return unclear for wear_level, pricing_tier, or evidence when the photos contain visible condition "
                    "or accessory evidence. Use unclear only when the image quality or crop truly prevents assessment."
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

    def _build_label_ocr_content(self, *, images: list[ImageInput]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for idx, img in enumerate(images[: self.max_images], start=1):
            media_type, image_bytes = self._prepare_image_for_llm(img.content_type or "image/jpeg", img.bytes_data)
            b64 = base64.b64encode(image_bytes).decode("ascii")
            image_id = img.image_id or f"image-{idx}"
            content.append(
                {
                    "type": "input_text",
                    "text": (
                        f"Image {idx} id={image_id} filename={img.filename or ''}. "
                        "Inspect this image for label or logo text."
                    ),
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{b64}",
                    "detail": self.image_detail,
                }
            )
        return content

    def _build_gemini_label_ocr_payload(self, *, content: list[dict[str, Any]]) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Label/OCR pre-step. Inspect every image only for readable text on the item or its accessories: "
                    "brand labels, care tags, size tags, hang tags, logos, embossed marks, sole stamps, hardware "
                    "engravings, dust bags, boxes, receipts, or packaging. Do not identify style, do not estimate value, "
                    "and do not use web search. Rotate images mentally when label text is sideways or upside down, "
                    "and zoom into close-up tag photos before deciding text is unreadable. Return ONLY one JSON object, "
                    "not an array, with keys exactly: "
                    "brand_text, confidence, evidence_image_id, raw_visible_text, rationale. "
                    "Use brand_text null when no readable brand is visible. Do not infer a brand from style, color, "
                    "or partially readable text. Return a brand only when readable text directly supports it."
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

    def _build_openai_label_ocr_payload(self, *, content: list[dict[str, Any]]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "brand_text": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence_image_id": {"type": ["string", "null"]},
                "raw_visible_text": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["brand_text", "confidence", "evidence_image_id", "raw_visible_text", "rationale"],
        }
        return {
            "model": self.openai_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        *content,
                        {
                            "type": "input_text",
                            "text": (
                                "Label/OCR fallback. Inspect the attached images only for readable brand text, labels, "
                                "size tags, care tags, logos, stamps, hang tags, or packaging text. Rotate sideways or "
                                "upside-down labels mentally and zoom into close-up tag photos. Return only JSON. "
                                "Do not infer a brand from style, color, or partially readable text. Return a brand "
                                "only when readable text directly supports it."
                            ),
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "label_ocr_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        }

    @staticmethod
    def _brand_from_label_ocr(label_ocr: dict[str, Any] | None) -> str | None:
        if not isinstance(label_ocr, dict):
            return None
        confidence = label_ocr.get("confidence")
        if not isinstance(confidence, (int, float)) or float(confidence) < 0.65:
            return None
        brand = str(label_ocr.get("brand_text") or "").strip()
        if not brand or brand.lower() in {"unknown", "unclear", "null", "none"}:
            return None
        return brand

    @staticmethod
    def _label_ocr_raw_text(label_ocr: dict[str, Any] | None) -> str:
        if not isinstance(label_ocr, dict):
            return ""
        raw = label_ocr.get("raw_visible_text")
        if isinstance(raw, list):
            return " ".join(str(part or "") for part in raw).strip()
        if isinstance(raw, str):
            return raw.strip()
        return ""

    @classmethod
    def _label_ocr_selection_score(
        cls,
        label_ocr: dict[str, Any] | None,
        *,
        image: ImageInput | None = None,
        batch: bool = False,
    ) -> float:
        brand = cls._brand_from_label_ocr(label_ocr)
        if not brand:
            return -1.0
        try:
            confidence = float(label_ocr.get("confidence"))  # type: ignore[union-attr]
        except Exception:
            confidence = 0.0

        score = confidence
        raw_text = cls._label_ocr_raw_text(label_ocr)
        if raw_text:
            score += 0.08
            if brand.casefold() in raw_text.casefold():
                score += 0.12
        if image is not None:
            evidence_id = str(label_ocr.get("evidence_image_id") or "").strip()  # type: ignore[union-attr]
            if evidence_id and evidence_id == image.image_id:
                score += 0.08
            role_hint = str(image.role_hint or "").casefold()
            filename = str(image.filename or "").casefold()
            if role_hint in {"close_up", "tag", "label", "logo"}:
                score += 0.08
            if any(token in filename for token in ("tag", "label", "logo", "receipt", "auth")):
                score += 0.04
        if batch:
            score -= 0.12
        return score

    def _content_with_label_context(
        self,
        content: list[dict[str, Any]],
        *,
        label_ocr: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        detected_brand = self._brand_from_label_ocr(label_ocr)
        if not detected_brand:
            return content
        return [
            *content[:1],
            {
                "type": "input_text",
                "text": (
                    f"Known visible label brand from OCR pre-step: {detected_brand}. "
                    "Treat this as primary brand evidence unless the label is clearly unrelated to the item. "
                    f"Label OCR evidence: {json.dumps(label_ocr, ensure_ascii=True)}"
                ),
            },
            *content[1:],
        ]

    def _call_gemini_label_ocr(self, *, images: list[ImageInput]) -> dict[str, Any] | None:
        if not images:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"

        def call_once(client: httpx.Client, candidate_images: list[ImageInput]) -> dict[str, Any] | None:
            content = self._build_label_ocr_content(images=candidate_images)
            resp = client.post(
                url,
                params={"key": self.gemini_api_key},
                headers={"Content-Type": "application/json"},
                json=self._build_gemini_label_ocr_payload(content=content),
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"gemini_label_ocr_http_{resp.status_code}: {resp.text[:600]}")
            raw = resp.json()
            text = self._extract_gemini_text(raw)
            if not text:
                return None
            parsed = self._parse_json_relaxed(text)
            if not isinstance(parsed, dict):
                return None
            if not parsed.get("evidence_image_id") and len(candidate_images) == 1:
                parsed["evidence_image_id"] = candidate_images[0].image_id
            return parsed

        with httpx.Client(timeout=self.timeout_s) as client:
            batch_result = call_once(client, images)
            candidates: list[tuple[float, dict[str, Any]]] = []
            for img in images[: self.max_images]:
                single = call_once(client, [img])
                if isinstance(single, dict):
                    score = self._label_ocr_selection_score(single, image=img)
                    if score >= 0:
                        candidates.append((score, single))
            if candidates:
                best = max(candidates, key=lambda item: item[0])[1]
                if isinstance(batch_result, dict):
                    best["_batch_ocr_result"] = batch_result
                return best
            if self._brand_from_label_ocr(batch_result):
                return batch_result
            return batch_result

    def _call_openai_label_ocr(self, *, images: list[ImageInput]) -> dict[str, Any] | None:
        if not images or not self.openai_api_key:
            return None
        content = self._build_label_ocr_content(images=images)
        payload = self._build_openai_label_ocr_payload(content=content)
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
                raise RuntimeError(f"openai_label_ocr_http_{resp.status_code}: {resp.text[:600]}")
            raw = resp.json()
        text = self._extract_output_text(raw)
        if not text:
            return None
        parsed = self._parse_json_relaxed(text)
        if not isinstance(parsed, dict):
            return None
        if self._brand_from_label_ocr(parsed):
            parsed["_provider"] = "openai"
        return parsed

    def _call_label_ocr(self, *, images: list[ImageInput]) -> dict[str, Any] | None:
        label_ocr = self._call_gemini_label_ocr(images=images)
        if self._brand_from_label_ocr(label_ocr):
            if isinstance(label_ocr, dict):
                label_ocr.setdefault("_provider", "gemini")
            return label_ocr
        try:
            openai_label_ocr = self._call_openai_label_ocr(images=images)
        except Exception as exc:
            if isinstance(label_ocr, dict):
                label_ocr["_fallback_error"] = f"openai_label_ocr: {exc}"
            return label_ocr
        if self._brand_from_label_ocr(openai_label_ocr):
            return openai_label_ocr
        return label_ocr

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
                "visual_condition_assessment": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "wear_level": {
                            "type": "string",
                            "enum": ["pristine", "minimal", "visible", "heavy", "unclear"],
                        },
                        "box_included": {"type": "string", "enum": ["yes", "no", "unclear"]},
                        "dust_bag_included": {"type": "string", "enum": ["yes", "no", "unclear"]},
                        "new_in_box_signal": {"type": "string", "enum": ["yes", "no", "unclear"]},
                        "pricing_tier": {
                            "type": "string",
                            "enum": ["new_in_box", "pristine", "excellent", "pre_owned", "worn", "unclear"],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "wear_level",
                        "box_included",
                        "dust_bag_included",
                        "new_in_box_signal",
                        "pricing_tier",
                        "confidence",
                        "evidence",
                    ],
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
                "shipping_profile": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "item_type": {"type": "string"},
                        "weight_class": {
                            "type": "string",
                            "enum": ["light", "medium", "heavy", "oversize", "unclear"],
                        },
                        "estimated_weight_oz": {"type": ["number", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                    },
                    "required": ["item_type", "weight_class", "estimated_weight_oz", "confidence", "rationale"],
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
                "visual_condition_assessment",
                "retail_price_estimate",
                "resale_price_estimate",
                "resale_price_breakdown",
                "receipt_present",
                "expected_auth_docs",
                "shipping_profile",
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

    def _build_valuation_schema(self) -> dict[str, Any]:
        full = self._build_schema()
        props = full["properties"]
        required = [
            "grounding_sources",
            "retail_price_estimate",
            "resale_price_estimate",
            "resale_price_breakdown",
            "expected_auth_docs",
            "shipping_profile",
        ]
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {key: props[key] for key in required},
            "required": required,
        }

    def _build_openai_valuation_payload(
        self,
        *,
        content: list[dict[str, Any]],
        gemini_profile: dict[str, Any],
        condition_grade: str | None = None,
        valuation_prompt_override: str | None = None,
    ) -> dict[str, Any]:
        valuation_schema = self._build_valuation_schema()
        valuation_context = {
            "user_condition": condition_grade,
            "category": gemini_profile.get("category"),
            "candidate_brand": gemini_profile.get("candidate_brand"),
            "candidate_model": gemini_profile.get("candidate_model"),
            "model_identification": gemini_profile.get("model_identification"),
            "visual_signatures": gemini_profile.get("visual_signatures"),
            "visual_condition_assessment": gemini_profile.get("visual_condition_assessment"),
        }
        text_context = [part for part in content if part.get("type") == "input_text"]
        default_prompt = (
            "### IDENTITY & SOURCES\n"
            "1. ITEM IDENTITY: Treat the provided Gemini identification (Brand, Model, Material, Season) as fixed ground truth. "
            "Do not reclassify brand or model unless hard visual or text evidence proves Gemini's identification is strictly impossible.\n"
            "2. RESALE SOURCES (Primary): Priority order for comp gathering:\n"
            "   - Luxury Handbags/Jewelry/Apparel: Fashionphile, Rebag, The RealReal, Vestiaire Collective.\n"
            "   - General Peer-to-Peer Resale: eBay (Sold listings ONLY), Poshmark, Depop, Vinted.\n\n"
            "3. MSRP / RETAIL SEARCH WATERFALL LOGIC:\n"
            "   - Tier 1 (Ultra-Luxury & Runway): Primary reference is Bergdorf Goodman or Neiman Marcus.\n"
            "   - Tier 2 (Contemporary & Premium Mall): Fall back to Saks Fifth Avenue, Net-A-Porter, Nordstrom, "
            "or the Brand Direct Webstore (e.g., Reformation.com, Theory.com).\n"
            "   - Tier 3 (Vintage / Archived Items): If current MSRP is not listed on active retail sites, retrieve "
            "historical MSRP from press records, catalog archives, or vintage listing documentation.\n"
            "   - Core MSRP Rule: ALWAYS use full, un-discounted original retail sticker price. NEVER use markdown, "
            "clearance, or outlet sale prices as the MSRP baseline.\n\n"
            "### VALUATION MODELING\n"
            "4. TRADE CONTEXT: Value for patient peer-to-peer luxury trade (target market clearing price within 30-60 days), "
            "NOT fast liquidation or wholesale trade-in values.\n"
            "5. SIZE & SEASON EXCLUSION: Size and season may be included as descriptive context only. "
            "Do not increase, decrease, discount, premium, or otherwise adjust valuation because of size, season, "
            "current-season status, off-season status, archive status, or common/outlier sizing.\n"
            "6. USER CONDITION IS AUTHORITATIVE: The user-selected condition is provided as user_condition. "
            "Use that exact condition for the final resale_price_estimate. Do not override it based on visible tags, packaging, "
            "box, dust bag, or inferred accessory cues. If user_condition is New, do NOT value the item as NewWithTags, NWT, "
            "new-in-box/NIB, full set, with tags, or with a box/dust-bag/full-set premium. Only apply NewWithTags/NWT/NIB/"
            "full-set premiums when user_condition is exactly NewWithTags. The condition-tier table may include NWT as a "
            "separate row, but resale_price_estimate must not use that row unless user_condition is NewWithTags.\n"
            "7. CONDITION & ACCESSORY MATRIX: Adjust base valuation for:\n"
            "   - Condition & visible wear (fading, pilling, structural shape, hardware scratching).\n"
            "   - Provenance & Accessories (Original tags, dust bag, box, authenticity cards, box/NIB signals add 5-15% premium).\n"
            "8. CONTEMPORARY VS. LUXURY DISCOUNT RULES:\n"
            "   - Contemporary Apparel (New With Tags):\n"
            "     - Use 45%-60% of MSRP unless sold comps explicitly prove lower. Do not change this range based on season.\n"
            "   - Luxury / Heritage Brands (Chanel, Hermes, Louis Vuitton, Rolex):\n"
            "     - Do NOT hard-cap at 60% MSRP. Anchor strictly to real-time secondary sold comps (may trade above or near MSRP).\n\n"
            "### OUTPUT DELIVERABLES\n"
            "9. CONDITION-TIER TABLE: Always provide a full multi-tier valuation table (NWT, EUC/Like New, GUC/Good, Fair) "
            "to establish a full market curve whenever comp evidence allows.\n"
            "10. LOGISTICS: Include an estimated packed shipping weight (e.g., 1.2 lbs / 0.55 kg) and box type recommendations.\n\n"
            "Return only the valuation JSON fields required by the schema."
        )
        valuation_prompt = (valuation_prompt_override or default_prompt).strip()
        valuation_content = [
            *text_context,
            {
                "type": "input_text",
                "text": (
                    f"{valuation_prompt}\n\n"
                    f"Gemini identification and condition:\n{json.dumps(valuation_context, ensure_ascii=True)}"
                ),
            },
        ]
        payload: dict[str, Any] = {
            "model": self.openai_model,
            "input": [{"role": "user", "content": valuation_content}],
            "tools": [{"type": "web_search_preview"}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "item_valuation_result",
                    "strict": True,
                    "schema": valuation_schema,
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
                    "1a) Derive visual condition and completeness from the photos: pristine/unworn cues, visible wear, "
                    "whether an original branded box is shown, whether dust bags or accessories are shown, and whether "
                    "the item should be priced as new-in-box/pristine versus ordinary pre-owned.\n"
                    "2) Use Google grounding and prioritize: Rebag, Poshmark, The RealReal, Vestiaire Collective, "
                    "1stdibs, Fashionphile. Use Bergdorf Goodman for retail/MSRP context. De-prioritize eBay unless needed.\n"
                    "3) Compute resale pricing specifically for the identified category/model and current item condition.\n"
                    "4) Provide a resale breakdown including median and range by condition when available.\n"
                    "5) Estimate packaged shipping weight from the item type and visible bulk.\n"
                    "6) Return ONLY JSON. No prose.\n\n"
                    "JSON keys required:\n"
                    "category, candidate_brand, candidate_model, confidence, visual_signatures, grounding_sources, "
                    "dupe_risk_assessment, why_not_fast_fashion, model_identification, authenticity_screen, visual_condition_assessment, "
                    "retail_price_estimate, resale_price_estimate, resale_price_breakdown, receipt_present, expected_auth_docs, shipping_profile.\n"
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
                    "Before any generic style search, inspect all uploaded images for readable label/OCR evidence: "
                    "brand labels, care tags, size tags, hang tags, logos, embossed marks, sole stamps, hardware engravings, "
                    "dust bags, boxes, receipts, or other text. Extract exact text, name the image/evidence type, and treat "
                    "readable brand-label text as primary brand evidence. Do not infer label text from style, color, or "
                    "partially readable marks. If readable label text clearly names a brand, candidate_brand must use that "
                    "exact label brand unless the label is clearly not part of the item. "
                    "Identify the exact category, brand, and model from the images. "
                    "Derive visual condition and completeness from the image: pristine/unworn cues, visible wear, "
                    "original branded box, dust bags, and whether the item should be valued as new-in-box/pristine. "
                    "Use Google grounding and ONLY use these websites, in this strict priority order:\n"
                    "Tier 1: 1) The RealReal, 2) Vestiaire Collective, 3) Fashionphile, 4) Rebag.\n"
                    "Tier 2: 5) Bergdorf Goodman for retail/MSRP context, 6) eBay, 7) Poshmark.\n"
                    "Tier 3: 8) Depop, 9) Vinted.\n"
                    "Search using explicit domain-limited queries such as: "
                    "site:therealreal.com OR site:vestiairecollective.com OR site:fashionphile.com OR site:rebag.com OR "
                    "site:bergdorfgoodman.com OR site:ebay.com OR site:poshmark.com OR site:depop.com OR site:vinted.com.\n"
                    "Prefer higher tiers first; only use lower tiers when higher-tier evidence is insufficient.\n"
                    "Collect pricing evidence relevant to the identified model and current condition, including "
                    "median-like central value and condition-based ranges when available.\n"
                    "Also infer the specific shipping item type and realistic packaged weight from the photos "
                    "(examples: dress, blouse, jeans, blazer, coat, heels, boots, handbag).\n"
                    "Return concise evidence text with sources and numeric price mentions."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 1.0},
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
                    "dupe_risk_assessment, why_not_fast_fashion, model_identification, authenticity_screen, visual_condition_assessment, "
                    "retail_price_estimate, resale_price_estimate, resale_price_breakdown, receipt_present, expected_auth_docs, shipping_profile.\n"
                    "For visual_condition_assessment, copy condition and accessory evidence from the grounded evidence into "
                    "the structured fields. If grounded evidence says the item is pristine/unworn, has original tags, "
                    "has a box, has a dust bag, has pristine soles, or shows no visible wear, do not return unclear for "
                    "wear_level, box_included, dust_bag_included, new_in_box_signal, pricing_tier, confidence, or evidence. "
                    "Use evidence as short bullet-like strings such as 'original tag attached', 'original branded box visible', "
                    "'pristine soles', or 'no visible wear'. Keep user-provided condition separate from visual evidence in the rationale. "
                    "For shipping_profile, estimate packaged shipping weight in ounces from item_type and visible bulk. "
                    "Use numeric values for estimated_price/ranges whenever possible. No markdown, no prose."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }

    def _build_vertex_ai_search_payload(self, *, content: list[dict[str, Any]]) -> dict[str, Any]:
        gemini_parts = self._build_gemini_parts(content=content)
        gemini_parts.append(
            {
                "text": (
                    "Step 1/2 - Vertex AI Search Evidence Collection.\n"
                    "Identify the exact category, brand, and model from the images. "
                    "Derive visual condition and completeness from the photos: pristine/unworn cues, visible wear, "
                    "original branded box, dust bags, and whether the item should be valued as new-in-box/pristine. "
                    "Use only evidence retrieved from the configured Vertex AI Search datastore. "
                    "Collect pricing evidence relevant to the identified model and current item condition, including "
                    "median-like central value and condition-based ranges when available. "
                    "Also infer the specific shipping item type and realistic packaged weight from the photos. "
                    "Return concise evidence text with source titles, URLs when present, and numeric price mentions."
                )
            }
        )
        return {
            "contents": [{"role": "user", "parts": gemini_parts}],
            "tools": [
                {
                    "retrieval": {
                        "vertexAiSearch": {
                            "datastore": self.vertex_data_store,
                            "maxResults": self.vertex_max_results,
                        }
                    }
                }
            ],
            "generationConfig": {"temperature": 1.0},
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
                    "dupe_risk_assessment, why_not_fast_fashion, model_identification, authenticity_screen, visual_condition_assessment, "
                    "retail_price_estimate, resale_price_estimate, resale_price_breakdown, receipt_present, expected_auth_docs, shipping_profile. "
                    "For shipping_profile, estimate packaged shipping weight in ounces from item_type and visible bulk. "
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

    def _call_openai_valuation(
        self,
        *,
        content: list[dict[str, Any]],
        gemini_profile: dict[str, Any],
        condition_grade: str | None = None,
        valuation_prompt_override: str | None = None,
    ) -> dict[str, Any] | None:
        payload = self._build_openai_valuation_payload(
            content=content,
            gemini_profile=gemini_profile,
            condition_grade=condition_grade,
            valuation_prompt_override=valuation_prompt_override,
        )
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
        text = self._extract_output_text(raw)
        if not text:
            return None
        data = self._parse_json_relaxed(text)
        return data if isinstance(data, dict) else None

    def _merge_gemini_identification_with_openai_valuation(
        self,
        *,
        gemini_profile: dict[str, Any],
        openai_valuation: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(gemini_profile)
        if "grounding_sources" in openai_valuation:
            merged["grounding_sources"] = openai_valuation.get("grounding_sources")
        for key in (
            "retail_price_estimate",
            "resale_price_estimate",
            "resale_price_breakdown",
            "expected_auth_docs",
        ):
            if key in openai_valuation:
                merged[key] = openai_valuation.get(key)
        workflow = dict(merged.get("_workflow") or {})
        workflow["hybrid"] = {
            "identification_provider": "gemini",
            "valuation_provider": "openai",
        }
        workflow["openai_valuation"] = openai_valuation
        merged["_workflow"] = workflow
        merged["_provider"] = "hybrid"
        return self._normalize_profile_shape(merged)

    def _call_gemini_openai_hybrid(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
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
        gemini_profile = self._call_gemini(
            images=images,
            brand_name=brand_name,
            category=category,
            item_size=item_size,
            condition_grade=condition_grade,
            condition_source=condition_source,
            item_description=item_description,
            schema=self._build_schema(),
        )
        if not isinstance(gemini_profile, dict):
            return None
        openai_valuation = self._call_openai_valuation(
            content=content,
            gemini_profile=gemini_profile,
            condition_grade=condition_grade,
        )
        if not isinstance(openai_valuation, dict):
            workflow = dict(gemini_profile.get("_workflow") or {})
            workflow["hybrid"] = {
                "identification_provider": "gemini",
                "valuation_provider": "openai",
                "valuation_error": "empty_response",
            }
            gemini_profile["_workflow"] = workflow
            gemini_profile["_provider"] = "hybrid"
            return gemini_profile
        return self._merge_gemini_identification_with_openai_valuation(
            gemini_profile=gemini_profile,
            openai_valuation=openai_valuation,
        )

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
        label_ocr = self._call_label_ocr(images=images)
        if isinstance(label_ocr, dict):
            workflow["label_ocr"] = label_ocr
            content = self._content_with_label_context(content, label_ocr=label_ocr)
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
        if isinstance(label_ocr, dict):
            parsed_single["label_ocr"] = label_ocr
        parsed_single["_workflow"] = workflow
        return parsed_single

    def _vertex_generate_content_url(self) -> str:
        project = self.vertex_project_id or ""
        location = self.vertex_location or "global"
        model = self.vertex_model or self.gemini_model
        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        return (
            f"https://{host}/v1beta1/projects/{project}/locations/{location}/"
            f"publishers/google/models/{model}:generateContent"
        )

    def _vertex_bearer_token(self) -> str:
        explicit = self.vertex_access_token or ""
        if explicit.strip():
            return explicit.strip()
        try:
            import google.auth  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
        except Exception as exc:
            raise RuntimeError("vertex_access_token_missing_and_google_auth_unavailable") from exc
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(Request())
        token = getattr(credentials, "token", None)
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("vertex_access_token_unavailable")
        return token.strip()

    def _call_vertex_ai_search(
        self,
        *,
        images: list[ImageInput],
        brand_name: str,
        category: str,
        item_size: str | None,
        condition_grade: str,
        condition_source: str,
        item_description: str | None,
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
        url = self._vertex_generate_content_url()
        token = self._vertex_bearer_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        grounding_metadata: dict[str, Any] | None = None
        workflow: dict[str, Any] = {
            "vertex_ai_search": {
                "project_id": self.vertex_project_id,
                "location": self.vertex_location,
                "model": self.vertex_model,
                "data_store": self.vertex_data_store,
                "max_results": self.vertex_max_results,
            }
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            search_resp = client.post(
                url,
                headers=headers,
                json=self._build_vertex_ai_search_payload(content=content),
            )
            if search_resp.status_code >= 400:
                raise RuntimeError(f"vertex_http_{search_resp.status_code}: {search_resp.text[:600]}")
            search_raw = search_resp.json()
            grounding_metadata = self._extract_gemini_grounding_metadata(search_raw)
            grounded_text = self._extract_gemini_text(search_raw) or ""
            workflow["grounded_search"] = grounded_text

            format_resp = client.post(
                url,
                headers=headers,
                json=self._build_gemini_formatter_payload(content=content, grounded_text=grounded_text),
            )
            if format_resp.status_code >= 400:
                raise RuntimeError(f"vertex_http_{format_resp.status_code}: {format_resp.text[:600]}")
            format_raw = format_resp.json()
        parsed = self._parse_gemini_response(format_raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("vertex_two_step_parse_failed")
        if isinstance(grounding_metadata, dict):
            grounding_sources = self._grounding_sources_from_metadata(grounding_metadata)
            if grounding_sources:
                parsed["grounding_sources"] = grounding_sources
            parsed["_grounding_metadata"] = grounding_metadata
        parsed["_workflow"] = workflow
        return parsed

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
        normalized["visual_condition_assessment"] = self._normalize_visual_condition_assessment(
            normalized.get("visual_condition_assessment")
        )
        normalized["retail_price_estimate"] = self._normalize_price_estimate(normalized.get("retail_price_estimate"))
        normalized["resale_price_estimate"] = self._normalize_price_estimate(normalized.get("resale_price_estimate"))
        normalized["resale_price_breakdown"] = self._normalize_resale_price_breakdown(
            normalized.get("resale_price_breakdown"),
            fallback=normalized.get("resale_price_estimate"),
        )
        normalized["receipt_present"] = self._normalize_receipt_present(normalized.get("receipt_present"))
        normalized["expected_auth_docs"] = self._normalize_expected_auth_docs(normalized.get("expected_auth_docs"))
        normalized["shipping_profile"] = self._normalize_shipping_profile(
            normalized.get("shipping_profile"),
            category=normalized.get("category"),
            model_identification=normalized.get("model_identification"),
            visual_signatures=normalized.get("visual_signatures"),
        )
        return normalized

    def _normalize_visual_condition_assessment(self, value: Any) -> dict[str, Any]:
        data = value if isinstance(value, dict) else {}

        def enum_value(raw: Any, allowed: set[str], default: str) -> str:
            if isinstance(raw, str):
                normalized = raw.strip().casefold().replace("-", "_").replace(" ", "_")
                if normalized in allowed:
                    return normalized
            return default

        evidence = self._as_str_list(data.get("evidence"))
        evidence_text = " ".join(evidence).casefold()
        wear_level = enum_value(
            data.get("wear_level"),
            {"pristine", "minimal", "visible", "heavy", "unclear"},
            "unclear",
        )
        box_included = enum_value(data.get("box_included"), {"yes", "no", "unclear"}, "unclear")
        dust_bag_included = enum_value(data.get("dust_bag_included"), {"yes", "no", "unclear"}, "unclear")
        new_in_box_signal = enum_value(data.get("new_in_box_signal"), {"yes", "no", "unclear"}, "unclear")
        pricing_tier = enum_value(
            data.get("pricing_tier"),
            {"new_in_box", "pristine", "excellent", "pre_owned", "worn", "unclear"},
            "unclear",
        )
        confidence = self._normalize_confidence(data.get("confidence")) or 0.0

        if evidence:
            if wear_level == "unclear" and (
                "pristine" in evidence_text
                or "unworn" in evidence_text
                or "no visible wear" in evidence_text
                or "pristine soles" in evidence_text
            ):
                wear_level = "pristine"
            if box_included == "unclear" and ("box visible" in evidence_text or "branded box" in evidence_text):
                box_included = "yes"
            if new_in_box_signal == "unclear" and (
                "original tag" in evidence_text
                or "tag visible" in evidence_text
                or "sticker/tag" in evidence_text
                or "branded box" in evidence_text
            ):
                new_in_box_signal = "yes"
            if pricing_tier == "unclear":
                if new_in_box_signal == "yes" and wear_level == "pristine":
                    pricing_tier = "new_in_box"
                elif wear_level == "pristine":
                    pricing_tier = "pristine"
            if confidence == 0.0 and any(
                value != "unclear"
                for value in (wear_level, box_included, dust_bag_included, new_in_box_signal, pricing_tier)
            ):
                confidence = 0.65

        return {
            "wear_level": wear_level,
            "box_included": box_included,
            "dust_bag_included": dust_bag_included,
            "new_in_box_signal": new_in_box_signal,
            "pricing_tier": pricing_tier,
            "confidence": confidence,
            "evidence": evidence,
        }

    def _normalize_shipping_profile(
        self,
        value: Any,
        *,
        category: Any,
        model_identification: Any,
        visual_signatures: Any,
    ) -> dict[str, Any]:
        data = value if isinstance(value, dict) else {}
        item_type = self._as_nullable_str(data.get("item_type")) or self._infer_shipping_item_type(
            category=category,
            model_identification=model_identification,
            visual_signatures=visual_signatures,
        )
        weight = self._coerce_weight_oz(data.get("estimated_weight_oz"))
        inferred_weight = self._default_shipping_weight_oz(item_type=item_type, category=category)
        if weight is None:
            weight = inferred_weight
        weight_class = self._as_nullable_str(data.get("weight_class")) or self._shipping_weight_class(weight)
        normalized_class = weight_class.strip().casefold().replace("-", "_").replace(" ", "_") if weight_class else "unclear"
        if normalized_class not in {"light", "medium", "heavy", "oversize", "unclear"}:
            normalized_class = self._shipping_weight_class(weight)
        return {
            "item_type": item_type or "unknown",
            "weight_class": normalized_class,
            "estimated_weight_oz": weight,
            "confidence": self._normalize_confidence(data.get("confidence")) or (0.45 if inferred_weight is not None else 0.0),
            "rationale": self._as_nullable_str(data.get("rationale"))
            or f"Estimated packaged weight for {item_type or category or 'item'} based on category and visible item type.",
        }

    @staticmethod
    def _coerce_weight_oz(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            weight = float(value)
            return round(weight, 2) if 1 <= weight <= 240 else None
        if isinstance(value, str):
            text = value.strip().lower()
            match = re.search(r"(\d+(?:\.\d+)?)", text)
            if not match:
                return None
            amount = float(match.group(1))
            if "lb" in text or "pound" in text:
                amount *= 16
            return round(amount, 2) if 1 <= amount <= 240 else None
        return None

    def _infer_shipping_item_type(self, *, category: Any, model_identification: Any, visual_signatures: Any) -> str:
        text_parts: list[str] = [str(category or "")]
        if isinstance(model_identification, dict):
            text_parts.append(str(model_identification.get("name") or ""))
            attrs = model_identification.get("attributes")
            if isinstance(attrs, list):
                text_parts.extend(str(x) for x in attrs if isinstance(x, str))
        if isinstance(visual_signatures, list):
            text_parts.extend(str(x) for x in visual_signatures if isinstance(x, str))
        text = " ".join(text_parts).casefold()
        checks = [
            ("coat", ("coat", "parka", "overcoat", "trench")),
            ("jacket", ("jacket", "blazer", "bomber")),
            ("boots", ("boot", "boots")),
            ("handbag", ("handbag", "bag", "tote", "satchel", "purse")),
            ("jeans", ("jean", "denim", "pants", "trouser")),
            ("dress", ("dress", "gown")),
            ("skirt", ("skirt",)),
            ("sweater", ("sweater", "cardigan", "knit")),
            ("top", ("top", "blouse", "shirt", "tee", "tank")),
            ("heels", ("heel", "pump", "sandal", "mule")),
            ("sneakers", ("sneaker", "trainer")),
        ]
        for item_type, needles in checks:
            if any(needle in text for needle in needles):
                return item_type
        normalized_category = str(category or "").strip().casefold()
        if normalized_category == "shoes":
            return "shoes"
        if normalized_category == "clothes":
            return "clothes"
        return normalized_category or "unknown"

    @staticmethod
    def _default_shipping_weight_oz(*, item_type: Any, category: Any) -> float | None:
        text = f"{item_type or ''} {category or ''}".casefold()
        weights = [
            ("coat", 72.0),
            ("boots", 64.0),
            ("handbag", 48.0),
            ("jacket", 48.0),
            ("blazer", 40.0),
            ("jeans", 32.0),
            ("pants", 28.0),
            ("sweater", 24.0),
            ("dress", 20.0),
            ("skirt", 16.0),
            ("heels", 32.0),
            ("sandal", 24.0),
            ("sneaker", 40.0),
            ("shoes", 40.0),
            ("top", 12.0),
            ("blouse", 12.0),
            ("shirt", 12.0),
            ("clothes", 24.0),
        ]
        for needle, weight in weights:
            if needle in text:
                return weight
        return None

    @staticmethod
    def _shipping_weight_class(weight_oz: float | None) -> str:
        if weight_oz is None:
            return "unclear"
        if weight_oz <= 16:
            return "light"
        if weight_oz <= 48:
            return "medium"
        if weight_oz <= 80:
            return "heavy"
        return "oversize"

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
        def first_object(parsed: Any) -> dict[str, Any] | None:
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        return item
            return None

        txt = text.strip()
        try:
            parsed = json.loads(txt)
            return first_object(parsed)
        except Exception:
            pass

        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", txt, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            try:
                parsed = json.loads(fence.group(1))
                return first_object(parsed)
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
