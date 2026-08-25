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
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["PHOTOROOM_API_KEY"] = ""
    os.environ["IMAGE_STAGING_ENABLED"] = "true"
    os.environ["IMAGE_STAGING_PHOTOROOM_ENABLED"] = "false"
    os.environ["IMAGE_STAGING_GEMINI_ENABLED"] = "false"
    os.environ["CONDITION_REMBG_ENABLED"] = "false"

    from app import deps, settings

    settings.get_settings.cache_clear()
    deps.get_db.cache_clear()
    deps.get_storage.cache_clear()
    deps.get_brand_analyzer.cache_clear()
    deps.get_condition_analyzer.cache_clear()

    from app.main import app

    app.dependency_overrides.clear()
    return TestClient(app)


def _stub_item_profile(
    *,
    brand: str = "Nike",
    model: str = "Air Force 1",
    category: str = "shoes",
    estimated_price: float | None = 700.0,
) -> dict:
    resale_price = estimated_price
    return {
        "category": category,
        "candidate_brand": brand,
        "candidate_model": model,
        "confidence": 0.9,
        "model_identification": {
            "name": model,
            "confidence": 0.85,
            "attributes": ["clean silhouette", "signature construction"],
        },
        "authenticity_screen": {
            "verdict": "inconclusive",
            "confidence": 0.6,
            "reasons": [],
            "required_checks": [],
            "disclaimer": "screening only",
        },
        "expected_auth_docs": {
            "usually_provided": "no",
            "typical_documents": [],
        },
        "receipt_present": "no",
        "retail_price_estimate": {
            "estimated_price": 1200 if resale_price is not None else None,
            "currency": "USD",
            "confidence": 0.7,
            "rationale": "stub",
            "references": [],
        },
        "resale_price_estimate": {
            "estimated_price": resale_price,
            "currency": "USD",
            "confidence": 0.66,
            "rationale": "stub",
            "condition_assumption": "LikeNew",
            "references": [],
        },
    }


def _override_gpt_profiler(profile: dict | None):
    from app.deps import get_gpt_item_profiler
    from app.gpt_item_profile import GptItemProfileResult
    from app.main import app

    class StubGptProfiler:
        def profile_item(self, **kwargs):
            return GptItemProfileResult(profile=profile, enabled=True, called=True)

    app.dependency_overrides[get_gpt_item_profiler] = lambda: StubGptProfiler()
    return app


def test_listing_title_from_analysis_uses_label_brand_for_generic_model() -> None:
    from app.main import _listing_title_from_analysis

    title = _listing_title_from_analysis(
        "unknown unknown",
        model_name="Unidentified tiered ruffle dress with lace detail",
        profile={"shipping_profile": {"item_type": "dress"}},
        brand="ALEXIS",
        category="clothes",
    )

    assert title == "ALEXIS tiered ruffle dress with lace detail"


def test_listing_title_from_analysis_preserves_specific_model_title() -> None:
    from app.main import _listing_title_from_analysis

    title = _listing_title_from_analysis(
        "New listing",
        model_name="Classic Flap Bag",
        profile={},
        brand="Chanel",
        category="handbag",
    )

    assert title == "Classic Flap Bag"


def test_listing_title_from_analysis_replaces_unclear_placeholder() -> None:
    from app.main import _listing_title_from_analysis

    title = _listing_title_from_analysis(
        "unclear",
        model_name="Sylvie Crochet Top (style LCDE-WS1076)",
        profile={},
        brand="L'Academie",
        category="clothes",
    )

    assert title == "Sylvie Crochet Top (style LCDE-WS1076)"


def test_listing_title_from_analysis_replaces_unidentified_with_brand_category() -> None:
    from app.main import _listing_title_from_analysis

    title = _listing_title_from_analysis(
        "unidentified",
        model_name="unidentified",
        profile={},
        brand="HERVE LEGER PARIS",
        category="clothes",
    )

    assert title == "HERVE LEGER PARIS clothing item"


def test_shippo_flat_rate_quote_overrides_display_amount_but_keeps_rate_id() -> None:
    from app.main import _apply_shippo_flat_rate_quote, _estimated_shipping_weight_oz_from_listing
    from app.settings import Settings

    settings = Settings(
        shippo_flat_rate_enabled=True,
        shippo_flat_rate_amount="6.49",
        shippo_flat_rate_currency="USD",
        shippo_flat_rate_max_weight_oz=32,
        shippo_parcel_weight_oz=32,
    )
    quote = {
        "status": "quoted",
        "carrier": "USPS",
        "service_level": "Priority Mail",
        "amount": "12.34",
        "currency": "USD",
        "rate_id": "shippo-rate-123",
        "parcel_weight_oz": str(_estimated_shipping_weight_oz_from_listing({
            "analysis": {
                "item_profile": {
                    "shipping_profile": {
                        "item_type": "dress",
                        "estimated_weight_oz": 20,
                    }
                }
            }
        }, settings)),
    }

    display_quote = _apply_shippo_flat_rate_quote(settings=settings, quote=quote)

    assert display_quote["amount"] == "6.49"
    assert display_quote["currency"] == "USD"
    assert display_quote["rate_id"] == "shippo-rate-123"
    assert "shippo_rate=USD 12.34" in display_quote["debug"]
    assert "jouft_flat_rate=USD 6.49" in display_quote["debug"]
    assert "max_weight_oz=32" in display_quote["debug"]


def test_shippo_flat_rate_quote_does_not_apply_above_weight_limit() -> None:
    from app.main import _apply_shippo_flat_rate_quote
    from app.settings import Settings

    settings = Settings(
        shippo_flat_rate_enabled=True,
        shippo_flat_rate_amount="6.49",
        shippo_flat_rate_max_weight_oz=32,
        shippo_parcel_weight_oz=96,
    )
    quote = {
        "status": "quoted",
        "carrier": "USPS",
        "service_level": "Priority Mail",
        "amount": "14.50",
        "currency": "USD",
        "rate_id": "shippo-rate-456",
    }

    display_quote = _apply_shippo_flat_rate_quote(settings=settings, quote=quote)

    assert display_quote == quote


