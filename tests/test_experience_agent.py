from app.experience_agent import build_experience_report


def _events(name: str, users: int, *, screen: str = "create_listing", reason: str | None = None) -> list[dict]:
    return [
        {
            "event_name": name,
            "owner_subject": f"user-{index}",
            "session_id": f"session-{index}",
            "screen": screen,
            "properties": {"reason": reason} if reason else {},
        }
        for index in range(users)
    ]


def test_experience_agent_identifies_material_listing_drop_off() -> None:
    events = _events("listing_started", 10) + _events("listing_photos_added", 8) + _events("listing_created", 4)

    report = build_experience_report(events, days=30, minimum_sample=5)

    listing_funnel = next(item for item in report["funnels"] if item["key"] == "listing_creation")
    assert report["data_quality"] == "sufficient"
    assert listing_funnel["largest_drop_off"]["rate"] == 50.0
    assert any(item["category"] == "drop_off" and item["severity"] == "high" for item in report["findings"])
    assert report["next_steps"][0]["success_metric"]
    assert "actionable" in report["executive_summary"]


def test_experience_agent_withholds_findings_for_small_samples() -> None:
    events = _events("listing_started", 2) + _events("listing_created", 1)

    report = build_experience_report(events, days=30, minimum_sample=5)

    assert report["data_quality"] == "insufficient"
    assert report["findings"] == []
    assert report["next_steps"] == []


def test_experience_agent_requires_funnel_events_in_sequence() -> None:
    events = []
    for index in range(5):
        events.extend([
            {"event_name": "listing_created", "owner_subject": f"user-{index}", "session_id": f"s-{index}"},
            {"event_name": "listing_started", "owner_subject": f"user-{index}", "session_id": f"s-{index}"},
        ])

    report = build_experience_report(events, days=30, minimum_sample=5)
    funnel = next(item for item in report["funnels"] if item["key"] == "listing_creation")

    assert funnel["steps"][0]["users"] == 5
    assert funnel["steps"][2]["users"] == 0


def test_experience_agent_groups_repeated_errors() -> None:
    events = _events("ui_error", 5, screen="trade", reason="shipping_quote_failed")

    report = build_experience_report(events, days=30, minimum_sample=5)

    assert report["friction_signals"][0]["reason"] == "shipping_quote_failed"
    assert report["friction_signals"][0]["affected_users"] == 5
    assert any(item["category"] == "friction" for item in report["findings"])
