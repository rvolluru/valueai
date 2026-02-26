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
