import asyncio
import base64
import io

import pytest
from PIL import Image

from app.mannequin_fidelity import generation_parts, review_passes, select_product_views, validate_plan


def plan():
    return {"sufficient_evidence": True, "views": ["label", "front", "back"],
            "reference_indices": [1, 2], "constraints": ["Bare shoulder", "Zipper continues to hem"],
            "requires_human_review": True}


def test_selects_front_over_mislabeled_label():
    assert validate_plan(plan(), 3)["reference_indices"] == [1, 2]


def test_all_original_views_including_label_are_sent_with_explicit_authority():
    parts = generation_parts([{"data": view.encode(), "_fidelity_view": view}
                              for view in ["front", "back", "label"]], "Preserve zipper")
    images = [part for part in parts if "inline_data" in part]
    assert len(images) == 3
    assert [base64.b64decode(part["inline_data"]["data"]) for part in images] == [b"front", b"back", b"label"]
    assert "Authoritative construction evidence" in parts[0]["text"]
    assert "Supporting label/text evidence only" in parts[4]["text"]


def test_live_gemini_label_selection_is_filtered_and_front_ordered():
    selected = select_product_views({**plan(), "reference_indices": [2, 1, 0]}, 3)
    assert selected["reference_indices"] == [1, 2]
    assert selected["model_reference_indices"] == [2, 1, 0]
    with pytest.raises(ValueError):
        select_product_views({**plan(), "reference_indices": [0]}, 3)


@pytest.mark.parametrize("change", [
    {"reference_indices": [0]}, {"reference_indices": [1, 3]}, {"reference_indices": [True]},
    {"reference_indices": [1, 1]}, {"sufficient_evidence": False}, {"constraints": []},
    {"requires_human_review": "false"}, {"views": ["front"]},
    {"reference_indices": [2, 1]}, {"reference_indices": [1, 0]},
])
def test_invalid_or_insufficient_plans_fail_closed(change):
    with pytest.raises(ValueError):
        validate_plan({**plan(), **change}, 3)


def review():
    return {"verdict": "passed", "additional_changes": [], "checks": [
        {"constraint_index": 0, "result": "matched", "evidence": "Shoulder remains exposed"},
        {"constraint_index": 1, "result": "matched", "evidence": "Zipper reaches the hem"},
    ]}


def test_review_requires_every_constraint_and_no_added_details():
    assert review_passes(review(), 2)
    for result in ("changed", "uncertain"):
        candidate = review()
        candidate["checks"][1]["result"] = result
        assert not review_passes(candidate, 2)
    assert not review_passes({**review(), "additional_changes": ["Added collar band"]}, 2)
    assert not review_passes({**review(), "checks": review()["checks"][:1]}, 2)
    assert not review_passes({**review(), "checks": [review()["checks"][0]] * 2}, 2)
    assert not review_passes({}, 2)


def test_asymmetric_source_generates_owner_review_preview(monkeypatch):
    from app import main
    from app.settings import Settings
    from app import mannequin_fidelity

    async def inspect(**kwargs):
        return {**plan(), "views": ["front"], "reference_indices": [0]}

    async def generate(**kwargs):
        assert kwargs["plan"]["requires_human_review"] is True
        assert "Bare shoulder" in kwargs["prompt"]
        return {"review_decision": "pending"}

    monkeypatch.setattr(mannequin_fidelity, "plan_references", inspect)
    monkeypatch.setattr(main, "_generate_verified_mannequin_asset", generate)
    result = asyncio.run(main._generate_mannequin_listing_asset(
        files=[{"data": b"original", "content_type": "image/jpeg"}], category="clothes",
        title="One shoulder dress", description="", item_id="test",
        settings=Settings(gemini_api_key="test", mannequin_image_generation_enabled=True),
        db=None, storage=None,
    ))
    assert result == {"review_decision": "pending"}


def test_pipeline_sends_all_originals_with_front_first_and_label_supporting(monkeypatch):
    from app import main, mannequin_fidelity
    from app.settings import Settings

    async def inspect(**kwargs):
        assert len(kwargs["files"]) == 3
        return plan()

    async def generate(**kwargs):
        assert [entry["data"] for entry in kwargs["reference_files"]] == [b"front", b"back", b"label"]
        assert [entry["_fidelity_view"] for entry in kwargs["reference_files"]] == ["front", "back", "label"]
        return {"review_decision": "pending"}

    monkeypatch.setattr(mannequin_fidelity, "plan_references", inspect)
    monkeypatch.setattr(main, "_generate_verified_mannequin_asset", generate)
    result = asyncio.run(main._generate_mannequin_listing_asset(
        files=[{"data": view.encode()} for view in ["label", "front", "back"]], category="clothes",
        title="Olive dress", description="", item_id="test",
        settings=Settings(gemini_api_key="test", mannequin_image_generation_enabled=True), db=None, storage=None,
    ))
    assert result["review_decision"] == "pending"


@pytest.mark.parametrize("outcome", ["changed", "uncertain", "unavailable"])
def test_flagged_candidate_is_saved_only_as_pending_owner_preview(monkeypatch, outcome):
    from app import main, mannequin_fidelity
    from app.settings import Settings

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="PNG")
    raw = buffer.getvalue()

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"inlineData": {
                "data": base64.b64encode(raw).decode(), "mimeType": "image/png",
            }}]}}]}

    class Client:
        async def post(self, *args, **kwargs):
            return Response()

    class Storage:
        def save_upload(self, **kwargs):
            return "test-preview.png"

        def save_debug_artifact(self, **kwargs):
            pass

    class Database:
        def insert_image(self, image):
            assert image.role_hint == "ai_mannequin"

    async def inspect(**kwargs):
        if outcome == "unavailable":
            raise TimeoutError("Diagnostic review timed out")
        result = review()
        result["checks"][1]["result"] = outcome
        return result

    monkeypatch.setattr(mannequin_fidelity, "review_candidate", inspect)
    result = asyncio.run(main._generate_verified_mannequin_asset(
        client=Client(), reference_files=[{"data": b"original"}], all_files=[{"data": b"original"}],
        plan={**plan(), "reference_indices": [0]}, prompt="preserve", model="generator", fidelity_model="reviewer",
        endpoint="https://example.test", asset_kind="mannequin_dress", category="clothes", item_id="test",
        settings=Settings(gemini_api_key="test"), db=Database(), storage=Storage(),
    ))
    assert result["review_decision"] == "pending"
    assert result["fidelity_passed"] is False
