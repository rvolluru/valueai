import ast
import importlib.util
from pathlib import Path

import pytest

from app.db import Database
from app.migrations import MIGRATIONS, migrate


def test_explicit_migrations_create_schema_and_are_versioned(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'schema.db'}")
    with pytest.raises(RuntimeError, match="Run python -m app.migrations"):
        db.verify_schema()
    assert migrate(db) == [version for version, _ in MIGRATIONS]
    db.verify_schema()
    # Subsequent deployments must not execute baseline DDL or row migrations.
    monkeypatch.setattr(db, "_bootstrap_schema", lambda: pytest.fail("Baseline reran"))
    monkeypatch.setattr(db, "migrate_listing_media_urls_to_http", lambda: pytest.fail("Data migration reran"))
    assert migrate(db) == []
    assert db.fetchone("SELECT COUNT(*) FROM schema_migrations")[0] == len(MIGRATIONS)


def test_legacy_columns_are_checked_before_alter_and_missing_column_is_added(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'legacy.db'}")
    db.initialize()
    db.execute("ALTER TABLE listings DROP COLUMN size")
    db.commit()
    statements = []
    execute = db.execute
    def tracked(sql, params=()):
        statements.append(sql.strip())
        return execute(sql, params)
    db.execute = tracked
    db._bootstrap_schema()
    alters = [sql for sql in statements if sql.startswith("ALTER TABLE")]
    assert alters == ["ALTER TABLE listings ADD COLUMN size TEXT"]


def test_failed_migration_is_not_recorded_and_can_be_retried(tmp_path, monkeypatch):
    from app import migrations
    db = Database(f"sqlite:///{tmp_path / 'failure.db'}")
    calls = []
    def fail(connection):
        calls.append("failed")
        raise RuntimeError("locked schema")
    monkeypatch.setattr(migrations, "MIGRATIONS", (("test", fail),))
    with pytest.raises(RuntimeError, match="locked schema"):
        migrate(db)
    assert db.fetchall("SELECT version FROM schema_migrations") == []
    monkeypatch.setattr(migrations, "MIGRATIONS", (("test", lambda connection: calls.append("ok")),))
    assert migrate(db) == ["test"]
    assert calls == ["failed", "ok"]


def test_readiness_rejects_missing_version_without_ddl(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'pending.db'}")
    db.initialize()
    db.execute("DELETE FROM schema_migrations WHERE version=?", (MIGRATIONS[-1][0],))
    db.commit()
    db.execute = lambda *args: pytest.fail("Readiness attempted a write")
    with pytest.raises(RuntimeError, match="Database migrations required"):
        db.verify_schema()


def test_runtime_code_has_no_implicit_migrations():
    root = Path(__file__).resolve().parents[1]
    for relative in ["apps/api/app/main.py", "apps/api/app/deps.py", "apps/api/app/analysis_worker.py",
                     "apps/api/app/backfill_mannequin_images.py"]:
        tree = ast.parse((root / relative).read_text())
        calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        assert not ({"initialize", "_bootstrap_schema", "ensure_notification_history_schema", "migrate_listing_media_urls_to_http"} & set(calls)), relative


def test_runner_uses_private_seekable_json_and_removes_it(monkeypatch):
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('runner', Path(__file__).resolve().parents[1] / 'scripts/run_ecs_migrations.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    paths = []
    def run(command, **kwargs):
        path = Path(command[command.index('--cli-input-json') + 1].removeprefix('file://'))
        paths.append(path)
        assert path.read_text() == '{"family": "test"}'
        assert path.stat().st_mode & 0o077 == 0
        assert 'input' not in kwargs
        return SimpleNamespace(returncode=0, stdout='{}')
    monkeypatch.setattr(runner.subprocess, 'run', run)
    assert runner.aws('register-task-definition', payload={'family': 'test'}) == {}
    assert not paths[0].exists()


def test_deployment_gate_precedes_both_rollout_modes_and_uses_new_image():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/deploy-prod.yml").read_text()
    gate = workflow.index("name: Migrate database before application rollout")
    assert gate < workflow.index("name: Fast deploy API image")
    assert gate < workflow.index("name: Terraform apply (new image)")
    spec = importlib.util.spec_from_file_location("migration_runner", root / "scripts/run_ecs_migrations.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    original = {"family": "app", "revision": 2, "taskDefinitionArn": "arn", "taskRoleArn": "role",
                "containerDefinitions": [{"name": "api", "image": "old", "healthCheck": {"command": ["test"]},
                                          "secrets": [{"name": "DATABASE_URL", "valueFrom": "secret"}]}]}
    result = runner.migration_definition(original, "new-image")
    assert result["containerDefinitions"][0]["image"] == "new-image"
    assert result["taskRoleArn"] == "role"
    assert result["containerDefinitions"][0]["secrets"] == original["containerDefinitions"][0]["secrets"]
    assert "healthCheck" not in result["containerDefinitions"][0]
    assert "taskDefinitionArn" not in result
    assert original["containerDefinitions"][0]["image"] == "old"


def test_assistant_release_enables_build_and_api_flags_and_smokes_migrated_tables():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / '.github/workflows/deploy-prod.yml').read_text()
    docker = (root / 'apps/api/Dockerfile').read_text()
    for flag in ('VITE_LISTING_AGENT_ENABLED', 'VITE_ASSISTANT_CONVERSATIONS_ENABLED'):
        assert '--build-arg ' + flag + '=true' in workflow
        assert 'ARG ' + flag + '="false"' in docker
    for flag in ('LISTING_AGENT_ENABLED', 'ASSISTANT_CONVERSATIONS_ENABLED'):
        assert 'upsert_env("' + flag + '"; "true")' in workflow
    assert 'SELECT COUNT(*) FROM assistant_conversations' in workflow


@pytest.mark.parametrize("exit_code", [0, 1, None])
def test_deployment_runner_requires_successful_migration_task(monkeypatch, exit_code):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("migration_runner", root / "scripts/run_ecs_migrations.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    calls = []
    def aws(operation, *args, **kwargs):
        calls.append(operation)
        return {
            "describe-services": {"services": [{"status": "ACTIVE", "taskDefinition": "old", "networkConfiguration": {"awsvpcConfiguration": {"subnets": ["subnet"]}}}]},
            "describe-task-definition": {"taskDefinition": {"family": "app", "containerDefinitions": [{"name": "api", "image": "old"}]}},
            "register-task-definition": {"taskDefinition": {"taskDefinitionArn": "migration-definition"}},
            "run-task": {"tasks": [{"taskArn": "migration-task"}]},
            "describe-tasks": {"tasks": [{"lastStatus": "STOPPED", "containers": [{"name": "api", "exitCode": exit_code}]}]},
        }[operation]
    monkeypatch.setattr(runner, "aws", aws)
    monkeypatch.setattr("sys.argv", ["run_ecs_migrations", "--cluster", "cluster", "--service", "service", "--image", "new"])
    if exit_code == 0:
        runner.main()
    else:
        with pytest.raises(RuntimeError, match="Rollout blocked"):
            runner.main()
    assert "update-service" not in calls
