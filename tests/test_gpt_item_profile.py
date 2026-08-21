import io

from PIL import Image

from brand.types import ImageInput
from app.gpt_item_profile import GptItemProfiler


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (16, 16), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _profiler(max_images: int) -> GptItemProfiler:
    return GptItemProfiler(
        enabled=True,
        provider_order="hybrid,gemini,openai",
        openai_api_key=None,
        openai_model="gpt-5",
        gemini_api_key="test",
        gemini_model="gemini-2.5-flash",
        timeout_s=25,
        max_images=max_images,
        image_detail="auto",
        reasoning_effort="low",
        vertex_search_enabled=False,
    )


def test_profiler_allows_up_to_six_images_in_provider_payload() -> None:
    images = [
        ImageInput(
            image_id=f"image-{idx}",
            filename=f"image-{idx}.jpg",
            content_type="image/jpeg",
            bytes_data=_jpeg_bytes(),
        )
        for idx in range(6)
    ]

    content = _profiler(max_images=6)._build_content(
        images=images,
        brand_name="Chanel",
        category="handbag",
        item_size="Medium",
        condition_grade="New",
        condition_source="user",
        item_description=None,
    )

    assert sum(1 for part in content if part["type"] == "input_image") == 6


def test_profiler_still_caps_provider_payload_at_six_images() -> None:
    images = [
        ImageInput(
            image_id=f"image-{idx}",
            filename=f"image-{idx}.jpg",
            content_type="image/jpeg",
            bytes_data=_jpeg_bytes(),
        )
        for idx in range(8)
    ]

    content = _profiler(max_images=8)._build_content(
        images=images,
        brand_name="Chanel",
        category="handbag",
        item_size="Medium",
        condition_grade="New",
        condition_source="user",
        item_description=None,
    )

    assert sum(1 for part in content if part["type"] == "input_image") == 6


def test_gemini_content_requests_condition_and_accessory_assessment() -> None:
    content = _profiler(max_images=6)._build_content(
        images=[],
        brand_name="Chanel",
        category="shoes",
        item_size="US 8",
        condition_grade="NewWithTags",
        condition_source="user",
        item_description=None,
    )
    prompt_text = "\n".join(part["text"] for part in content if part["type"] == "input_text")

    assert "Inspect every image for visible condition and accessory signals" in prompt_text
    assert "original tags attached" in prompt_text
    assert "box, dust bag, authenticity card" in prompt_text
    assert "Do not return unclear for wear_level" in prompt_text


def test_gemini_content_prioritizes_visible_label_ocr() -> None:
    content = _profiler(max_images=6)._build_content(
        images=[],
        brand_name="unknown",
        category="clothes",
        item_size="S",
        condition_grade="New",
        condition_source="user",
        item_description=None,
    )
    prompt_text = "\n".join(part["text"] for part in content if part["type"] == "input_text")

    assert "readable brand labels" in prompt_text
    assert "Extract exact visible label/OCR text" in prompt_text
    assert "primary brand evidence" in prompt_text


def test_gemini_label_ocr_payload_is_narrow_and_structured() -> None:
    payload = _profiler(max_images=6)._build_gemini_label_ocr_payload(
        content=[{"type": "input_text", "text": "unused"}]
    )
    prompt = payload["contents"][0]["parts"][-1]["text"]

    assert "Label/OCR pre-step" in prompt
    assert "Do not identify style" in prompt
    assert "do not estimate value" in prompt
    assert "Rotate images mentally" in prompt
    assert "not an array" in prompt
    assert "brand_text, confidence, evidence_image_id, raw_visible_text, rationale" in prompt
    assert "ALEXIS" in prompt
    assert "L'Academie" in prompt
    assert "tools" not in payload
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["temperature"] == 0.0


def test_parse_json_relaxed_accepts_single_object_array() -> None:
    parsed = _profiler(max_images=6)._parse_json_relaxed(
        """[{"brand_text":"L'Academie","confidence":0.9,"raw_visible_text":["L'Academie"]}]"""
    )

    assert parsed == {
        "brand_text": "L'Academie",
        "confidence": 0.9,
        "raw_visible_text": ["L'Academie"],
    }


