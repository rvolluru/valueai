from app.db import Database
import pytest
from types import SimpleNamespace


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

    def fetchall(self, sql: str, params: tuple = ()):
        self._events.append(("verify", sql))
        return []

    def fetchone(self, sql: str, params: tuple = ()):
        return None


def test_initialize_commits_create_tables_before_optional_alters() -> None:
    db = _TrackingDatabase()
    db.initialize()

    first_alter_index = next(i for i, e in enumerate(db._events) if e == ("execute", "alter"))
    assert ("commit", "") in db._events[:first_alter_index], "expected commit before first ALTER"

    # Failed ALTERs should be tolerated and rolled back without aborting initialize.
    assert db._pg.rollback_calls >= 1
    assert db.commit_calls >= 2


def test_required_notification_migration_failure_is_not_swallowed():
    db = _TrackingDatabase()
    execute = db.execute
    def fail(sql, params=()):
        if sql.startswith("ALTER TABLE user_notifications"):
            raise RuntimeError("migration lock timeout")
        return execute(sql, params)
    db.execute = fail
    with pytest.raises(RuntimeError, match="migration lock timeout"):
        db.initialize()


def test_production_dependency_does_not_run_optional_migrations(monkeypatch):
    from app import deps
    calls = []
    class ProductionDatabase:
        _pg = object()
        def __init__(self, url): pass
        def initialize(self): raise AssertionError('Optional migrations must not run on request startup')
        def ensure_notification_history_schema(self): calls.append('ready')
    deps.get_db.cache_clear()
    monkeypatch.setattr(deps, 'Database', ProductionDatabase)
    monkeypatch.setattr(deps, 'get_settings', lambda: SimpleNamespace(database_url='postgresql://test'))
    try:
        assert deps.get_db() is deps.get_db()
        assert calls == ['ready']
    finally:
        deps.get_db.cache_clear()


@pytest.mark.parametrize('method,args', [('fetchone', ('SELECT 1',)), ('fetchall', ('SELECT 1',)), ('_fetch_dicts', ('SELECT 1',)), ('list_user_notifications', ('owner',))])
def test_failed_pg_reads_rollback_transaction(method, args):
    db = _TrackingDatabase()
    class Cursor:
        closed = False
        def execute(self, *args): raise RuntimeError('query failed')
        def close(self): self.closed = True
    cursor = Cursor()
    db._pg_cursor = lambda: cursor
    # Use the actual implementation rather than the initializer test double.
    with pytest.raises(RuntimeError, match='query failed'):
        getattr(Database, method)(db, *args)
    assert db._pg.rollback_calls == 1
    assert cursor.closed
