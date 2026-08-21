from app.db import Database


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return self._row

    def close(self):
        return None


class _FakePG:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCursor(self._row)


def test_get_user_profile_quiz_postgres_tuple_column_mapping() -> None:
    # Simulate the positional tuple returned by psycopg for the SELECT in get_user_profile_quiz.
    # This specifically guards against column-offset bugs when optional columns are added.
    row = (
        "user_123",  # owner_subject
        "Jane",  # first_name
        "Doe",  # last_name
        "jane@example.com",  # email
        "female",  # gender
        "1990-01-15",  # birthday
        "M",  # tops_size
        "6",  # dresses_size
        "28",  # bottoms_size
        "8",  # shoes_size
        '["handbag"]',  # category_preferences_json
        '["Classic"]',  # style_descriptors_json
        '["Refresh My Closet"]',  # jouft_goals_json
        "Jane Doe",  # shipping_full_name
        "1 Main St",  # shipping_address_line1
        "Apt 1",  # shipping_address_line2
        "Miami",  # shipping_city
        "FL",  # shipping_state
        "33101",  # shipping_postal_code
        "US",  # shipping_country
        "jane@example.com",  # shipping_email
        "+1-555-0100",  # shipping_phone
        "[]",  # shipping_addresses_json
        "premium",  # subscription_plan
        "monthly",  # subscription_billing_cycle
        "active",  # subscription_status
        None,  # subscription_renewal_date
        '["pm_123"]',  # payment_methods_json
        "2026-05-01T12:00:00+00:00",  # created_at
        "2026-05-02T12:00:00+00:00",  # updated_at
    )

    db = object.__new__(Database)
    db._sqlite_conn = None
    db._pg = _FakePG(row)
    db.param = "%s"

    quiz = db.get_user_profile_quiz("user_123")

    assert quiz is not None
    assert quiz["owner_subject"] == "user_123"
    assert quiz["first_name"] == "Jane"
    assert quiz["last_name"] == "Doe"
    assert quiz["email"] == "jane@example.com"
    assert quiz["birthday"] == "1990-01-15"
    assert quiz["style_descriptors"] == ["Classic"]
    assert quiz["jouft_goals"] == ["Refresh My Closet"]
    assert quiz["subscription_plan"] == "premium"
    assert quiz["subscription_billing_cycle"] == "monthly"
    assert quiz["subscription_status"] == "active"
    assert quiz["subscription_renewal_date"] is None
    assert quiz["payment_methods"] == ["pm_123"]
    assert quiz["created_at"] == "2026-05-01T12:00:00+00:00"
    assert quiz["updated_at"] == "2026-05-02T12:00:00+00:00"


def test_create_trade_offer_stores_sender_receive_address() -> None:
    db = Database("sqlite:///:memory:")
    db.initialize()

    address = {
        "label": "Home",
        "full_name": "Jane Doe",
        "address_line1": "1 Main St",
        "address_line2": "Apt 1",
        "city": "Miami",
        "state": "FL",
        "postal_code": "33101",
        "country": "US",
        "is_default": True,
    }

    offer = db.create_trade_offer(
        offer_id="offer_123",
        target_listing_id="target_listing",
        offered_listing_id="offered_listing",
        offered_listing_ids=["offered_listing"],
        from_subject="sender",
        to_subject="receiver",
        from_receive_address=address,
        message="Trade?",
    )

    assert offer["accepted_by_from"] is True
    assert offer["from_receive_address"]["address_line1"] == "1 Main St"
    assert offer["from_receive_address"]["city"] == "Miami"
    assert offer["to_receive_address"] is None
    assert offer["selected_offered_listing_id"] is None


def test_trade_offer_acceptance_records_selected_offered_listing() -> None:
    db = Database("sqlite:///:memory:")
    db.initialize()

    receive_address = {
        "full_name": "Receiver",
        "address_line1": "2 Main St",
        "city": "Miami",
        "state": "FL",
        "postal_code": "33101",
        "country": "US",
    }
    offer = db.create_trade_offer(
        offer_id="offer_multi",
        target_listing_id="target_listing",
        offered_listing_id="offered_a",
        offered_listing_ids=["offered_a", "offered_b"],
        from_subject="sender",
        to_subject="receiver",
        from_receive_address=receive_address,
        message="Choose one",
    )

    assert offer["selected_offered_listing_id"] is None

    missing_selection = db.set_trade_offer_participant_action(
        offer_id="offer_multi",
        actor_subject="receiver",
        status="accepted",
        receive_address=receive_address,
    )
    assert missing_selection is None

    accepted = db.set_trade_offer_participant_action(
        offer_id="offer_multi",
        actor_subject="receiver",
        status="accepted",
        receive_address=receive_address,
        selected_offered_listing_id="offered_b",
    )

    assert accepted is not None
    assert accepted["status"] == "accepted"
    assert accepted["selected_offered_listing_id"] == "offered_b"
    assert accepted["offered_listing_ids"] == ["offered_a", "offered_b"]
