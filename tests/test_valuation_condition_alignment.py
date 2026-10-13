import pytest
import asyncio
from app.main import retry_new_condition_pricing

from app.main import _pricing_condition_label, valuation_from_gpt_item_profile
from app.gpt_item_profile import GptItemProfiler


def test_normalizers_preserve_structured_condition():
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    value = {"condition_grade": "New", "estimated_price": 220, "label": "New"}
    assert profiler._normalize_price_estimate(value)["condition_grade"] == "New"
    assert profiler._normalize_resale_price_breakdown([value], fallback=None)[0]["condition_grade"] == "New"


def test_retry_prompt_uses_reference_without_fixed_uplift(monkeypatch):
    profiler = GptItemProfiler.__new__(GptItemProfiler)
    profiler.openai_api_key = "test"
    captured = {}
    def call(**kwargs):
        captured.update(kwargs)
        return None
    monkeypatch.setattr(profiler, "_call_openai_valuation", call)
    profiler.estimate_new_from_like_new(item_profile={"model_name": "dress"}, reference={"estimated_price": 150})
    assert captured["condition_grade"] == "New"
    assert "do not apply a fixed" in captured["valuation_prompt_override"]
    assert "150" in captured["valuation_prompt_override"]


@pytest.mark.parametrize("response,status", [
    ({"condition_grade": "New", "estimated_price": 240, "currency": "USD", "confidence": .9}, "estimated"),
    ({"condition_grade": "LikeNew", "estimated_price": 200}, "unavailable"),
    ({"condition_grade": "New", "estimated_price": None}, "unavailable"),
    ({"condition_grade": "New", "estimated_price": 240, "currency": "EUR"}, "unavailable"),
])
def test_new_pricing_retry_validates_response(response, status):
    class Profiler:
        def estimate_new_from_like_new(self, **kwargs):
            assert kwargs["reference"]["condition_grade"] == "LikeNew"
            return {"resale_price_estimate": response}
    data = profile(rows=[{"label": "EUC", "condition_grade": "LikeNew", "estimated_price": 200, "currency": "USD"}])
    debug = {}
    asyncio.run(retry_new_condition_pricing(data, Profiler(), debug))
    assert debug["condition_pricing_retry"]["status"] == status
    if status == "estimated":
        assert data["resale_price_estimate"]["confidence"] == .2
        assert data["condition_pricing_provenance"]["reference"]["estimated_price"] == 200
    else:
        assert data["resale_price_estimate"]["condition_grade"] == "LikeNew"


def test_new_pricing_retry_skips_existing_new_band():
    data = profile(rows=[{"label": "New", "estimated_price": 220}])
    debug = {}
    asyncio.run(retry_new_condition_pricing(data, object(), debug))
    assert debug == {}


@pytest.mark.parametrize("text", ["New (not NWT)", "New; no full‑set/NWT uplift applied", "New; does not include NWT premium"])
def test_negated_tag_premium_is_still_new(text):
    assert _pricing_condition_label(text) == "New"


@pytest.mark.parametrize("label,expected", [
    ("LikeNew", "LikeNew"), ("EUC / Like New", "LikeNew"),
    ("New without tags", "New"), ("Unworn", "New"),
    ("NWT / New in box full set", "NewWithTags"),
    ("Current-season style with MSRP context", ""), ("Pristine", ""),
    ("New or Like New", "Ambiguous"), ("Used, not new", ""),
])
def test_condition_labels_are_unambiguous(label, expected):
    assert _pricing_condition_label(label) == expected


def profile(primary_condition="LikeNew", rows=None):
    return {
        "category": "clothes",
        "resale_price_estimate": {"estimated_price": 200, "condition_grade": primary_condition,
                                  "condition_assumption": primary_condition, "confidence": .9, "currency": "USD"},
        "resale_price_breakdown": rows or [],
    }


@pytest.mark.parametrize("condition", ["NewWithTags", "New", "LikeNew"])
def test_primary_estimate_must_match_selected_condition(condition):
    result = valuation_from_gpt_item_profile(profile(condition), default_currency="USD", condition_grade=condition)
    assert result["estimated_value"] == 200
    assert result["condition_alignment"]["primary_rejected"] is False


def test_new_uses_matching_band_not_likenew_primary_or_nwt_band():
    rows = [
        {"label": "New with tags", "condition_grade": "NewWithTags", "estimated_price": 400},
        {"label": "EUC / Like New", "condition_grade": "LikeNew", "estimated_price": 150},
        {"label": "New without tags", "condition_grade": "New", "estimated_price": 300, "confidence": .6},
    ]
    result = valuation_from_gpt_item_profile(profile(rows=rows), default_currency="USD", condition_grade="New")
    assert result["estimated_value"] == 300
    assert result["selected_breakdown_label"] == "New without tags"
    assert result["confidence"] == .6
    assert result["condition_alignment"]["primary_rejected"] is True


def test_mismatched_or_unlabelled_prices_are_not_used_without_a_valid_fallback():
    for p in [profile("LikeNew"), profile("NewWithTags"), profile("")]:
        assert valuation_from_gpt_item_profile(p, default_currency="USD", condition_grade="New") is None


def test_conflicting_explicit_grade_and_label_is_rejected():
    p = profile("New")
    p["resale_price_estimate"]["condition_assumption"] = "EUC / Like New"
    p["resale_price_breakdown"] = [{"label": "NWT", "condition_grade": "New", "estimated_price": 999}]
    assert valuation_from_gpt_item_profile(p, default_currency="USD", condition_grade="New") is None


def test_retail_fallback_is_explicitly_condition_adjusted_and_low_confidence():
    p = profile("LikeNew")
    p["retail_price_estimate"] = {"estimated_price": 1000, "confidence": .9, "currency": "USD"}
    result = valuation_from_gpt_item_profile(p, default_currency="USD", condition_grade="New")
    assert result["estimated_value"] == 720
    assert result["basis"] == "gpt_retail_reference_resale_fallback"
    assert result["confidence"] <= .35
    assert result["condition_alignment"]["selected_condition"] == "New"


def test_cached_analysis_revalidates_price_instead_of_copying_old_wrong_band():
    from app.main import _reuse_recent_analysis_for_listing

    p = profile("LikeNew", rows=[{"label": "New without tags", "condition_grade": "New", "estimated_price": 300}])
    p["model_identification"] = {"name": "Dress"}
    cached = {"brand": {"name": "Known brand", "confidence": .95}, "category": "clothes",
              "user_condition": "New", "item_profile": p,
              "valuation": {"estimated_value": 999, "currency": "USD"}}

    class FakeDb:
        updated = None

        def list_image_records_for_item(self, item_id, limit=20):
            return [{"image_id": "photo", "content_hash": "same-photo", "role_hint": "full_item"}]

        def find_recent_analysis_by_image_hashes(self, hashes, limit=50):
            return {"analysis_id": "cached", "item_id": "source", "response": cached}

        def update_listing(self, **kwargs):
            self.updated = kwargs

    db = FakeDb()
    result = _reuse_recent_analysis_for_listing(
        db=db, listing_id="listing", owner_subject="owner",
        current={"source_item_id": "source", "condition": "New", "title": "Dress"},
    )
    assert result is not None
    assert db.updated["estimated_value"] == 300
    assert db.updated["analysis"]["valuation"]["condition_alignment"]["primary_rejected"] is True
    assert cached["valuation"]["estimated_value"] == 999  # The source analysis is not mutated.
