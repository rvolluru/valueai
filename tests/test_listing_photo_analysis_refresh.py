from types import SimpleNamespace

import pytest

from app import main


@pytest.mark.parametrize("photos_changed", [True, False])
def test_edited_photos_skip_previous_analysis(monkeypatch, photos_changed):
    current = {"listing_id": "listing", "source_item_id": "old-two-photo-item"}

    class FakeDb:
        def __init__(self, url):
            pass

        def initialize(self):
            pass

        def list_owner_listings(self, subject, limit):
            return [current]

    calls = []

    def reuse(**kwargs):
        calls.append("reuse")
        return {"item_id": "cached"}

    files = [{"data": b"front"}, {"data": b"label"}, {"data": b"new-back"}]
    monkeypatch.setattr(main, "Database", FakeDb)
    monkeypatch.setattr(main, "_reuse_recent_analysis_for_listing", reuse)
    monkeypatch.setattr(main, "_collect_listing_analysis_files", lambda **kwargs: files)
    monkeypatch.setattr(main, "_run_listing_analysis_job_threaded", lambda **kwargs: calls.append(kwargs["files"]))
    main._run_listing_analysis_for_existing_listing_job(
        listing_id="listing", owner_subject="owner", category="clothes",
        item_size="S", user_condition="New", item_description="Dress",
        debug=True, settings=SimpleNamespace(database_url="sqlite:///:memory:"),
        valuation_service=None, gpt_item_profiler=None,
        stage_images_after_analysis=photos_changed,
        force_fresh_analysis=photos_changed,
    )
    assert calls == ([files] if photos_changed else ["reuse"])
