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
        "female",  # gender
        "M",  # tops_size
        "6",  # dresses_size
        "28",  # bottoms_size
        "8",  # shoes_size
        '["handbag"]',  # category_preferences_json
        "Jane Doe",  # shipping_full_name
        "1 Main St",  # shipping_address_line1
        "Apt 1",  # shipping_address_line2
        "Miami",  # shipping_city
        "FL",  # shipping_state
        "33101",  # shipping_postal_code
        "US",  # shipping_country
        "jane@example.com",  # shipping_email
        "+1-555-0100",  # shipping_phone
        "premium",  # subscription_plan
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
    assert quiz["subscription_plan"] == "premium"
    assert quiz["subscription_status"] == "active"
    assert quiz["subscription_renewal_date"] is None
    assert quiz["payment_methods"] == ["pm_123"]
    assert quiz["created_at"] == "2026-05-01T12:00:00+00:00"
    assert quiz["updated_at"] == "2026-05-02T12:00:00+00:00"