def test_label_ocr_brand_context_is_injected_when_confident() -> None:
    profiler = _profiler(max_images=6)
    content = [{"type": "input_text", "text": "Role prompt"}]
    enriched = profiler._content_with_label_context(
        content,
        label_ocr={
            "brand_text": "ALEXIS",
            "confidence": 0.92,
            "evidence_image_id": "image-2",
            "raw_visible_text": ["ALEXIS", "S"],
            "rationale": "brand tag visible",
        },
    )

    prompt_text = "\n".join(part["text"] for part in enriched if part["type"] == "input_text")
    assert "Known visible label brand from OCR pre-step: ALEXIS" in prompt_text
    assert "primary brand evidence" in prompt_text


def test_label_ocr_brand_context_ignores_low_confidence() -> None:
    profiler = _profiler(max_images=6)
    content = [{"type": "input_text", "text": "Role prompt"}]
    enriched = profiler._content_with_label_context(
        content,
        label_ocr={"brand_text": "ALEXIS", "confidence": 0.4, "raw_visible_text": ["ALEXIS"]},
    )

    assert enriched == content


def test_openai_label_ocr_payload_is_structured() -> None:
    payload = _profiler(max_images=6)._build_openai_label_ocr_payload(
        content=[{"type": "input_text", "text": "Image 1 id=image-1"}]
    )
    prompt = payload["input"][0]["content"][-1]["text"]
    schema = payload["text"]["format"]["schema"]

    assert payload["text"]["format"]["name"] == "label_ocr_result"
    assert schema["required"] == ["brand_text", "confidence", "evidence_image_id", "raw_visible_text", "rationale"]
    assert "Label/OCR fallback" in prompt
    assert "L'Academie" in prompt
    assert "ALEXIS" in prompt


def test_label_ocr_uses_openai_fallback_when_gemini_misses_brand() -> None:
    profiler = _profiler(max_images=6)
    profiler.openai_api_key = "test-openai"
    profiler._call_gemini_label_ocr = lambda images: {"brand_text": None, "confidence": 1.0}  # type: ignore[method-assign]
    profiler._call_openai_label_ocr = lambda images: {  # type: ignore[method-assign]
        "brand_text": "L'Academie",
        "confidence": 0.92,
        "evidence_image_id": "image-3",
        "raw_visible_text": ["L'Academie"],
        "rationale": "brand tag visible",
        "_provider": "openai",
    }

    parsed = profiler._call_label_ocr(images=[])

    assert parsed is not None
    assert parsed["brand_text"] == "L'Academie"
    assert parsed["_provider"] == "openai"


def test_label_ocr_keeps_gemini_result_when_openai_fallback_errors() -> None:
    profiler = _profiler(max_images=6)
    profiler.openai_api_key = "test-openai"
    profiler._call_gemini_label_ocr = lambda images: {"brand_text": None, "confidence": 1.0}  # type: ignore[method-assign]

    def raise_quota(images):
        raise RuntimeError("openai_label_ocr_http_429: credit_balance_exhausted")

    profiler._call_openai_label_ocr = raise_quota  # type: ignore[method-assign]

    parsed = profiler._call_label_ocr(images=[])

    assert parsed is not None
    assert parsed["brand_text"] is None
    assert "credit_balance_exhausted" in parsed["_fallback_error"]


def test_gemini_grounded_search_prompt_uses_site_queries() -> None:
    payload = _profiler(max_images=6)._build_gemini_grounded_search_payload(
        content=[{"type": "input_text", "text": "Analyze this item."}]
    )
    prompt = payload["contents"][0]["parts"][-1]["text"]

    assert payload["tools"] == [{"google_search": {}}]
    assert payload["generationConfig"]["temperature"] == 1.0
    assert "site:therealreal.com" in prompt
    assert "site:vestiairecollective.com" in prompt
    assert "site:fashionphile.com" in prompt
    assert "site:rebag.com" in prompt
    assert "site:bergdorfgoodman.com" in prompt
    assert "bergdorfgoodman.com" in GptItemProfiler.TRUSTED_PRICING_DOMAINS


def test_gemini_grounded_search_prompt_prioritizes_label_before_style_search() -> None:
    payload = _profiler(max_images=6)._build_gemini_grounded_search_payload(
        content=[{"type": "input_text", "text": "Analyze this item."}]
    )
    prompt = payload["contents"][0]["parts"][-1]["text"]

    assert "Before any generic style search" in prompt
    assert "readable label/OCR evidence" in prompt
    assert "candidate_brand must use that label" in prompt
    assert "ALEXIS" in prompt


