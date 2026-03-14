import io
import os
import tempfile

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw


def _make_image(text: str = "") -> bytes:
    img = Image.new("RGB", (320, 320), color="white")
    d = ImageDraw.Draw(img)
    d.rectangle((40, 60, 280, 260), outline="black", width=4)
    if text:
        d.text((70, 140), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _build_client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="valueai-data-")
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["API_KEY"] = "test-key"
    os.environ["BRAND_DEBUG"] = "false"

    from app import deps, settings

    settings.get_settings.cache_clear()
    deps.get_db.cache_clear()
    deps.get_storage.cache_clear()
    deps.get_brand_analyzer.cache_clear()
    deps.get_condition_analyzer.cache_clear()

    from app.main import app

    return TestClient(app)


def test_analyze_response_schema_and_debug_payload() -> None:
    client = _build_client()
    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("nike_tag_closeup.jpg", _make_image("NIKE"), "image/jpeg")),
    ]
    data = {"item_id": "item-123", "debug": "true"}
    res = client.post("/v1/analyze", data=data, files=files, headers={"x-api-key": "test-key"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["item_id"] == "item-123"
    assert body["category"] in {"clothes", "shoes", "handbag"}
    assert body["brand"]["name"] == "Nike"
    assert body["brand"]["evidence"] == "ocr_tag"
    assert body["brand"]["confidence"] >= 0.75
    assert body["condition"]["grade"] in {"New", "LikeNew", "Good", "Fair", "Poor"}
    assert isinstance(body["condition"]["confidence"], float)
    assert "valuation" in body
    assert body["valuation"] is not None
    assert body["valuation"]["currency"] == "USD"
    assert "estimated_value" in body["valuation"]
    assert "debug" in body and body["debug"] is not None
    assert "brand" in body["debug"]
    assert "condition" in body["debug"]
    assert "valuation" in body["debug"]
    assert "thresholds" in body["debug"]
    assert body["warnings"] == []


def test_analyze_accepts_item_size_in_debug_hints() -> None:
    client = _build_client()
    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("nike_tag_closeup.jpg", _make_image("NIKE"), "image/jpeg")),
    ]
    data = {"item_id": "item-size-test", "category": "shoes", "item_size": "US 10", "debug": "true"}
    res = client.post("/v1/analyze", data=data, files=files, headers={"x-api-key": "test-key"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["debug"] is not None
    assert body["debug"]["input_hints"]["item_size"] == "US 10"


def test_analyze_generates_item_id_when_missing() -> None:
    client = _build_client()
    files = [("images", ("full_item.jpg", _make_image(), "image/jpeg"))]
    res = client.post("/v1/analyze", data={"debug": "true"}, files=files, headers={"x-api-key": "test-key"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert isinstance(body["item_id"], str)
    assert body["item_id"].startswith("item-")
    assert len(body["item_id"]) > 10


def test_analyze_unknown_brand_requests_more_photos() -> None:
    client = _build_client()
    files = [("images", ("full_item.jpg", _make_image(), "image/jpeg"))]
    res = client.post(
        "/v1/analyze",
        data={"item_id": "item-unknown"},
        files=files,
        headers={"x-api-key": "test-key"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["brand"]["name"] == "unknown"
    assert body["valuation"] is None
    assert "close_up_tag_label" in body["requested_photos"]


def test_analyze_warns_when_user_condition_conflicts_with_model() -> None:
    client = _build_client()
    from app.deps import get_condition_analyzer
    from app.main import app
    from condition.types import ConditionResult

    class LowConditionAnalyzer:
        def analyze(self, primary_image: bytes, category_hint: str | None = None, debug: bool = False):
            return ConditionResult(
                category=category_hint or "handbag",
                category_confidence=1.0,
                grade="Fair",
                confidence=0.86,
                issues=[],
                debug={"condition": {"model": "test_override"}},
            )

    app.dependency_overrides[get_condition_analyzer] = lambda: LowConditionAnalyzer()
    files = [("images", ("full_item.jpg", _make_image(), "image/jpeg"))]
    try:
        res = client.post(
            "/v1/analyze",
            data={"user_condition": "LikeNew"},
            files=files,
            headers={"x-api-key": "test-key"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["user_condition"] == "LikeNew"
        assert body["condition"]["grade"] == "Fair"
        assert len(body["warnings"]) == 1
        assert "model assessment suggests Fair" in body["warnings"][0]
    finally:
        app.dependency_overrides.clear()


def test_user_condition_drives_valuation_before_model_is_trusted() -> None:
    client = _build_client()
    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("nike_tag_closeup.jpg", _make_image("NIKE"), "image/jpeg")),
    ]
    res = client.post(
        "/v1/analyze",
        data={"user_condition": "New", "debug": "true"},
        files=files,
        headers={"x-api-key": "test-key"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user_condition"] == "New"
    assert body["condition"]["grade"] in {"New", "LikeNew", "Good", "Fair", "Poor"}
    assert body["valuation"] is not None
    assert body["debug"]["valuation"]["condition_source"] == "user_input"
    assert body["debug"]["valuation"]["condition_grade_used"] == "New"


def test_gpt_pricing_is_used_as_primary_when_available() -> None:
    os.environ["VALUATION_PROVIDERS"] = "stub"
    client = _build_client()
    os.environ["GPT_ITEM_PROFILE_ENABLED"] = "true"
    from app.deps import get_brand_analyzer, get_gpt_item_profiler, get_valuation_service
    from app.main import app
    from app.gpt_item_profile import GptItemProfileResult

    class StubBrandAnalyzer:
        def analyze(self, image_inputs, debug=False):
            return {"name": "Nike", "confidence": 0.9, "evidence": "stub"}

    class StubGptProfiler:
        def profile_item(self, **kwargs):
            return GptItemProfileResult(
                profile={
                    "model_identification": {"name": "Test Model", "confidence": 0.8, "attributes": []},
                    "authenticity_screen": {
                        "verdict": "inconclusive",
                        "confidence": 0.6,
                        "reasons": [],
                        "required_checks": [],
                        "disclaimer": "screening only",
                    },
                    "retail_price_estimate": {
                        "estimated_price": 1200,
                        "currency": "USD",
                        "confidence": 0.7,
                        "rationale": "stub",
                        "references": [],
                    },
                    "resale_price_estimate": {
                        "estimated_price": 700,
                        "currency": "USD",
                        "confidence": 0.66,
                        "rationale": "stub",
                        "condition_assumption": "Good",
                        "references": [],
                    },
                },
                enabled=True,
                called=True,
            )

    class FailIfCalledValuationService:
        def evaluate(self, request, debug=False):
            raise AssertionError("Crawler valuation should not be called when GPT price is available")

        @staticmethod
        def serialize(result):
            return {}

    app.dependency_overrides[get_brand_analyzer] = lambda: StubBrandAnalyzer()
    app.dependency_overrides[get_gpt_item_profiler] = lambda: StubGptProfiler()
    app.dependency_overrides[get_valuation_service] = lambda: FailIfCalledValuationService()

    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("nike_tag_closeup.jpg", _make_image("NIKE"), "image/jpeg")),
    ]
    try:
        res = client.post("/v1/analyze", data={"debug": "true"}, files=files, headers={"x-api-key": "test-key"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["valuation"] is not None
        assert body["valuation"]["estimated_value"] == 700
        assert body["valuation"]["basis"] == "gpt_resale_estimate_primary"
        assert body["debug"]["valuation"]["pricing_source"] == "gpt_primary"
        assert body["debug"]["valuation"]["pricing_fallback_used"] is False
    finally:
        app.dependency_overrides.clear()


def test_crawler_pricing_is_used_as_fallback_when_gpt_has_no_price() -> None:
    os.environ["VALUATION_PROVIDERS"] = "stub"
    client = _build_client()
    os.environ["GPT_ITEM_PROFILE_ENABLED"] = "true"
    from app.deps import get_brand_analyzer, get_gpt_item_profiler, get_valuation_service
    from app.main import app
    from app.gpt_item_profile import GptItemProfileResult
    from valuation.types import ValuationResult

    class StubBrandAnalyzer:
        def analyze(self, image_inputs, debug=False):
            return {"name": "Nike", "confidence": 0.9, "evidence": "stub"}

    class StubGptProfilerNoPrice:
        def profile_item(self, **kwargs):
            return GptItemProfileResult(
                profile={
                    "model_identification": {"name": "Test Model", "confidence": 0.8, "attributes": []},
                    "authenticity_screen": {
                        "verdict": "inconclusive",
                        "confidence": 0.6,
                        "reasons": [],
                        "required_checks": [],
                        "disclaimer": "screening only",
                    },
                    "retail_price_estimate": {
                        "estimated_price": None,
                        "currency": "USD",
                        "confidence": 0.4,
                        "rationale": "stub",
                        "references": [],
                    },
                    "resale_price_estimate": {
                        "estimated_price": None,
                        "currency": "USD",
                        "confidence": 0.4,
                        "rationale": "stub",
                        "condition_assumption": "Good",
                        "references": [],
                    },
                },
                enabled=True,
                called=True,
            )

    class StubFallbackValuationService:
        def evaluate(self, request, debug=False):
            return ValuationResult(
                estimated_value=321.0,
                currency="USD",
                range_low=300.0,
                range_high=350.0,
                confidence=0.8,
                basis="median_sold_comps_with_condition_adjustment",
                comps_summary={"count": 3, "source_breakdown": {"stub": 3}},
                resale_market_value=321.0,
                retail_reference_value=None,
                debug={"providers": ["stub"]} if debug else {},
            )

        @staticmethod
        def serialize(result):
            payload = {
                "estimated_value": result.estimated_value,
                "currency": result.currency,
                "range_low": result.range_low,
                "range_high": result.range_high,
                "confidence": result.confidence,
                "basis": result.basis,
                "comps_summary": result.comps_summary,
                "resale_market_value": result.resale_market_value,
                "retail_reference_value": result.retail_reference_value,
            }
            if result.debug:
                payload["_debug"] = result.debug
            return payload

    app.dependency_overrides[get_brand_analyzer] = lambda: StubBrandAnalyzer()
    app.dependency_overrides[get_gpt_item_profiler] = lambda: StubGptProfilerNoPrice()
    app.dependency_overrides[get_valuation_service] = lambda: StubFallbackValuationService()

    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("nike_tag_closeup.jpg", _make_image("NIKE"), "image/jpeg")),
    ]
    try:
        res = client.post("/v1/analyze", data={"debug": "true"}, files=files, headers={"x-api-key": "test-key"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["valuation"] is not None
        assert body["valuation"]["estimated_value"] == 321.0
        assert body["debug"]["valuation"]["pricing_source"] == "crawler_fallback"
        assert body["debug"]["valuation"]["pricing_fallback_used"] is True
    finally:
        app.dependency_overrides.clear()


def test_create_and_list_listing_with_api_key() -> None:
    client = _build_client()
    create_payload = {
        "title": "Jimmy Choo Rosalia 50 Slingback Pump",
        "mode": "sell_trade",
        "category": "shoes",
        "brand": "Jimmy Choo",
        "condition": "Good",
        "estimated_value": 425.0,
        "city": "New York, NY",
        "image": "https://example.test/image.jpg",
        "wants": "Open to similar-value offers",
        "tags": ["Good", "Jimmy Choo", "sell/trade"],
        "source_item_id": "item-abc",
        "analysis": {"item_id": "item-abc"},
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["listing_id"]
    assert created["owner_subject"] == "api-key"
    assert created["title"] == create_payload["title"]

    list_res = client.get("/v1/listings?limit=5", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    payload = list_res.json()
    assert payload["count"] >= 1
    assert any(item["listing_id"] == created["listing_id"] for item in payload["items"])
