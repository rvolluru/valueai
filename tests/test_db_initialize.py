from app.db import Database


class _FakePG:
    def __init__(self):
        self.rollback_calls = 0

    def rollback(self):
        self.rollback_calls += 1


class _TrackingDatabase(Database):
    def __init__(self):
        self._sqlite_conn = None
        self._pg = _FakePG()
        self.param = "%s"
        self.commit_calls = 0
        self._events: list[tuple[str, str]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        stmt = sql.strip()
        if stmt.startswith("CREATE TABLE"):
            self._events.append(("execute", "create"))
            return
        if stmt.startswith("ALTER TABLE"):
            self._events.append(("execute", "alter"))
            if "ALTER TABLE listings ADD COLUMN images_json" in stmt:
                raise RuntimeError("duplicate column")
            return
        self._events.append(("execute", "other"))

    def commit(self) -> None:
        self.commit_calls += 1
        self._events.append(("commit", ""))


def test_initialize_commits_create_tables_before_optional_alters() -> None:
    db = _TrackingDatabase()
    db.initialize()

    first_alter_index = next(i for i, e in enumerate(db._events) if e == ("execute", "alter"))
    assert ("commit", "") in db._events[:first_alter_index], "expected commit before first ALTER"

    # Failed ALTERs should be tolerated and rolled back without aborting initialize.
    assert db._pg.rollback_calls >= 1
    assert db.commit_calls >= 2