def test_gemini_formatter_prompt_preserves_condition_evidence() -> None:
    payload = _profiler(max_images=6)._build_gemini_formatter_payload(
        content=[{"type": "input_text", "text": "Analyze this item."}],
        grounded_text=(
            "The item appears pristine and unworn. Original tags are attached, "
            "the original branded box is visible, and the soles show no wear."
        ),
    )
    prompt = payload["contents"][0]["parts"][-1]["text"]

    assert "copy condition and accessory evidence" in prompt
    assert "do not return unclear" in prompt
    assert "original tag attached" in prompt
    assert "original branded box visible" in prompt


def test_vertex_ai_search_payload_uses_configured_datastore() -> None:
    profiler = GptItemProfiler(
        enabled=True,
        provider_order="vertex,gemini,openai",
        openai_api_key=None,
        openai_model="gpt-5",
        gemini_api_key="test",
        gemini_model="gemini-2.5-flash",
        timeout_s=25,
        max_images=6,
        image_detail="auto",
        reasoning_effort="low",
        vertex_search_enabled=True,
        vertex_project_id="jouft-analysis",
        vertex_location="global",
        vertex_model="gemini-2.5-flash",
        vertex_data_store=(
            "projects/jouft-analysis/locations/global/collections/default_collection/"
            "dataStores/luxury-resale-sites"
        ),
        vertex_access_token="test-token",
        vertex_max_results=7,
    )

    payload = profiler._build_vertex_ai_search_payload(
        content=[{"type": "input_text", "text": "Analyze this item."}]
    )
    vertex_search = payload["tools"][0]["retrieval"]["vertexAiSearch"]

    assert vertex_search["datastore"].endswith("/dataStores/luxury-resale-sites")
    assert vertex_search["maxResults"] == 7
    assert "Use only evidence retrieved from the configured Vertex AI Search datastore" in payload["contents"][0]["parts"][-1]["text"]
    assert payload["generationConfig"]["temperature"] == 1.0


def test_vertex_provider_is_skipped_when_not_configured() -> None:
    profiler = GptItemProfiler(
        enabled=True,
        provider_order="vertex",
        openai_api_key=None,
        openai_model="gpt-5",
        gemini_api_key=None,
        gemini_model="gemini-2.5-flash",
        timeout_s=25,
        max_images=6,
        image_detail="auto",
        reasoning_effort="low",
        vertex_search_enabled=False,
    )

    result = profiler.profile_item(
        images=[],
        brand_name="",
        category="",
        item_size=None,
        condition_grade="New",
        condition_source="user",
        item_description=None,
    )

    assert result.enabled is True
    assert result.called is False
    assert result.profile is None
    assert "vertex: disabled" in (result.error or "")