def test_google_places_address_suggest_parses_components(monkeypatch) -> None:
    from app.main import _google_places_address_suggest
    from app.settings import Settings

    class FakeResponse:
        status_code = 200
        content = b"{}"

        def __init__(self, payload: dict):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json, headers):
            assert "places:autocomplete" in url
            assert headers["X-Goog-Api-Key"] == "google-key"
            assert json["includedRegionCodes"] == ["us"]
            return FakeResponse({
                "suggestions": [{
                    "placePrediction": {
                        "placeId": "places/abc123",
                        "text": {"text": "120 Vantis Dr Suite 300, Aliso Viejo, CA 92656"},
                    }
                }]
            })

        def get(self, url, headers):
            assert url.endswith("/places/abc123")
            return FakeResponse({
                "formattedAddress": "120 Vantis Dr Suite 300, Aliso Viejo, CA 92656, USA",
                "addressComponents": [
                    {"longText": "120", "shortText": "120", "types": ["street_number"]},
                    {"longText": "Vantis Drive", "shortText": "Vantis Dr", "types": ["route"]},
                    {"longText": "Aliso Viejo", "shortText": "Aliso Viejo", "types": ["locality"]},
                    {"longText": "California", "shortText": "CA", "types": ["administrative_area_level_1"]},
                    {"longText": "92656", "shortText": "92656", "types": ["postal_code"]},
                    {"longText": "United States", "shortText": "US", "types": ["country"]},
                ],
            })

    monkeypatch.setattr("app.main.httpx.Client", FakeClient)
    result = _google_places_address_suggest(
        q="120 Vantis",
        city="Aliso Viejo",
        state="CA",
        postal_code="92656",
        settings=Settings(
            google_places_api_key="google-key",
            google_places_autocomplete_url="https://places.googleapis.com/v1/places:autocomplete",
            google_places_details_url="https://places.googleapis.com/v1/{place_id}",
        ),
    )

    suggestions = result["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["street_address"] == "120 Vantis Drive"
    assert suggestions[0]["city"] == "Aliso Viejo"
    assert suggestions[0]["state"] == "CA"
    assert suggestions[0]["postal_code"] == "92656"
    assert suggestions[0]["country"] == "US"
    assert suggestions[0]["provider"] == "google_places"


def test_shippo_tracking_snapshot_parses_delivery_status(monkeypatch) -> None:
    from app.main import _shippo_tracking_snapshot
    from app.settings import Settings

    class FakeResponse:
        status_code = 200
        content = b"{}"

        def json(self):
            return {
                "eta": "2026-08-15T12:00:00Z",
                "tracking_status": {
                    "status": "OUT_FOR_DELIVERY",
                    "status_details": "Out for delivery",
                    "status_date": "2026-08-14T09:30:00Z",
                },
                "tracking_history": [
                    {
                        "status": "TRANSIT",
                        "status_details": "Arrived at USPS facility",
                        "status_date": "2026-08-13T20:00:00Z",
                        "location": "Edison, NJ",
                    }
                ],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers):
            assert url == "https://api.goshippo.com/tracks/usps/940011189922385"
            assert headers["Authorization"] == "ShippoToken shippo-key"
            return FakeResponse()

    monkeypatch.setattr("app.main.httpx.Client", FakeClient)
    result = _shippo_tracking_snapshot(
        settings=Settings(shippo_api_key="shippo-key", shippo_api_base_url="https://api.goshippo.com"),
        carrier="USPS",
        tracking_number="940011189922385",
    )

    assert result["status"] == "out_for_delivery"
    assert result["tracking_status"] == "out_for_delivery"
    assert result["tracking_status_details"] == "Out for delivery"
    assert result["tracking_status_updated_at"] == "2026-08-14T09:30:00Z"
    assert result["tracking_eta"] == "2026-08-15T12:00:00Z"
    assert result["tracking_history"][0]["location"] == "Edison, NJ"


def test_analyze_response_schema_and_debug_payload() -> None:
    client = _build_client()
    _override_gpt_profiler(_stub_item_profile())
    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("nike_tag_closeup.jpg", _make_image("NIKE"), "image/jpeg")),
    ]
    data = {"item_id": "item-123", "user_condition": "LikeNew", "debug": "true"}
    res = client.post("/v1/analyze", data=data, files=files, headers={"x-api-key": "test-key"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["item_id"] == "item-123"
    assert body["category"] in {"clothes", "shoes", "handbag"}
    assert body["brand"]["name"] == "Nike"
    assert body["brand"]["evidence"] == "gpt_item_profile"
    assert body["brand"]["confidence"] >= 0.75
    assert body["condition"]["grade"] in {"New", "LikeNew"}
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


def test_client_state_round_trip_uses_backend_storage() -> None:
    client = _build_client()

    initial = client.get("/v1/me/client-state", headers={"x-api-key": "test-key"})
    assert initial.status_code == 200, initial.text
    assert initial.json()["liked_listing_ids"] == []

    payload = {
        "alert_preferences": {"likes": True, "trades": False, "shipping": True},
        "liked_listing_ids": ["listing-1", "listing-2", "listing-1"],
    }
    saved = client.put("/v1/me/client-state", json=payload, headers={"x-api-key": "test-key"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["alert_preferences"] == payload["alert_preferences"]
    assert body["liked_listing_ids"] == ["listing-1", "listing-2"]

    fetched = client.get("/v1/me/client-state", headers={"x-api-key": "test-key"})
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["alert_preferences"] == payload["alert_preferences"]
    assert fetched.json()["liked_listing_ids"] == ["listing-1", "listing-2"]

    partial = client.put(
        "/v1/me/client-state",
        json={"liked_listing_ids": ["listing-3"]},
        headers={"x-api-key": "test-key"},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["alert_preferences"] == payload["alert_preferences"]
    assert partial.json()["liked_listing_ids"] == ["listing-3"]


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


def test_upload_images_persists_without_analysis() -> None:
    client = _build_client()
    files = [
        ("images", ("full_item.jpg", _make_image(), "image/jpeg")),
        ("images", ("detail.jpg", _make_image("DETAIL"), "image/jpeg")),
    ]
    res = client.post("/v1/uploads/images", data={"item_id": "item-upload-only"}, files=files, headers={"x-api-key": "test-key"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["item_id"] == "item-upload-only"
    assert len(body["uploaded_images"]) == 2
    assert body["uploaded_images"][0]["image_url"].startswith("/v1/images/")
    assert body["uploaded_images"][0]["role_hint"] == "full_item"
    assert body["uploaded_images"][1]["role_hint"] == "close_up"


def test_presigned_upload_confirm_persists_images() -> None:
    client = _build_client()

    from app import deps
    from app.storage import Storage

    class FakePresignedStorage(Storage):
        def save_upload(self, item_id: str, filename: str, content_type: str, data: bytes) -> str:
            raise NotImplementedError

        def save_debug_artifact(self, item_id: str, filename: str, data: bytes) -> str:
            raise NotImplementedError

        def create_presigned_upload(self, item_id: str, filename: str, content_type: str, expires_in: int = 900) -> tuple[str, str]:
            return f"https://uploads.example.test/{item_id}/{filename}", f"s3://test-bucket/uploads/{item_id}/{filename}"

        def object_exists(self, storage_uri: str) -> bool:
            return storage_uri.startswith("s3://test-bucket/uploads/")

    client.app.dependency_overrides[deps.get_storage] = lambda: FakePresignedStorage()
    presign = client.post(
        "/v1/uploads/images/presign",
        json={
            "item_id": "item-direct-upload",
            "images": [
                {"filename": "full_item.jpeg", "content_type": "image/jpeg", "content_length": 123},
                {"filename": "detail.jpeg", "content_type": "image/jpeg", "content_length": 456},
            ],
        },
        headers={"x-api-key": "test-key"},
    )
    assert presign.status_code == 200, presign.text
    slots = presign.json()["upload_slots"]
    assert len(slots) == 2
    assert slots[0]["headers"]["Content-Type"] == "image/jpeg"

    confirm = client.post(
        "/v1/uploads/images/confirm",
        json={
            "item_id": "item-direct-upload",
            "uploaded_images": [
                {
                    "image_id": slots[0]["image_id"],
                    "filename": "full_item.jpg",
                    "content_type": "image/jpeg",
                    "storage_uri": slots[0]["storage_uri"],
                    "role_hint": slots[0]["role_hint"],
                    "content_hash": "abc",
                },
                {
                    "image_id": slots[1]["image_id"],
                    "filename": "detail.jpg",
                    "content_type": "image/jpeg",
                    "storage_uri": slots[1]["storage_uri"],
                    "role_hint": slots[1]["role_hint"],
                    "content_hash": "def",
                },
            ],
        },
        headers={"x-api-key": "test-key"},
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["item_id"] == "item-direct-upload"
    assert [entry["role_hint"] for entry in body["uploaded_images"]] == ["full_item", "close_up"]
    assert body["uploaded_images"][0]["image_url"].startswith("/v1/images/")
    image_urls = [entry["image_url"] for entry in body["uploaded_images"]]

    create = client.post(
        "/v1/listings",
        json={
            "title": "Direct upload listing",
            "mode": "trade",
            "category": "handbag",
            "brand": "Chanel",
            "condition": "LikeNew",
            "size": "Medium",
            "estimated_value": 1200,
            "city": "Your area",
            "image": image_urls[0],
            "images": image_urls,
            "description": "Created from direct-upload image URLs.",
            "wants": "Open to similar-value offers",
            "tags": [],
            "source_item_id": "item-direct-upload",
            "status": "Active",
        },
        headers={"x-api-key": "test-key"},
    )
    assert create.status_code == 200, create.text
    listing = create.json()
    listing_id = listing["listing_id"]
    assert listing["image"].startswith("/v1/images/")
    assert listing["images"] == image_urls

    closet = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert closet.status_code == 200, closet.text
    closet_items = closet.json()["items"]
    saved = next(item for item in closet_items if item["listing_id"] == listing_id)
    assert saved["image"].startswith("/v1/images/")
    assert len(saved["images"]) == 2
    assert all(url.startswith("/v1/images/") for url in saved["images"])

    marketplace = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert marketplace.status_code == 200, marketplace.text
    market_saved = next(item for item in marketplace.json()["items"] if item["listing_id"] == listing_id)
    assert market_saved["image"].startswith("/v1/images/")
    assert len(market_saved["images"]) == 2

    update = client.put(
        f"/v1/listings/{listing_id}",
        json={
            "title": "Edited direct upload listing",
            "mode": "trade",
            "category": "handbag",
            "brand": "Chanel",
            "condition": "LikeNew",
            "size": "Large",
            "estimated_value": 1300,
            "city": "Your area",
            "image": image_urls[1],
            "images": [image_urls[1], image_urls[0]],
            "description": "Edited with reordered direct-upload image URLs.",
            "wants": "Open to similar-value offers",
            "tags": [],
            "source_item_id": "item-direct-upload",
            "status": "Active",
        },
        headers={"x-api-key": "test-key"},
    )
    assert update.status_code == 200, update.text
    updated = update.json()
    assert updated["image"] == image_urls[1]
    assert updated["images"] == [image_urls[1], image_urls[0]]


def test_listings_support_limit_offset_pagination() -> None:
    client = _build_client()
    created_ids: list[str] = []
    for idx in range(5):
        payload = {
            "title": f"Paged Listing {idx}",
            "mode": "trade",
            "category": "handbag",
            "brand": "Chanel",
            "condition": "LikeNew",
            "size": "Medium",
            "estimated_value": 1000 + idx,
            "city": "Your area",
            "image": f"https://example.test/paged-{idx}.jpg",
            "images": [f"https://example.test/paged-{idx}.jpg"],
            "description": "Pagination test listing.",
            "wants": "Open to similar-value offers",
            "tags": [],
            "status": "Active",
        }
        res = client.post("/v1/listings", json=payload, headers={"x-api-key": "test-key"})
        assert res.status_code == 200, res.text
        created_ids.append(res.json()["listing_id"])

    first = client.get("/v1/listings?mine=true&limit=2&offset=0", headers={"x-api-key": "test-key"})
    second = client.get("/v1/listings?mine=true&limit=2&offset=2", headers={"x-api-key": "test-key"})
    last = client.get("/v1/listings?mine=true&limit=2&offset=4", headers={"x-api-key": "test-key"})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert last.status_code == 200, last.text

    first_body = first.json()
    second_body = second.json()
    last_body = last.json()
    assert first_body["has_more"] is True
    assert first_body["next_offset"] == 2
    assert second_body["has_more"] is True
    assert second_body["next_offset"] == 4
    assert last_body["has_more"] is False
    assert last_body["next_offset"] is None

    first_ids = [item["listing_id"] for item in first_body["items"]]
    second_ids = [item["listing_id"] for item in second_body["items"]]
    last_ids = [item["listing_id"] for item in last_body["items"]]
    assert first_ids == list(reversed(created_ids[-2:]))
    assert second_ids == list(reversed(created_ids[1:3]))
    assert last_ids == [created_ids[0]]


def test_create_listing_with_analyzing_status_queues_backend_analysis() -> None:
    client = _build_client()
    _override_gpt_profiler(
        _stub_item_profile(
            brand="Chanel",
            model="Classic Flap Bag",
            category="handbag",
            estimated_price=2300,
        )
    )
    upload = client.post(
        "/v1/uploads/images",
        data={"item_id": "item-create-analysis"},
        files=[("images", ("full_item.jpg", _make_image("CHANEL"), "image/jpeg"))],
        headers={"x-api-key": "test-key"},
    )
    assert upload.status_code == 200, upload.text
    image_url = upload.json()["uploaded_images"][0]["image_url"]

    create_res = client.post(
        "/v1/listings",
        json={
            "title": "New listing",
            "mode": "trade",
            "category": "handbag",
            "brand": "unknown",
            "condition": "LikeNew",
            "size": "Medium",
            "estimated_value": 0,
            "city": "Your area",
            "image": image_url,
            "images": [image_url],
            "description": "",
            "wants": "Open to similar-value offers",
            "tags": ["Analyzing"],
            "source_item_id": "item-create-analysis",
            "analysis": None,
            "status": "Analyzing",
        },
        headers={"x-api-key": "test-key"},
    )
    assert create_res.status_code == 200, create_res.text
    listing_id = create_res.json()["listing_id"]

    list_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listing = next(item for item in list_res.json()["items"] if item["listing_id"] == listing_id)
    assert listing["status"] == "Review"
    assert listing["title"] == "Classic Flap Bag"
    assert listing["brand"] == "Chanel"
    assert listing["estimated_value"] == 2300
    assert listing["image"] == image_url
    assert listing["images"] == [image_url]
    assert listing["analysis"]["brand"]["name"] == "Chanel"


def test_create_listing_reuses_recent_analysis_for_same_uploaded_images() -> None:
    client = _build_client()
    _override_gpt_profiler(
        _stub_item_profile(
            brand="Louis Vuitton",
            model="Looping MM",
            category="handbag",
            estimated_price=1150,
        )
    )
    image_bytes = _make_image("LV")
    analyze_res = client.post(
        "/v1/analyze",
        data={"item_id": "item-original-analysis", "user_condition": "LikeNew", "debug": "true"},
        files=[("images", ("lv.jpg", image_bytes, "image/jpeg"))],
        headers={"x-api-key": "test-key"},
    )
    assert analyze_res.status_code == 200, analyze_res.text

    upload = client.post(
        "/v1/uploads/images",
        data={"item_id": "item-repeat-upload"},
        files=[("images", ("lv-repeat.jpg", image_bytes, "image/jpeg"))],
        headers={"x-api-key": "test-key"},
    )
    assert upload.status_code == 200, upload.text
    image_url = upload.json()["uploaded_images"][0]["image_url"]

    create_res = client.post(
        "/v1/listings",
        json={
            "title": "New listing",
            "mode": "trade",
            "category": "handbag",
            "brand": "unknown",
            "condition": "LikeNew",
            "size": "Medium",
            "estimated_value": 0,
            "city": "Your area",
            "image": image_url,
            "images": [image_url],
            "description": "",
            "wants": "Open to similar-value offers",
            "tags": ["Analyzing"],
            "source_item_id": "item-repeat-upload",
            "analysis": None,
            "status": "Analyzing",
        },
        headers={"x-api-key": "test-key"},
    )
    assert create_res.status_code == 200, create_res.text
    body = create_res.json()
    assert body["status"] == "Analyzing"
    assert body["image"] == image_url
    assert body["images"] == [image_url]

    list_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listing = next(item for item in list_res.json()["items"] if item["listing_id"] == body["listing_id"])
    assert listing["status"] == "Review"
    assert listing["title"] == "Looping MM"
    assert listing["brand"] == "Louis Vuitton"
    assert listing["estimated_value"] == 1150
    assert listing["image"] == image_url
    assert listing["images"] == [image_url]
    assert listing["analysis"]["item_id"] == "item-repeat-upload"
    assert listing["analysis"]["uploaded_images"][0]["image_url"] == image_url
    assert listing["analysis"]["debug"]["analysis_reuse"]["reused"] is True


def test_create_listing_with_analyzing_status_marks_failed_when_images_are_unreadable() -> None:
    client = _build_client()
    _override_gpt_profiler(_stub_item_profile())

    create_res = client.post(
        "/v1/listings",
        json={
            "title": "New listing",
            "mode": "trade",
            "category": "handbag",
            "brand": "unknown",
            "condition": "LikeNew",
            "size": None,
            "estimated_value": 0,
            "city": "Your area",
            "image": "/v1/images/missing-image-id",
            "images": ["/v1/images/missing-image-id"],
            "description": "",
            "wants": "Open to similar-value offers",
            "tags": ["Analyzing"],
            "source_item_id": "item-missing-image",
            "analysis": None,
            "status": "Analyzing",
        },
        headers={"x-api-key": "test-key"},
    )
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["status"] == "Analyzing"

    list_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listing = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listing["status"] == "AnalysisFailed"
    assert listing["tags"] == ["Analysis failed"]


def test_recently_updated_analyzing_listing_is_not_marked_stale_by_original_created_at() -> None:
    client = _build_client()
    from app import deps

    db = deps.get_db()
    db.insert_listing(
        listing_id="recent-edit-analyzing",
        owner_subject="api-key",
        owner_name="Local Tester",
        title="Old Listing Recently Edited",
        mode="trade",
        category="handbag",
        brand="Louis Vuitton",
        condition="New",
        size="Large",
        estimated_value=1200.0,
        city="Your area",
        image="https://example.test/bag.jpg",
        images=["https://example.test/bag.jpg"],
        description="Recently edited listing",
        wants="Open to similar-value offers",
        tags=["Analyzing"],
        source_item_id=None,
        analysis=None,
        status="Analyzing",
    )
    db.execute(
        "UPDATE listings SET created_at = ?, updated_at = ? WHERE listing_id = ?",
        (
            "2026-01-01T00:00:00+00:00",
            "2099-01-01T00:00:00+00:00",
            "recent-edit-analyzing",
        ),
    )
    db.commit()

    list_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listing = next(item for item in list_res.json()["items"] if item["listing_id"] == "recent-edit-analyzing")
    assert listing["status"] == "Analyzing"


def test_listing_media_repair_does_not_append_analysis_uploads_to_existing_gallery() -> None:
    client = _build_client()
    from app import deps

    db = deps.get_db()
    analysis_uploads = [
        {"image_id": f"original-{idx}", "image_url": f"/v1/images/original-{idx}"}
        for idx in range(4)
    ]
    display_images = [f"/v1/images/display-{idx}" for idx in range(4)]
    mixed_gallery = [*display_images, *[entry["image_url"] for entry in analysis_uploads]]
    db.insert_listing(
        listing_id="listing-with-display-and-analysis-images",
        owner_subject="api-key",
        owner_name="Local Tester",
        title="Gianvito Rossi Portofino Ankle Strap Sandal",
        mode="trade",
        category="shoes",
        brand="Gianvito Rossi",
        condition="LikeNew",
        size="Medium",
        estimated_value=650.0,
        city="Your area",
        image=mixed_gallery[0],
        images=mixed_gallery,
        description="Display gallery should not include analysis inputs",
        wants="Open to similar-value offers",
        tags=[],
        source_item_id="item-gallery-repair",
        analysis={"uploaded_images": analysis_uploads},
        status="Active",
    )

    changed = db.migrate_listing_media_urls_to_http()
    assert changed == 1

    list_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listing = next(item for item in list_res.json()["items"] if item["listing_id"] == "listing-with-display-and-analysis-images")
    assert listing["images"] == display_images
    assert len(listing["images"]) == 4


def test_photoroom_staging_uses_segment_api(monkeypatch) -> None:
    monkeypatch.setenv("PHOTOROOM_API_KEY", "photoroom-test-key")

    from app.main import _stage_item_image
    from app.settings import Settings

    captured: dict[str, object] = {}
    processed = io.BytesIO()
    Image.new("RGB", (16, 16), color="white").save(processed, format="JPEG")

    class StubResponse:
        status_code = 200
        content = processed.getvalue()

        def raise_for_status(self):
            return None

    class StubClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, data, files):
            captured["url"] = url
            captured["headers"] = headers
            captured["data"] = data
            captured["files"] = files
            return StubResponse()

    monkeypatch.setattr("app.main.httpx.Client", StubClient)
    raw = _make_image("PRODUCT")
    out, content_type, debug = _stage_item_image(
        raw,
        "image/jpeg",
        Settings(
            image_staging_enabled=True,
            image_staging_photoroom_enabled=True,
            image_staging_gemini_enabled=False,
            condition_rembg_enabled=False,
            photoroom_api_key="photoroom-test-key",
        ),
    )

    with Image.open(io.BytesIO(out)) as staged:
        assert staged.size == (16, 16)
    assert content_type == "image/jpeg"
    assert debug["provider"] == "photoroom_remove_background"
    assert debug["synthetic_shadow"] is False
    assert captured["url"] == "https://sdk.photoroom.com/v1/segment"
    assert captured["headers"] == {"x-api-key": "photoroom-test-key"}
    assert captured["data"]["format"] == "jpg"
    assert captured["data"]["bg_color"] == "#FFFFFF"
    assert captured["data"]["crop"] == "false"
    assert captured["data"]["despill"] == "false"
    assert "image_file" in captured["files"]


def test_gpt_profile_uses_retail_reference_as_low_confidence_resale_before_crawlers() -> None:
    from app.main import apply_gemini_grounded_retail_reference, valuation_from_gpt_item_profile

    profile = {
        "category": "shoes",
        "retail_price_estimate": {"estimated_price": None, "currency": "USD", "confidence": 0.5},
        "resale_price_estimate": {"estimated_price": None, "currency": "USD", "confidence": 0.5},
        "resale_price_breakdown": [],
    }
    debug: dict[str, object] = {}
    workflow = {
        "grounded_search": (
            'A comparable Chanel chain-link cap-toe ankle boot had a retail price of $1550. '
            "Direct resale comps for this exact model were limited."
        )
    }

    apply_gemini_grounded_retail_reference(profile, workflow, debug)
    valuation = valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade="New")

    assert profile["retail_price_estimate"]["estimated_price"] == 1550.0
    assert debug["retail_reference_extracted"]["applied"] is True
    assert valuation["estimated_value"] == 1240.0
    assert valuation["retail_reference_value"] == 1550.0
    assert valuation["confidence"] == 0.35
    assert valuation["basis"] == "gpt_retail_reference_resale_fallback"


def test_gpt_profile_uses_visual_condition_signals_for_retail_resale_fallback() -> None:
    from app.main import valuation_from_gpt_item_profile

    profile = {
        "category": "shoes",
        "visual_condition_assessment": {
            "wear_level": "pristine",
            "box_included": "yes",
            "dust_bag_included": "yes",
            "new_in_box_signal": "yes",
            "pricing_tier": "new_in_box",
            "confidence": 0.82,
            "evidence": ["Original branded box visible", "No visible sole wear"],
        },
        "retail_price_estimate": {"estimated_price": 1550, "currency": "USD", "confidence": 0.5},
        "resale_price_estimate": {"estimated_price": None, "currency": "USD", "confidence": 0.5},
        "resale_price_breakdown": [],
    }

    valuation = valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade="NewWithTags")

    assert valuation["estimated_value"] == 1609.52
    assert valuation["retail_reference_value"] == 1550.0
    assert valuation["basis"] == "gpt_retail_reference_resale_fallback"
    assert valuation["visual_condition_adjustment"]["applied"] is True
    assert valuation["visual_condition_adjustment"]["multiplier"] == 1.18
    assert "new_in_box_pricing_tier" in valuation["visual_condition_adjustment"]["reasons"]


def test_gpt_profile_does_not_apply_nib_visual_premium_for_plain_new() -> None:
    from app.main import valuation_from_gpt_item_profile

    profile = {
        "category": "shoes",
        "visual_condition_assessment": {
            "wear_level": "pristine",
            "box_included": "yes",
            "dust_bag_included": "yes",
            "new_in_box_signal": "yes",
            "pricing_tier": "new_in_box",
            "confidence": 0.82,
            "evidence": ["Original branded box visible", "No visible sole wear"],
        },
        "retail_price_estimate": {"estimated_price": 1550, "currency": "USD", "confidence": 0.5},
        "resale_price_estimate": {"estimated_price": None, "currency": "USD", "confidence": 0.5},
        "resale_price_breakdown": [],
    }

    valuation = valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade="New")

    assert valuation["estimated_value"] == 1240.0
    assert valuation["retail_reference_value"] == 1550.0
    assert valuation["basis"] == "gpt_retail_reference_resale_fallback"
    assert valuation["visual_condition_adjustment"] == {
        "applied": False,
        "reason": "user_condition_new_excludes_new_with_tags_nib_full_set_premium",
    }


def test_new_with_tags_condition_normalization_and_breakdown_selection() -> None:
    from app.main import normalize_condition_grade, valuation_from_gpt_item_profile

    assert normalize_condition_grade("New with Tags") == "NewWithTags"
    assert normalize_condition_grade("NWT") == "NewWithTags"

    profile = {
        "category": "clothes",
        "retail_price_estimate": {"estimated_price": 495, "currency": "USD", "confidence": 0.8},
        "resale_price_estimate": {"estimated_price": 135, "currency": "USD", "confidence": 0.7},
        "resale_price_breakdown": [
            {
                "label": "Without tags / excellent condition",
                "estimated_price": 75,
                "range_low": 60,
                "range_high": 90,
                "rationale": "Excellent used examples.",
            },
            {
                "label": "New with tags / brand new",
                "estimated_price": 210,
                "range_low": 180,
                "range_high": 240,
                "rationale": "NWT peer-to-peer comps.",
            },
            {
                "label": "Current-season style with MSRP context",
                "estimated_price": 260,
                "range_low": 225,
                "range_high": 300,
                "rationale": "Current-season style with MSRP around $495.",
            },
            {
                "label": "Original Retail Value",
                "estimated_price": 495,
                "range_low": 495,
                "range_high": 495,
                "rationale": "MSRP, not resale.",
            },
        ],
    }

    new_with_tags = valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade="NewWithTags")
    plain_new_profile = {
        **profile,
        "resale_price_estimate": {"estimated_price": None, "currency": "USD", "confidence": 0.7},
    }
    plain_new = valuation_from_gpt_item_profile(plain_new_profile, default_currency="USD", condition_grade="New")

    assert new_with_tags["estimated_value"] == 260.0
    assert new_with_tags["selected_breakdown_label"] == "Current-season style with MSRP context"
    assert plain_new["estimated_value"] == 75.0
    assert plain_new["selected_breakdown_label"] == "Without tags / excellent condition"


def test_plain_new_condition_ignores_nwt_breakdown_row_when_primary_missing() -> None:
    from app.main import valuation_from_gpt_item_profile

    profile = {
        "category": "shoes",
        "retail_price_estimate": {"estimated_price": 900, "currency": "USD", "confidence": 0.8},
        "resale_price_estimate": {"estimated_price": None, "currency": "USD", "confidence": 0.7},
        "resale_price_breakdown": [
            {
                "label": "NWT / New in box full set",
                "estimated_price": 560,
                "range_low": 520,
                "range_high": 600,
                "rationale": "NWT full-set examples with box and dust bag.",
            },
            {
                "label": "EUC / Like New",
                "estimated_price": 380,
                "range_low": 340,
                "range_high": 420,
                "rationale": "Clean peer-to-peer examples without tags or box premium.",
            },
        ],
    }

    valuation = valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade="New")

    assert valuation["estimated_value"] == 380.0
    assert valuation["selected_breakdown_label"] == "EUC / Like New"


def test_plain_new_condition_replaces_primary_nwt_framing_with_non_nwt_breakdown() -> None:
    from app.main import valuation_from_gpt_item_profile

    profile = {
        "category": "shoes",
        "retail_price_estimate": {"estimated_price": 900, "currency": "USD", "confidence": 0.8},
        "resale_price_estimate": {
            "estimated_price": 520,
            "currency": "USD",
            "confidence": 0.72,
            "condition_assumption": "NWT / new-in-box full set",
            "rationale": "The valuation uses new with tags and box/dust bag premium comps.",
        },
        "resale_price_breakdown": [
            {
                "label": "NWT / New in box full set",
                "estimated_price": 560,
                "range_low": 520,
                "range_high": 600,
                "rationale": "NWT full-set examples.",
            },
            {
                "label": "EUC / Like New",
                "estimated_price": 380,
                "range_low": 340,
                "range_high": 420,
                "rationale": "Clean examples without tags or full-set premium.",
            },
        ],
    }

    valuation = valuation_from_gpt_item_profile(profile, default_currency="USD", condition_grade="New")

    assert valuation["estimated_value"] == 380.0
    assert valuation["selected_breakdown_label"] == "EUC / Like New"


def test_analyze_skips_crawler_when_gemini_retail_reference_can_be_derived(monkeypatch) -> None:
    os.environ["GPT_ITEM_PROFILE_ENABLED"] = "true"
    client = _build_client()
    from app.deps import get_gpt_item_profiler, get_valuation_service
    from app.gpt_item_profile import GptItemProfileResult
    from app.main import app

    class StubGptProfiler:
        def profile_item(self, **kwargs):
            return GptItemProfileResult(
                profile={
                    "category": "shoes",
                    "candidate_brand": "Chanel",
                    "candidate_model": "Chanel Two-Tone Cap-Toe Ankle Boots with Chain Detail",
                    "confidence": 0.9,
                    "model_identification": {
                        "name": "Chanel Two-Tone Cap-Toe Ankle Boots with Chain Detail",
                        "confidence": 0.9,
                        "attributes": ["two-tone cap toe", "chain detail"],
                    },
                    "authenticity_screen": {
                        "verdict": "inconclusive",
                        "confidence": 0.6,
                        "reasons": [],
                        "required_checks": [],
                        "disclaimer": "screening only",
                    },
                    "visual_condition_assessment": {
                        "wear_level": "pristine",
                        "box_included": "yes",
                        "dust_bag_included": "yes",
                        "new_in_box_signal": "yes",
                        "pricing_tier": "new_in_box",
                        "confidence": 0.82,
                        "evidence": ["Original branded box visible", "No visible sole wear"],
                    },
                    "retail_price_estimate": {
                        "estimated_price": None,
                        "currency": "USD",
                        "confidence": 0.5,
                        "rationale": "",
                        "references": [],
                    },
                    "resale_price_estimate": {
                        "estimated_price": None,
                        "currency": "USD",
                        "confidence": 0.5,
                        "rationale": "",
                        "condition_assumption": "New",
                        "references": [],
                    },
                    "resale_price_breakdown": [],
                    "_workflow": {
                        "grounded_search": "A comparable Chanel chain-link ankle boot had a retail price of $1550."
                    },
                },
                enabled=True,
                called=True,
            )

    class FailingValuationService:
        def evaluate(self, *args, **kwargs):
            raise AssertionError("Crawler valuation should not run when Gemini retail fallback is available")

        @staticmethod
        def serialize(result):
            raise AssertionError("Crawler valuation should not run when Gemini retail fallback is available")

    app.dependency_overrides[get_gpt_item_profiler] = lambda: StubGptProfiler()
    app.dependency_overrides[get_valuation_service] = lambda: FailingValuationService()
    try:
        res = client.post(
            "/v1/analyze",
            data={"user_condition": "New", "item_size": "US 8", "debug": "true"},
            files=[("images", ("boots.jpg", _make_image("CHANEL"), "image/jpeg"))],
            headers={"x-api-key": "test-key"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["valuation"]["estimated_value"] == 1240.0
        assert body["valuation"]["visual_condition_adjustment"]["applied"] is False
        assert body["valuation"]["retail_reference_value"] == 1550.0
        assert body["valuation"]["basis"] == "gpt_retail_reference_resale_fallback"
        assert body["debug"]["enrichment"]["gpt_item_profile"]["retail_reference_extracted"]["applied"] is True
        assert body["debug"]["valuation"]["pricing_source"] == "gpt_primary"
        assert body["debug"]["valuation"]["pricing_fallback_used"] is False
    finally:
        app.dependency_overrides.clear()


def test_analyze_uses_original_upload_bytes_for_item_profile(monkeypatch) -> None:
    os.environ["GPT_ITEM_PROFILE_ENABLED"] = "true"
    client = _build_client()
    from app.deps import get_gpt_item_profiler
    from app.gpt_item_profile import GptItemProfileResult
    from app.main import app

    original = _make_image("ORIGINAL")
    captured: dict[str, object] = {}

    def fake_stage_item_image(raw, content_type, settings):
        raise AssertionError("PhotoRoom/background staging should not run before item analysis")

    class StubGptProfiler:
        def profile_item(self, **kwargs):
            images = kwargs["images"]
            captured["analysis_bytes"] = images[0].bytes_data
            captured["analysis_content_type"] = images[0].content_type
            return GptItemProfileResult(
                profile={
                    "category": "handbag",
                    "brand": {"name": "Chanel", "confidence": 0.8},
                    "model_identification": {"name": "Classic Flap", "confidence": 0.8, "attributes": []},
                    "authenticity_screen": {
                        "verdict": "inconclusive",
                        "confidence": 0.6,
                        "reasons": [],
                        "required_checks": [],
                        "disclaimer": "screening only",
                    },
                    "resale_price_estimate": {
                        "estimated_price": 800,
                        "currency": "USD",
                        "confidence": 0.7,
                        "rationale": "stub",
                        "condition_assumption": "LikeNew",
                        "references": [],
                    },
                },
                enabled=True,
                called=True,
            )

    monkeypatch.setattr("app.main._stage_item_image", fake_stage_item_image)
    app.dependency_overrides[get_gpt_item_profiler] = lambda: StubGptProfiler()
    try:
        res = client.post(
            "/v1/analyze",
            data={"debug": "true"},
            files=[("images", ("product.jpg", original, "image/jpeg"))],
            headers={"x-api-key": "test-key"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["uploaded_images"][0]["storage_uri"].endswith(".jpg")
        assert captured["analysis_bytes"] == original
        assert captured["analysis_content_type"] == "image/jpeg"
        assert body["debug"]["uploads"][0]["staging"]["provider"] == "exif_orientation"
        assert body["debug"]["uploads"][0]["staging"]["background_staging"] == "deferred"
        assert body["debug"]["uploads"][0]["analysis_source"] == "original_upload"
    finally:
        app.dependency_overrides.clear()


def test_analyze_unknown_brand_requests_more_photos() -> None:
    client = _build_client()
    _override_gpt_profiler(None)
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
    assert body["requested_photos"] == []
    assert body["item_profile"] is None


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
                grade="LikeNew",
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
        assert body["condition"]["grade"] == "LikeNew"
        assert body["warnings"] == []
    finally:
        app.dependency_overrides.clear()


def test_user_condition_drives_valuation_before_model_is_trusted() -> None:
    client = _build_client()
    _override_gpt_profiler(_stub_item_profile())
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
    assert body["condition"]["grade"] in {"New", "LikeNew"}
    assert body["valuation"] is not None
    assert body["debug"]["valuation"]["condition_source"] == "user_input"
    assert body["debug"]["valuation"]["condition_grade_used"] == "New"


def test_gpt_pricing_is_used_as_primary_when_available() -> None:
    os.environ["VALUATION_PROVIDERS"] = "stub"
    client = _build_client()
    from app.deps import get_gpt_item_profiler, get_valuation_service
    from app.main import app
    from app.gpt_item_profile import GptItemProfileResult

    class StubGptProfiler:
        def profile_item(self, **kwargs):
            return GptItemProfileResult(
                profile=_stub_item_profile(model="Test Model", estimated_price=700),
                enabled=True,
                called=True,
            )

    class FailIfCalledValuationService:
        def evaluate(self, request, debug=False):
            raise AssertionError("Crawler valuation should not be called when GPT price is available")

        @staticmethod
        def serialize(result):
            return {}

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
    os.environ["VALUATION_COMPS_ENABLED"] = "true"
    client = _build_client()
    from app.deps import get_gpt_item_profiler, get_valuation_service
    from app.main import app
    from app.gpt_item_profile import GptItemProfileResult
    from valuation.types import ValuationResult

    class StubGptProfilerNoPrice:
        def profile_item(self, **kwargs):
            return GptItemProfileResult(
                profile=_stub_item_profile(model="Test Model", estimated_price=None),
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
        os.environ["VALUATION_COMPS_ENABLED"] = "false"


def test_create_and_list_listing_with_api_key() -> None:
    client = _build_client()
    create_payload = {
        "title": "Jimmy Choo Rosalia 50 Slingback Pump",
        "mode": "trade",
        "category": "shoes",
        "brand": "Jimmy Choo",
        "condition": "LikeNew",
        "estimated_value": 425.0,
        "city": "New York, NY",
        "image": "https://example.test/image.jpg",
        "wants": "Open to similar-value offers",
        "tags": ["LikeNew", "Jimmy Choo", "trade"],
        "source_item_id": "item-abc",
        "analysis": {"item_id": "item-abc"},
        "status": "Active",
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


def test_marketplace_matches_exclude_same_owner_listings() -> None:
    client = _build_client()
    base_payload = {
        "mode": "trade",
        "category": "handbag",
        "brand": "Jouft",
        "condition": "LikeNew",
        "city": "New York, NY",
        "wants": "Open to similar-value offers",
        "status": "Active",
    }

    first_res = client.post(
        "/v1/listings",
        json={
            **base_payload,
            "title": "Same Owner Tote",
            "estimated_value": 500.0,
            "image": "https://example.test/tote.jpg",
        },
        headers={"x-api-key": "test-key"},
    )
    second_res = client.post(
        "/v1/listings",
        json={
            **base_payload,
            "title": "Same Owner Bag",
            "estimated_value": 525.0,
            "image": "https://example.test/bag.jpg",
        },
        headers={"x-api-key": "test-key"},
    )
    assert first_res.status_code == 200, first_res.text
    assert second_res.status_code == 200, second_res.text

    list_res = client.get("/v1/listings?limit=10&include_matches=true", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    items = list_res.json()["items"]
    created_ids = {first_res.json()["listing_id"], second_res.json()["listing_id"]}
    listed = [item for item in items if item["listing_id"] in created_ids]
    assert len(listed) == 2
    assert all(item["matches"] == [] for item in listed)


def test_marketplace_matches_allow_same_display_name_with_different_owner_subjects() -> None:
    client = _build_client()
    from app import deps

    db = deps.get_db()
    db.insert_listing(
        listing_id="viewer-active-bag",
        owner_subject="api-key",
        owner_name="Rajesh Volluru",
        title="Viewer Active Bag",
        mode="trade",
        category="handbag",
        brand="Louis Vuitton",
        condition="LikeNew",
        size="Medium",
        estimated_value=1000.0,
        city="New York, NY",
        image="https://example.test/viewer.jpg",
        images=["https://example.test/viewer.jpg"],
        description="Viewer closet item.",
        wants="Open to similar-value offers",
        tags=[],
        source_item_id="item-viewer",
        analysis={"item_id": "item-viewer"},
        status="Active",
    )
    db.insert_listing(
        listing_id="other-active-bag-same-name",
        owner_subject="other-user",
        owner_name="Rajesh Volluru",
        title="Other Active Bag Same Name",
        mode="trade",
        category="handbag",
        brand="Louis Vuitton",
        condition="LikeNew",
        size="Medium",
        estimated_value=1030.0,
        city="New York, NY",
        image="https://example.test/other.jpg",
        images=["https://example.test/other.jpg"],
        description="Other user marketplace item.",
        wants="Open to similar-value offers",
        tags=[],
        source_item_id="item-other",
        analysis={"item_id": "item-other"},
        status="Active",
    )

    list_res = client.get("/v1/listings?limit=10&include_matches=true", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    other = next(item for item in list_res.json()["items"] if item["listing_id"] == "other-active-bag-same-name")
    assert [match["listing_id"] for match in other["matches"]] == ["viewer-active-bag"]


def test_trade_match_agent_generates_persisted_optional_matches() -> None:
    client = _build_client()
    from app import deps

    db = deps.get_db()
    db.insert_listing(
        listing_id="other-active-bag",
        owner_subject="other-user",
        owner_name="Other User",
        title="Other Active Bag",
        mode="trade",
        category="handbag",
        brand="Chanel",
        condition="LikeNew",
        size=None,
        estimated_value=1000.0,
        city="New York, NY",
        image="https://example.test/other.jpg",
        images=["https://example.test/other.jpg"],
        description="Target listing",
        wants="Open to similar-value offers",
        tags=[],
        source_item_id=None,
        analysis=None,
        status="Active",
    )
    own_res = client.post(
        "/v1/listings",
        json={
            "title": "My Active Bag",
            "mode": "trade",
            "category": "handbag",
            "brand": "Louis Vuitton",
            "condition": "LikeNew",
            "estimated_value": 950.0,
            "city": "New York, NY",
            "image": "https://example.test/mine.jpg",
            "images": ["https://example.test/mine.jpg"],
            "wants": "Open to similar-value offers",
            "status": "Active",
        },
        headers={"x-api-key": "test-key"},
    )
    assert own_res.status_code == 200, own_res.text

    run_res = client.post("/v1/trade-match-agent/run?limit=10", headers={"x-api-key": "test-key"})
    assert run_res.status_code == 200, run_res.text
    body = run_res.json()
    assert body["generated_count"] == 1
    match = body["items"][0]
    assert match["target_listing_id"] == "other-active-bag"
    assert match["candidate_listing_id"] == own_res.json()["listing_id"]
    assert match["status"] == "suggested"
    assert match["target_listing"]["title"] == "Other Active Bag"
    assert match["candidate_listing"]["title"] == "My Active Bag"

    list_res = client.get("/v1/trade-match-agent/matches", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    assert list_res.json()["count"] == 1

    dismiss_res = client.patch(
        f"/v1/trade-match-agent/matches/{match['match_id']}",
        json={"status": "dismissed"},
        headers={"x-api-key": "test-key"},
    )
    assert dismiss_res.status_code == 200, dismiss_res.text
    assert dismiss_res.json()["status"] == "dismissed"

    suggested_res = client.get("/v1/trade-match-agent/matches", headers={"x-api-key": "test-key"})
    assert suggested_res.status_code == 200, suggested_res.text
    assert suggested_res.json()["count"] == 0


def test_create_listing_recovers_images_from_analysis_uploads() -> None:
    client = _build_client()
    create_payload = {
        "title": "Mobile Uploaded Listing",
        "mode": "trade",
        "category": "handbag",
        "brand": "Jouft",
        "condition": "LikeNew",
        "estimated_value": 225.0,
        "city": "New York, NY",
        "image": "file:///private/var/mobile/local-photo.jpg",
        "images": ["file:///private/var/mobile/local-photo.jpg"],
        "analysis": {
            "item_id": "item-mobile-upload",
            "uploaded_images": [
                {"image_url": "/v1/images/mobile-upload-1"},
                {"image_url": "/v1/images/mobile-upload-2"},
            ],
        },
        "status": "Active",
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["image"] == "/v1/images/mobile-upload-1"
    assert created["images"] == ["/v1/images/mobile-upload-1", "/v1/images/mobile-upload-2"]

    list_res = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listed = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listed["image"].endswith("/v1/images/mobile-upload-1")
    assert listed["images"][0].endswith("/v1/images/mobile-upload-1")


def test_listing_media_normalizes_raw_alb_image_urls() -> None:
    client = _build_client()
    raw_alb_url = "https://valueai-mvp-alb-103817159.us-east-1.elb.amazonaws.com/v1/images/4103cfb0-1239-4e60-af3c-0b5c69eb015b"
    create_payload = {
        "title": "Legacy ALB Image Listing",
        "mode": "trade",
        "category": "handbag",
        "brand": "Jouft",
        "condition": "LikeNew",
        "estimated_value": 225.0,
        "city": "New York, NY",
        "image": raw_alb_url,
        "images": [raw_alb_url],
        "status": "Active",
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["image"] == "/v1/images/4103cfb0-1239-4e60-af3c-0b5c69eb015b"
    assert created["images"] == ["/v1/images/4103cfb0-1239-4e60-af3c-0b5c69eb015b"]

    list_res = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listed = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listed["image"] == "/v1/images/4103cfb0-1239-4e60-af3c-0b5c69eb015b"
    assert listed["images"] == ["/v1/images/4103cfb0-1239-4e60-af3c-0b5c69eb015b"]


def test_listing_media_dedupes_absolute_and_relative_api_image_urls() -> None:
    client = _build_client()
    create_payload = {
        "title": "Duplicate Absolute Relative Listing",
        "mode": "trade",
        "category": "handbag",
        "brand": "Chanel",
        "condition": "LikeNew",
        "estimated_value": 225.0,
        "city": "New York, NY",
        "image": "https://www.jouft.com/v1/images/image-one",
        "images": [
            "https://www.jouft.com/v1/images/image-one",
            "https://api.jouft.com/v1/images/image-two",
            "/v1/images/image-one",
            "/v1/images/image-two",
        ],
        "status": "Active",
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["image"] == "/v1/images/image-one"
    assert created["images"] == ["/v1/images/image-one", "/v1/images/image-two"]

    list_res = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listed = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listed["images"] == ["/v1/images/image-one", "/v1/images/image-two"]


def test_create_listing_does_not_append_analysis_uploads_to_display_gallery() -> None:
    client = _build_client()
    display_images = [
        "/v1/images/photoroom-front",
        "/v1/images/photoroom-side",
        "/v1/images/photoroom-sole",
    ]
    create_payload = {
        "title": "Three Photo Boots",
        "mode": "trade",
        "category": "shoes",
        "brand": "Chanel",
        "condition": "NewWithTags",
        "estimated_value": 1495.0,
        "city": "New York, NY",
        "image": display_images[0],
        "images": display_images,
        "analysis": {
            "uploaded_images": [
                {"image_url": "/v1/images/original-front"},
                {"image_url": "/v1/images/original-side"},
                {"image_url": "/v1/images/original-sole"},
            ],
        },
        "status": "Active",
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["images"] == display_images

    list_res = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listed = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listed["images"] == display_images


def test_create_listing_stores_listed_image_pairs() -> None:
    client = _build_client()
    create_payload = {
        "title": "Paired Image Listing",
        "mode": "trade",
        "category": "shoes",
        "brand": "Chanel",
        "condition": "NewWithTags",
        "estimated_value": 1495.0,
        "city": "New York, NY",
        "image": "/v1/images/processed-front",
        "images": ["/v1/images/processed-front", "/v1/images/processed-side"],
        "listed_images": [
            {"p_img": "/v1/images/original-front", "d_img": "/v1/images/processed-front", "is_hero": True},
            {"p_img": "/v1/images/original-side", "d_img": "/v1/images/processed-side"},
        ],
        "status": "Active",
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["image"] == "/v1/images/processed-front"
    assert created["images"] == ["/v1/images/processed-front", "/v1/images/processed-side"]
    assert created["listed_images"] == [
        {"p_img": "/v1/images/original-front", "d_img": "/v1/images/processed-front", "is_hero": True},
        {"p_img": "/v1/images/original-side", "d_img": "/v1/images/processed-side", "is_hero": False},
    ]

    list_res = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listed = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listed["images"] == ["/v1/images/processed-front", "/v1/images/processed-side"]
    assert listed["listed_images"][0]["p_img"] == "/v1/images/original-front"
    assert listed["listed_images"][0]["d_img"] == "/v1/images/processed-front"
    assert listed["listed_images"][0]["is_hero"] is True


def test_listing_media_dedupes_upload_url_variants_to_image_ids() -> None:
    client = _build_client()
    files = [
        ("images", ("boots-front.jpg", _make_image("FRONT"), "image/jpeg")),
        ("images", ("boots-side.jpg", _make_image("SIDE"), "image/jpeg")),
    ]
    upload_res = client.post(
        "/v1/uploads/images",
        data={"item_id": "item-duplicate-upload-urls"},
        files=files,
        headers={"x-api-key": "test-key"},
    )
    assert upload_res.status_code == 200, upload_res.text
    uploaded = upload_res.json()["uploaded_images"]
    first_url = uploaded[0]["image_url"]
    second_url = uploaded[1]["image_url"]
    first_upload_path = uploaded[0]["storage_uri"].replace(".data/uploads/", "/uploads/", 1)
    second_upload_path = uploaded[1]["storage_uri"].replace(".data/uploads/", "/uploads/", 1)

    create_payload = {
        "title": "Duplicate Upload URL Listing",
        "mode": "trade",
        "category": "shoes",
        "brand": "Chanel",
        "condition": "LikeNew",
        "estimated_value": 1200.0,
        "city": "New York, NY",
        "image": f"http://127.0.0.1:8000{first_upload_path}",
        "images": [
            f"http://127.0.0.1:8000{first_upload_path}",
            f"http://127.0.0.1:8000{second_upload_path}",
            first_upload_path,
            second_upload_path,
            first_url,
            second_url,
        ],
        "source_item_id": "item-duplicate-upload-urls",
        "status": "Active",
    }

    create_res = client.post("/v1/listings", json=create_payload, headers={"x-api-key": "test-key"})
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    assert created["image"] == first_url
    assert created["images"] == [first_url, second_url]

    list_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert list_res.status_code == 200, list_res.text
    listed = next(item for item in list_res.json()["items"] if item["listing_id"] == created["listing_id"])
    assert listed["image"] == first_url
    assert listed["images"] == [first_url, second_url]


def test_marketplace_lists_only_active_but_mine_includes_review() -> None:
    client = _build_client()
    review_payload = {
        "title": "Review Queue Dress",
        "mode": "trade",
        "category": "clothes",
        "brand": "Jouft",
        "condition": "LikeNew",
        "estimated_value": 125.0,
        "city": "New York, NY",
        "image": "https://example.test/review.jpg",
        "status": "Review",
    }
    active_payload = {
        **review_payload,
        "title": "Active Marketplace Dress",
        "image": "https://example.test/active.jpg",
        "status": "Active",
    }

    review_res = client.post("/v1/listings", json=review_payload, headers={"x-api-key": "test-key"})
    active_res = client.post("/v1/listings", json=active_payload, headers={"x-api-key": "test-key"})
    assert review_res.status_code == 200, review_res.text
    assert active_res.status_code == 200, active_res.text
    review_id = review_res.json()["listing_id"]
    active_id = active_res.json()["listing_id"]

    market_res = client.get("/v1/listings?limit=10", headers={"x-api-key": "test-key"})
    assert market_res.status_code == 200, market_res.text
    market_ids = {item["listing_id"] for item in market_res.json()["items"]}
    assert active_id in market_ids
    assert review_id not in market_ids

    mine_res = client.get("/v1/listings?mine=true&limit=10", headers={"x-api-key": "test-key"})
    assert mine_res.status_code == 200, mine_res.text
    mine_ids = {item["listing_id"] for item in mine_res.json()["items"]}
    assert active_id in mine_ids
    assert review_id in mine_ids
