import pytest

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


@pytest.mark.parametrize("group,status", [("active", "requested"), ("done", "declined")])
def test_trade_groups_preserve_postgres_tuple_column_mapping(group, status, monkeypatch):
    db = Database("sqlite:///:memory:")
    db.initialize()
    connection = db._sqlite_conn
    connection.execute(
        "INSERT INTO trade_offers (offer_id,target_listing_id,offered_listing_id,"
        "offered_listing_ids_json,selected_offered_listing_id,from_subject,to_subject,"
        "status,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("offer", "target", "offered", '["offered", "second"]', "second",
         "sender", "receiver", status, "Trade message", "created", "updated"),
    )
    # PostgreSQL returns positional tuples, unlike SQLite's named Row objects.
    # Execute the real query against a schema whose physical order differs from
    # the decoder's required order, then return tuples just like PostgreSQL.
    connection.row_factory = None
    db._sqlite_conn = None
    monkeypatch.setattr(db, "_pg_cursor", connection.cursor)
    offers = db.list_trade_offers_for_subject("sender", status=group)
    assert len(offers) == 1
    offer = offers[0]
    assert offer["status"] == status
    assert offer["from_subject"] == "sender"
    assert offer["to_subject"] == "receiver"
    assert offer["selected_offered_listing_id"] == "second"
    assert offer["offered_listing_ids"] == ["offered", "second"]
    assert offer["message"] == "Trade message"
    assert offer["created_at"] == "created"
    assert offer["updated_at"] == "updated"
    assert offer["accepted_by_from"] is False
    assert offer["accepted_by_to"] is False