def test_hybrid_provider_uses_gemini_identity_and_openai_valuation(monkeypatch) -> None:
    profiler = GptItemProfiler(
        enabled=True,
        provider_order="hybrid",
        openai_api_key="openai-test",
        openai_model="gpt-5",
        gemini_api_key="gemini-test",
        gemini_model="gemini-2.5-flash",
        timeout_s=25,
        max_images=6,
        image_detail="auto",
        reasoning_effort="low",
        vertex_search_enabled=False,
    )
    gemini_profile = {
        "category": "handbag",
        "candidate_brand": "Louis Vuitton",
        "candidate_model": "Looping MM",
        "confidence": 0.88,
        "visual_signatures": ["monogram canvas", "single shoulder strap"],
        "grounding_sources": [{"domain": "google", "url": None, "snippet": "Gemini source"}],
        "dupe_risk_assessment": "Low based on visible monogram placement.",
        "why_not_fast_fashion": "Luxury construction details visible.",
        "model_identification": {
            "name": "Louis Vuitton Looping MM",
            "confidence": 0.88,
            "attributes": ["monogram canvas"],
        },
        "authenticity_screen": {
            "verdict": "inconclusive",
            "confidence": 0.5,
            "reasons": [],
            "required_checks": [],
            "disclaimer": "Screening signal only; not definitive authentication.",
        },
        "visual_condition_assessment": {
            "wear_level": "minimal",
            "box_included": "no",
            "dust_bag_included": "unclear",
            "new_in_box_signal": "no",
            "pricing_tier": "excellent",
            "confidence": 0.7,
            "evidence": ["clean canvas"],
        },
        "retail_price_estimate": {"estimated_price": 0, "currency": "USD", "confidence": 0.1, "rationale": "", "references": []},
        "resale_price_estimate": {"estimated_price": 100, "currency": "USD", "confidence": 0.1, "rationale": "Gemini placeholder", "condition_assumption": "LikeNew", "references": []},
        "resale_price_breakdown": [{"label": "default", "estimated_price": 100, "range_low": None, "range_high": None, "currency": "USD", "confidence": 0.1, "rationale": ""}],
        "receipt_present": "unclear",
        "expected_auth_docs": {"usually_provided": "mixed", "typical_documents": [], "confidence": 0.5, "notes": ""},
        "shipping_profile": {
            "item_type": "handbag",
            "weight_class": "medium",
            "estimated_weight_oz": 48,
            "confidence": 0.6,
            "rationale": "Packaged weight for a small handbag.",
        },
    }
    openai_valuation = {
        "grounding_sources": [{"domain": "therealreal.com", "url": "https://www.therealreal.com/example", "snippet": "Comp"}],
        "retail_price_estimate": {"estimated_price": 1650, "currency": "USD", "confidence": 0.6, "rationale": "Retail reference", "references": []},
        "resale_price_estimate": {
            "estimated_price": 920,
            "currency": "USD",
            "confidence": 0.7,
            "rationale": "Resale comps",
            "condition_assumption": "LikeNew",
            "references": [{"source": "The RealReal", "url": "https://www.therealreal.com/example"}],
        },
        "resale_price_breakdown": [{"label": "LikeNew", "estimated_price": 920, "range_low": 850, "range_high": 990, "currency": "USD", "confidence": 0.7, "rationale": "Comp range"}],
        "expected_auth_docs": {"usually_provided": "mixed", "typical_documents": ["date code"], "confidence": 0.6, "notes": "Often included."},
        "shipping_profile": {
            "item_type": "handbag",
            "weight_class": "medium",
            "estimated_weight_oz": 48,
            "confidence": 0.6,
            "rationale": "Packaged weight for a small handbag.",
        },
    }

    monkeypatch.setattr(profiler, "_call_gemini", lambda **_: gemini_profile)
    monkeypatch.setattr(profiler, "_call_openai_valuation", lambda **_: openai_valuation)

    result = profiler.profile_item(
        images=[],
        brand_name="",
        category="",
        item_size="Medium",
        condition_grade="LikeNew",
        condition_source="user",
        item_description=None,
    )

    assert result.profile is not None
    assert result.profile["_provider"] == "hybrid"
    assert result.profile["candidate_brand"] == "Louis Vuitton"
    assert result.profile["candidate_model"] == "Looping MM"
    assert result.profile["resale_price_estimate"]["estimated_price"] == 920
    assert result.profile["grounding_sources"][0]["domain"] == "therealreal.com"
    assert result.profile["shipping_profile"]["estimated_weight_oz"] == 48
    assert result.profile["_workflow"]["hybrid"]["identification_provider"] == "gemini"
    assert result.profile["_workflow"]["hybrid"]["valuation_provider"] == "openai"


def test_profile_normalization_infers_shipping_profile_when_missing() -> None:
    profiler = _profiler(max_images=6)

    normalized = profiler._normalize_profile_shape({
        "category": "clothes",
        "candidate_brand": "Theory",
        "candidate_model": "Gabe Blazer",
        "confidence": 0.8,
        "visual_signatures": ["structured blazer", "lined jacket"],
        "grounding_sources": [],
        "dupe_risk_assessment": "",
        "why_not_fast_fashion": "",
        "model_identification": {
            "name": "Theory Gabe Blazer",
            "confidence": 0.8,
            "attributes": ["structured blazer"],
        },
        "authenticity_screen": {
            "verdict": "inconclusive",
            "confidence": 0.5,
            "reasons": [],
            "required_checks": [],
            "disclaimer": "screening only",
        },
        "visual_condition_assessment": {},
        "retail_price_estimate": {},
        "resale_price_estimate": {},
        "resale_price_breakdown": [],
        "receipt_present": "unclear",
        "expected_auth_docs": {},
    })

    assert normalized["shipping_profile"]["item_type"] == "jacket"
    assert normalized["shipping_profile"]["estimated_weight_oz"] == 48
    assert normalized["shipping_profile"]["weight_class"] == "medium"


