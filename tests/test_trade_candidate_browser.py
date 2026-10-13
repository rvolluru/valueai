from types import SimpleNamespace
import pytest
from fastapi import HTTPException


def test_candidate_browser_includes_eligible_items_beyond_first_source_page(monkeypatch):
    from app import main
    class Listing:
        def __init__(self, **data): self.data = data
        def model_dump(self): return self.data
    monkeypatch.setattr(main, "ListingResponse", Listing)
    class DB:
        def get_trade_offer_by_id(self, offer_id):
            return {"to_subject": "receiver", "from_subject": "sender", "target_listing_id": "target", "status": "requested"}
        def get_listing_by_id(self, listing_id): return {"estimated_value": 100, "status": "Active"}
        def list_owner_listings(self, owner, limit, offset):
            assert owner == "sender"
            if offset == 0: return [{"listing_id": str(i), "estimated_value": 100, "status": "Review"} for i in range(100)]
            return [{"listing_id": "eligible", "estimated_value": 100, "status": "Active"}]
    result = main.list_offer_proposal_candidates("offer", limit=100, offset=0, principal=SimpleNamespace(subject="receiver"), db=DB())
    assert [item["listing_id"] for item in result["items"]] == ["eligible"]
    assert result["has_more"] is False


@pytest.mark.parametrize("actor,status,target_status,expected", [
    ("sender", "requested", "Active", 403),
    ("receiver", "declined", "Active", 409),
    ("receiver", "requested", "Traded", 409),
])
def test_candidate_browser_rejects_unauthorized_or_unavailable_requests(actor, status, target_status, expected):
    from app import main
    class DB:
        def get_trade_offer_by_id(self, _):
            return {"to_subject":"receiver", "from_subject":"sender", "target_listing_id":"target", "status":status}
        def get_listing_by_id(self, _): return {"status":target_status}
    with pytest.raises(HTTPException) as error:
        main.list_offer_proposal_candidates("offer", limit=100, offset=0, principal=SimpleNamespace(subject=actor), db=DB())
    assert error.value.status_code == expected
