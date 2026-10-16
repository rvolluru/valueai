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

    def _schema_columns(self):
        return {}


def test_bootstrap_commits_create_tables_before_alters_and_fails_closed() -> None:
    db = _TrackingDatabase()
    with pytest.raises(RuntimeError, match="duplicate column"):
        db._bootstrap_schema()

    first_alter_index = next(i for i, e in enumerate(db._events) if e == ("execute", "alter"))
    assert ("commit", "") in db._events[:first_alter_index], "expected commit before first ALTER"

    # Migration errors must block rollout rather than being silently swallowed.
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
        db._bootstrap_schema()


def test_production_dependency_does_not_run_optional_migrations(monkeypatch):
    from app import deps
    calls = []
    class ProductionDatabase:
        _pg = object()
        def __init__(self, url): pass
        def initialize(self): raise AssertionError('Optional migrations must not run on request startup')
        def ensure_notification_history_schema(self): raise AssertionError('No runtime DDL, including notification repair')
        def verify_schema(self): calls.append('ready')
    deps.get_db.cache_clear()
    monkeypatch.setattr(deps, 'Database', ProductionDatabase)
    monkeypatch.setattr(deps, 'get_settings', lambda: SimpleNamespace(database_url='postgresql://test'))
    try:
        assert deps.get_db() is deps.get_db()
        assert calls == ['ready']
    finally:
        deps.get_db.cache_clear()


@pytest.mark.parametrize('method,args', [('fetchone', ('SELECT 1',)), ('fetchall', ('SELECT 1',)), ('_fetch_dicts', ('SELECT 1',)), ('list_user_notifications', ('owner',)), ('list_recent_listings', ()), ('list_owner_listings', ('owner',))])
def test_failed_pg_reads_rollback_transaction(method, args):
    db = _TrackingDatabase()
    class Cursor:
        closed = False
        def execute(self, *args): raise RuntimeError('query failed')
        def close(self): self.closed = True
    cursor = Cursor()
    db._pg_cursor = lambda: cursor
    if method in {'list_recent_listings', 'list_owner_listings'}:
        db.fetchall = lambda *arguments: Database.fetchall(db, *arguments)
    # Use the actual implementation rather than the initializer test double.
    with pytest.raises(RuntimeError, match='query failed'):
        getattr(Database, method)(db, *args)
    assert db._pg.rollback_calls == 1
    assert cursor.closed
