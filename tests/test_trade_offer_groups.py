from app.db import Database


def test_trade_groups_filter_before_limit_and_preserve_subject_scope():
    db = Database("sqlite:///:memory:")
    db.initialize()
    statuses = ["declined", "completed", "finished", "accepted", "pending", "countered", "cancelled", "future_status"]
    for index, status in enumerate(statuses):
        db.execute(
            "INSERT INTO trade_offers (offer_id,target_listing_id,offered_listing_id,from_subject,to_subject,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(index), "target", "offered", "owner", "other", status, str(index), str(index)),
        )
    db.execute(
        "INSERT INTO trade_offers (offer_id,target_listing_id,offered_listing_id,from_subject,to_subject,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("unrelated", "target", "offered", "stranger", "another", "declined", "99", "99"),
    )
    db.commit()
    assert {o["status"] for o in db.list_trade_offers_for_subject("owner", status="done")} == set(statuses[:3])
    assert {o["status"] for o in db.list_trade_offers_for_subject("owner", status="active")} == set(statuses[3:])
    assert len(db.list_trade_offers_for_subject("owner", status="done", limit=1)) == 1
    assert db.list_trade_offers_for_subject("owner", status="done", limit=1)[0]["status"] == "finished"
    assert len(db.list_trade_offers_for_subject("other", status="active")) == 5
