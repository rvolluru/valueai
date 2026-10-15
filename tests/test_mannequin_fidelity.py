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
        assert "Technical product specification" not in kwargs["prompt"]
        assert kwargs["model"] == "gemini-3-pro-image"
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


def test_pipeline_generates_from_front_only_but_keeps_all_originals_for_review(monkeypatch):
    from app import main, mannequin_fidelity
    from app.settings import Settings

    async def inspect(**kwargs):
        assert len(kwargs["files"]) == 3
        return plan()

    async def generate(**kwargs):
        assert [entry["data"] for entry in kwargs["reference_files"]] == [b"front"]
        assert [entry["_fidelity_view"] for entry in kwargs["reference_files"]] == ["front"]
        assert [entry["data"] for entry in kwargs["all_files"]] == [b"label", b"front", b"back"]
        assert kwargs["plan"]["constraints"] == plan()["constraints"]
        return {"review_decision": "pending"}

    monkeypatch.setattr(mannequin_fidelity, "plan_references", inspect)
    monkeypatch.setattr(main, "_generate_verified_mannequin_asset", generate)
    result = asyncio.run(main._generate_mannequin_listing_asset(
        files=[{"data": view.encode()} for view in ["label", "front", "back"]], category="clothes",
        title="Olive dress", description="", item_id="test",
        settings=Settings(gemini_api_key="test", mannequin_image_generation_enabled=True), db=None, storage=None,
    ))
    assert result["review_decision"] == "pending"


@pytest.mark.parametrize("outcome", ["changed", "uncertain", "unavailable", "underdressed", "bottom_fallback"])
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
            assert kwargs["headers"] == {"x-goog-api-key": "test"}
            assert "key" not in kwargs.get("params", {})
            return Response()

    class Storage:
        def save_upload(self, **kwargs):
            assert outcome not in {"unavailable", "underdressed"}, "Unsafe preview must not be persisted"
            return "test-preview.png"

        def save_debug_artifact(self, **kwargs):
            pass

    class Database:
        def insert_image(self, image):
            assert image.role_hint == "ai_mannequin"

    review_modes = []
    async def inspect(**kwargs):
        review_modes.append(kwargs["display_mode"])
        if outcome == "unavailable":
            raise TimeoutError("Diagnostic review timed out")
        result = review()
        rejected = outcome == "underdressed" or (outcome == "bottom_fallback" and kwargs["display_mode"] != "lower_body")
        result["clothing_coverage"] = {"verdict": "failed" if rejected else "passed",
                                       "evidence": "Visible clothing coverage inspected"}
        result["checks"][1]["result"] = "matched" if outcome in {"underdressed", "bottom_fallback"} else outcome
        return result

    monkeypatch.setattr(mannequin_fidelity, "review_candidate", inspect)
    result = asyncio.run(main._generate_verified_mannequin_asset(
        client=Client(), reference_files=[{"data": b"original"}], all_files=[{"data": b"original"}],
        plan={**plan(), "reference_indices": [0]}, prompt="preserve", model="generator", fidelity_model="reviewer",
        endpoint="https://example.test", asset_kind="mannequin_bottom" if outcome == "bottom_fallback" else "mannequin_dress", category="clothes", item_id="test",
        settings=Settings(gemini_api_key="test"), db=Database(), storage=Storage(),
    ))
    if outcome in {"unavailable", "underdressed"}:
        assert result is None
        return
    assert result["review_decision"] == "pending"
    if outcome == "bottom_fallback":
        assert review_modes == ["full", "full", "lower_body"]
        assert result["display_mode"] == "lower_body"
        assert result["clothing_attempt"] == 3
        return
    assert result["fidelity_passed"] is False


@pytest.mark.parametrize("title,required,forbidden", [
    ("Silk blouse", "Dress the lower body", "Do not add unnecessary layers"),
    ("Wool blazer", "neutral underlayer", "Do not add unnecessary layers"),
    ("One-shoulder dress", "Do not add unnecessary layers", "Dress the lower body"),
    ("Utility jumpsuit", "Do not add unnecessary layers", "Dress the lower body"),
    ("Pleated skirt", "neutral top covering", "Dress the lower body"),
    ("Tous Les Jours Rayla Shorts", "Never show a bare upper torso", "Dress the lower body"),
    ("Tweed shorts", "covers the chest", "Dress the lower body"),
    ("Halter top", "Dress the lower body", "Do not add unnecessary layers"),
])
def test_category_specific_supporting_clothing(title, required, forbidden):
    from app.main import _mannequin_generation_prompt
    _, prompt = _mannequin_generation_prompt(category="clothes", title=title, description="Pairs with a dress")
    assert required in prompt
    assert forbidden not in prompt
    if "shorts" not in title.lower() and "skirt" not in title.lower():
        assert "Preserve intentional bare shoulders" in prompt
    assert "must not obscure, extend or alter" in prompt


def test_bag_is_fully_dressed_in_contrast_without_inventing_straps():
    from app.main import _mannequin_generation_prompt
    _, prompt = _mannequin_generation_prompt(category="handbag", title="Black clutch", description="")
    assert "Fully dress" in prompt
    assert "top and trousers or skirt" in prompt
    assert "clearly contrast" in prompt
    assert "light neutral clothing for dark bags" in prompt
    assert "dark neutral clothing for light bags" in prompt
    assert "do not invent a shoulder strap" in prompt


@pytest.mark.parametrize("coverage", [None, {}, {"verdict": "passed"},
    {"verdict": "failed", "evidence": "Bare chest"}, {"verdict": "uncertain", "evidence": "Obscured"}])
def test_clothing_coverage_requires_explicit_verified_evidence(coverage):
    from app.mannequin_fidelity import coverage_passes
    assert not coverage_passes({"clothing_coverage": coverage})


def test_bottom_attempts_prioritize_a_top_then_fall_back_to_lower_body():
    from app.main import _mannequin_generation_prompt
    from app.mannequin_fidelity import clothing_attempts
    kind, prompt = _mannequin_generation_prompt(category="clothes", title="Rayla Shorts", description="")
    attempts = clothing_attempts(prompt, kind)
    assert kind == "mannequin_bottom"
    assert [mode for _, mode, _ in attempts] == ["full", "full", "lower_body"]
    assert prompt.startswith("Create a TWO-PIECE dressed outfit")
    assert "Preserve intentional bare shoulders" not in prompt
    assert "CORRECTIVE RETRY" in attempts[1][2]
    assert "no upper torso" in attempts[2][2]
    assert "entire waistband" in attempts[2][2]
    assert len(clothing_attempts("dress", "mannequin_dress")) == 1
