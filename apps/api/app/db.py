from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class PersistedImage:
    image_id: str
    item_id: str
    storage_uri: str
    filename: str
    role_hint: str | None


class Database:
    def __init__(self, url: str):
        self.url = url
        self._sqlite_conn: sqlite3.Connection | None = None
        self._pg = None
        if url.startswith("sqlite:///"):
            path = url.replace("sqlite:///", "", 1)
            self._sqlite_conn = sqlite3.connect(path, check_same_thread=False)
            self._sqlite_conn.row_factory = sqlite3.Row
            self.param = "?"
        elif url.startswith("postgresql://"):
            try:
                import psycopg
            except Exception as exc:  # pragma: no cover
                raise RuntimeError("psycopg is required for PostgreSQL DATABASE_URL") from exc
            self._pg = psycopg.connect(url)
            self.param = "%s"
        else:
            raise ValueError(f"Unsupported DATABASE_URL: {url}")

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS items (
              item_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS images (
              image_id TEXT PRIMARY KEY,
              item_id TEXT NOT NULL,
              filename TEXT NOT NULL,
              role_hint TEXT,
              storage_uri TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analyses (
              analysis_id TEXT PRIMARY KEY,
              item_id TEXT NOT NULL,
              category TEXT NOT NULL,
              brand_name TEXT NOT NULL,
              brand_confidence REAL NOT NULL,
              brand_evidence TEXT NOT NULL,
              condition_grade TEXT NOT NULL,
              condition_confidence REAL NOT NULL,
              requested_photos_json TEXT NOT NULL,
              response_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS model_versions (
              id TEXT PRIMARY KEY,
              module TEXT NOT NULL,
              version TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
        ]
        for stmt in statements:
            self.execute(stmt)
        self.commit()

    def execute(self, sql: str, params: tuple = ()) -> None:
        if self._sqlite_conn is not None:
            self._sqlite_conn.execute(sql, params)
            return
        cur = self._pg.cursor()
        cur.execute(sql, params)
        cur.close()

    def commit(self) -> None:
        if self._sqlite_conn is not None:
            self._sqlite_conn.commit()
        else:
            self._pg.commit()

    def insert_item(self, item_id: str) -> None:
        self.execute(
            f"INSERT OR IGNORE INTO items (item_id, created_at) VALUES ({self.param}, {self.param})"
            if self._sqlite_conn is not None
            else "INSERT INTO items (item_id, created_at) VALUES (%s, %s) ON CONFLICT (item_id) DO NOTHING",
            (item_id, utc_now_iso()),
        )
        self.commit()

    def insert_image(self, record: PersistedImage) -> None:
        self.execute(
            f"""INSERT INTO images
            (image_id, item_id, filename, role_hint, storage_uri, created_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                record.image_id,
                record.item_id,
                record.filename,
                record.role_hint,
                record.storage_uri,
                utc_now_iso(),
            ),
        )
        self.commit()

    def insert_analysis(self, analysis_id: str, item_id: str, response: dict) -> None:
        self.execute(
            f"""INSERT INTO analyses
            (analysis_id, item_id, category, brand_name, brand_confidence, brand_evidence,
             condition_grade, condition_confidence, requested_photos_json, response_json, created_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param},
                    {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                analysis_id,
                item_id,
                response["category"],
                response["brand"]["name"],
                float(response["brand"]["confidence"]),
                response["brand"]["evidence"],
                response["condition"]["grade"],
                float(response["condition"]["confidence"]),
                json.dumps(response.get("requested_photos", [])),
                json.dumps(response),
                utc_now_iso(),
            ),
        )
        self.commit()
