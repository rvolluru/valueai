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
    assert result.profile["_workflow"]["hybrid"]["identification_provider"] == "gemini"
    assert result.profile["_workflow"]["hybrid"]["valuation_provider"] == "openai"