def test_visual_condition_normalization_infers_structured_fields_from_evidence() -> None:
    condition = _profiler(max_images=6)._normalize_visual_condition_assessment({
        "wear_level": "unclear",
        "box_included": "unclear",
        "dust_bag_included": "no",
        "new_in_box_signal": "unclear",
        "pricing_tier": "unclear",
        "confidence": 0,
        "evidence": [
            "original branded box visible",
            "pristine soles with sticker/tag",
            "no visible wear on leather or hardware",
        ],
    })

    assert condition["wear_level"] == "pristine"
    assert condition["box_included"] == "yes"
    assert condition["new_in_box_signal"] == "yes"
    assert condition["pricing_tier"] == "new_in_box"
    assert condition["confidence"] == 0.65


def test_openai_valuation_payload_uses_gemini_context_without_images() -> None:
    profiler = GptItemProfiler(
        enabled=True,
        provider_order="hybrid",
        openai_api_key="openai-test",
        openai_model="gpt-5",
        gemini_api_key="gemini-test",
        gemini_model="gemini-2.5-flash",
        timeout_s=120,
        max_images=6,
        image_detail="auto",
        reasoning_effort="low",
        vertex_search_enabled=False,
    )
    content = [
        {"type": "input_text", "text": "Known context: category=clothes; condition=NewWithTags"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,abc", "detail": "auto"},
    ]
    payload = profiler._build_openai_valuation_payload(
        content=content,
        gemini_profile={
            "category": "clothes",
            "candidate_brand": "Theory",
            "candidate_model": "Gabe Blazer",
            "model_identification": {"name": "Theory Gabe Blazer", "confidence": 0.8, "attributes": []},
            "visual_signatures": ["tag visible"],
            "visual_condition_assessment": {"wear_level": "pristine", "pricing_tier": "new_in_box"},
        },
    )

    valuation_content = payload["input"][0]["content"]
    assert all(part["type"] != "input_image" for part in valuation_content)
    assert "Theory" in valuation_content[-1]["text"]
    assert "Gabe Blazer" in valuation_content[-1]["text"]


def test_openai_valuation_payload_uses_candidate_prompt_by_default() -> None:
    profiler = _profiler(max_images=6)
    payload = profiler._build_openai_valuation_payload(
        content=[{"type": "input_text", "text": "Known context: category=shoes; condition=NewWithTags"}],
        gemini_profile={
            "category": "shoes",
            "candidate_brand": "Chanel",
            "candidate_model": "Slingback Pumps",
            "model_identification": {"name": "Chanel Slingback Pumps", "confidence": 0.8, "attributes": []},
            "visual_signatures": [],
            "visual_condition_assessment": {},
        },
    )

    valuation_prompt = payload["input"][0]["content"][-1]["text"]
    assert "### IDENTITY & SOURCES" in valuation_prompt
    assert "MSRP / RETAIL SEARCH WATERFALL LOGIC" in valuation_prompt
    assert "SIZE & SEASON EXCLUSION" in valuation_prompt
    assert "Do not increase, decrease, discount, premium, or otherwise adjust valuation because of size, season" in valuation_prompt
    assert "common/in-demand sizes vs. extreme outlier sizes" not in valuation_prompt
    assert "Current / Near-Current Season" not in valuation_prompt
    assert "Off-Season / Older Archive" not in valuation_prompt
    assert "CONDITION-TIER TABLE" in valuation_prompt
    assert "Valuation task: Use the Gemini visual identification" not in valuation_prompt


def test_openai_valuation_payload_accepts_prompt_override() -> None:
    profiler = GptItemProfiler(
        enabled=True,
        provider_order="hybrid",
        openai_api_key="openai-test",
        openai_model="gpt-5",
        gemini_api_key="gemini-test",
        gemini_model="gemini-2.5-flash",
        timeout_s=120,
        max_images=6,
        image_detail="auto",
        reasoning_effort="low",
        vertex_search_enabled=False,
    )
    payload = profiler._build_openai_valuation_payload(
        content=[{"type": "input_text", "text": "Known context: category=shoes; condition=New"}],
        gemini_profile={
            "category": "shoes",
            "candidate_brand": "Chanel",
            "candidate_model": "Cap-Toe Ankle Boots",
            "model_identification": {"name": "Chanel Cap-Toe Ankle Boots", "confidence": 0.8, "attributes": []},
            "visual_signatures": [],
            "visual_condition_assessment": {},
        },
        valuation_prompt_override="Candidate prompt B. Use only patient-trade pricing.",
    )

    valuation_prompt = payload["input"][0]["content"][-1]["text"]
    assert "Candidate prompt B" in valuation_prompt
    assert "Valuation task: Use the Gemini visual identification" not in valuation_prompt
