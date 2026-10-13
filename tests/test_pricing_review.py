from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from app import main


def test_owner_cannot_publish_pending_pricing_review():
    db = SimpleNamespace(list_owner_listings=lambda *args, **kwargs: [
        {"listing_id": "listing", "brand": "Brand", "analysis": {"pricing_review": {"status": "pending"}}}
    ])
    with pytest.raises(HTTPException) as error:
        main.update_listing(
            "listing", SimpleNamespace(brand="Brand", status="Active"),
            None, SimpleNamespace(subject="owner"), db, None, None, None,
        )
    assert error.value.status_code == 409
    assert "manual pricing review" in error.value.detail


def test_pricing_review_creates_incident_and_sends_admin_email(monkeypatch):
    monkeypatch.setattr(main, "_pricing_review_admin_recipients", lambda settings: ["admin@example.com"])
    incidents, emails = [], []
    db = SimpleNamespace(create_production_incident=lambda **kwargs: incidents.append(kwargs))
    settings = SimpleNamespace(pricing_review_admin_email="admin@example.com")
    def send(**kwargs):
        emails.append(kwargs)
        return "sent_ses"
    monkeypatch.setattr(main, "_send_support_email", send)
    kwargs = dict(listing_id="listing", item_id="item", job_id="job", title="Dress")
    review = main._request_listing_pricing_review(db, settings, **kwargs)
    assert review["status"] == "pending"
    assert "do not need to set a value" in review["message"]
    assert incidents[0]["incident_type"] == "pricing_review_required"
    assert emails[0]["recipient"] == "admin@example.com"
    main._request_listing_pricing_review(db, settings, previous_review=review, **kwargs)
    assert len(incidents) == len(emails) == 1


def test_pricing_review_email_failure_does_not_lose_review(monkeypatch):
    monkeypatch.setattr(main, "_pricing_review_admin_recipients", lambda settings: ["admin@example.com"])
    db = SimpleNamespace(create_production_incident=lambda **kwargs: None)
    def fail(**kwargs):
        raise RuntimeError("mail unavailable")
    monkeypatch.setattr(main, "_send_support_email", fail)
    review = main._request_listing_pricing_review(
        db, SimpleNamespace(pricing_review_admin_email="admin@example.com"),
        listing_id="listing", item_id="item", job_id="job", title="Dress",
    )
    assert review["status"] == "pending"
    assert review["email_status"] == "failed"
    assert review["incident_id"]


def test_admin_directory_filters_roles_and_verification(monkeypatch):
    def user(uid, role, verified=True, unsafe=False):
        return {"id": uid, "primary_email_address_id": uid,
                "unsafe_metadata" if unsafe else "public_metadata": {"role": role},
                "email_addresses": [{"id": uid, "email_address": f"{uid}@example.com",
                                     "verification": {"status": "verified" if verified else "unverified"}}]}
    pages = [[user("admin", "admin"), user("second", "admin"), user("member", "member"),
              user("unverified", "admin", False), user("unsafe", "admin", unsafe=True)]]
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: pages.pop(0))
    monkeypatch.setattr(main.httpx, "Client", Client)
    assert main._pricing_review_admin_recipients(SimpleNamespace(clerk_secret_key="test")) == ["admin@example.com", "second@example.com"]


def test_alerts_each_admin_and_retries_only_failed_delivery(monkeypatch):
    monkeypatch.setattr(main, "_pricing_review_admin_recipients", lambda settings: ["a@example.com", "b@example.com"])
    sent = []
    def send(**kwargs):
        sent.append(kwargs["recipient"])
        return "failed_ses" if len(sent) == 2 else "sent_ses"
    monkeypatch.setattr(main, "_send_support_email", send)
    db = SimpleNamespace(create_production_incident=lambda **kwargs: None)
    kwargs = dict(listing_id="listing", item_id="item", job_id="job", title="Dress")
    review = main._request_listing_pricing_review(db, object(), **kwargs)
    assert review["email_status"] == "failed"
    review = main._request_listing_pricing_review(db, object(), previous_review=review, **kwargs)
    assert sent == ["a@example.com", "b@example.com", "b@example.com"]
    assert review["email_status"] == "sent"
