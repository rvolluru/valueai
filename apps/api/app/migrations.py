"""Explicit versioned migrations. Run before starting API/workers, not in jobs."""
from __future__ import annotations

import argparse
import json

from .db import Database, utc_now_iso


def _baseline(db):
    db._bootstrap_schema()


def _analysis_history(db):
    db.execute("""CREATE TABLE IF NOT EXISTS analysis_listing_links (
        item_id TEXT NOT NULL, listing_id TEXT NOT NULL, owner_subject TEXT NOT NULL,
        job_id TEXT, created_at TEXT NOT NULL, PRIMARY KEY (item_id, listing_id))""")
    # Only backfill relationships established by stored IDs, never inferred ownership.
    for source in ("SELECT source_item_id, listing_id, owner_subject, NULL, created_at FROM listings WHERE source_item_id IS NOT NULL",
                   "SELECT result_item_id, listing_id, owner_subject, job_id, created_at FROM listing_analysis_jobs WHERE result_item_id IS NOT NULL"):
        db.execute("INSERT INTO analysis_listing_links (item_id, listing_id, owner_subject, job_id, created_at) "
                   + source + " ON CONFLICT (item_id, listing_id) DO NOTHING")
    db.commit()


def _media_urls(db):
    db.migrate_listing_media_urls_to_http()


def _pipeline_components(db):
    db.execute("""CREATE TABLE IF NOT EXISTS listing_pipeline_components (
        job_id TEXT NOT NULL, component TEXT NOT NULL, inputs_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
        error TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (job_id, component))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_analysis_jobs_listing_owner_created "
               "ON listing_analysis_jobs (listing_id, owner_subject, created_at)")
    db.commit()


# Add a new version for future changes; do not edit an already-applied migration.
MIGRATIONS = (
    ("0001_application_schema", _baseline),
    ("0002_analysis_listing_links", _analysis_history),
    ("0003_listing_media_urls", _media_urls),
    ("0004_listing_pipeline_components", _pipeline_components),
)


def migrate(db: Database) -> list[str]:
    with db.analysis_execution_lock("schema-migrations") as acquired:
        if not acquired:
            raise RuntimeError("Another schema migration is running; no changes applied by this runner")
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        db.commit()
        applied = {row[0] for row in db.fetchall("SELECT version FROM schema_migrations")}
        db.commit()
        completed = []
        for version, operation in MIGRATIONS:
            if version in applied:
                continue
            try:
                operation(db)
                db.execute(f"INSERT INTO schema_migrations (version, applied_at) VALUES ({db.param}, {db.param})",
                           (version, utc_now_iso()))
                db.commit()
            except Exception:
                if db._pg is not None:
                    db._pg.rollback()
                elif db._sqlite_conn is not None:
                    db._sqlite_conn.rollback()
                raise
            completed.append(version)
        return completed


def main():
    from .settings import get_settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only schema readiness check")
    args = parser.parse_args()
    db = Database(get_settings().database_url)
    try:
        if args.check:
            db.verify_schema()
            print(json.dumps({"schema_ready": True}))
        else:
            print(json.dumps({"migrations_applied": migrate(db)}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
