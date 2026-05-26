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
            """
            CREATE TABLE IF NOT EXISTS condition_feedback (
              id TEXT PRIMARY KEY,
              item_id TEXT NOT NULL,
              user_condition TEXT NOT NULL,
              model_condition TEXT NOT NULL,
              warning_json TEXT NOT NULL,
              response_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS listings (
              listing_id TEXT PRIMARY KEY,
              owner_subject TEXT NOT NULL,
              owner_name TEXT,
              title TEXT NOT NULL,
              mode TEXT NOT NULL,
              category TEXT NOT NULL,
              brand TEXT NOT NULL,
              condition TEXT NOT NULL,
              size TEXT,
              estimated_value REAL NOT NULL,
              city TEXT NOT NULL,
              image TEXT,
              images_json TEXT NOT NULL DEFAULT '[]',
              wants TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              source_item_id TEXT,
              analysis_json TEXT,
              status TEXT NOT NULL DEFAULT 'Review',
              created_at TEXT NOT NULL
            )
            """,
        ]
        for stmt in statements:
            self.execute(stmt)
        for alter in (
            "ALTER TABLE listings ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE listings ADD COLUMN status TEXT NOT NULL DEFAULT 'Review'",
            "ALTER TABLE listings ADD COLUMN size TEXT",
        ):
            try:
                self.execute(alter)
            except Exception:
                if self._pg is not None:
                    self._pg.rollback()
                pass
        self.commit()

    def execute(self, sql: str, params: tuple = ()) -> None:
        if self._sqlite_conn is not None:
            self._sqlite_conn.execute(sql, params)
            return
        cur = self._pg.cursor()
        try:
            cur.execute(sql, params)
        except Exception:
            self._pg.rollback()
            raise
        finally:
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

    def update_analysis_response(self, analysis_id: str, response: dict) -> None:
        self.execute(
            f"""UPDATE analyses
            SET category = {self.param},
                brand_name = {self.param},
                brand_confidence = {self.param},
                brand_evidence = {self.param},
                condition_grade = {self.param},
                condition_confidence = {self.param},
                requested_photos_json = {self.param},
                response_json = {self.param}
            WHERE analysis_id = {self.param}""",
            (
                response["category"],
                response["brand"]["name"],
                float(response["brand"]["confidence"]),
                response["brand"]["evidence"],
                response["condition"]["grade"],
                float(response["condition"]["confidence"]),
                json.dumps(response.get("requested_photos", [])),
                json.dumps(response),
                analysis_id,
            ),
        )
        self.commit()

    def insert_condition_feedback(
        self,
        feedback_id: str,
        item_id: str,
        user_condition: str,
        model_condition: str,
        warnings: list[str],
        response: dict,
    ) -> None:
        self.execute(
            f"""INSERT INTO condition_feedback
            (id, item_id, user_condition, model_condition, warning_json, response_json, created_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                feedback_id,
                item_id,
                user_condition,
                model_condition,
                json.dumps(warnings),
                json.dumps(response),
                utc_now_iso(),
            ),
        )
        self.commit()

    def list_recent_analyses(self, limit: int = 50) -> list[dict]:
        query = (
            f"SELECT analysis_id, item_id, response_json, created_at FROM analyses "
            f"ORDER BY created_at DESC LIMIT {self.param}"
        )
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (limit,)).fetchall()
            return [self._analysis_row_to_dict(row) for row in rows]
        cur = self._pg.cursor()
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        cur.close()
        return [self._analysis_row_to_dict(row) for row in rows]

    def get_image_storage_uri(self, image_id: str) -> str | None:
        query = f"SELECT storage_uri FROM images WHERE image_id = {self.param} LIMIT 1"
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (image_id,)).fetchone()
            if not row:
                return None
            return row["storage_uri"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg.cursor()
        cur.execute(query, (image_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return row[0]

    def get_first_image_id_for_item(self, item_id: str) -> str | None:
        query = (
            f"SELECT image_id FROM images WHERE item_id = {self.param} "
            f"ORDER BY created_at ASC LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (item_id,)).fetchone()
            if not row:
                return None
            return row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg.cursor()
        cur.execute(query, (item_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return row[0]

    def list_image_ids_for_item(self, item_id: str, limit: int = 8) -> list[str]:
        safe_limit = max(1, min(int(limit), 20))
        query = (
            f"SELECT image_id FROM images WHERE item_id = {self.param} "
            f"ORDER BY created_at ASC LIMIT {self.param}"
        )
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (item_id, safe_limit)).fetchall()
            result: list[str] = []
            for row in rows:
                image_id = row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
                if isinstance(image_id, str) and image_id.strip():
                    result.append(image_id)
            return result
        cur = self._pg.cursor()
        cur.execute(query, (item_id, safe_limit))
        rows = cur.fetchall()
        cur.close()
        result: list[str] = []
        for row in rows:
            image_id = row[0]
            if isinstance(image_id, str) and image_id.strip():
                result.append(image_id)
        return result

    def insert_listing(
        self,
        *,
        listing_id: str,
        owner_subject: str,
        owner_name: str | None,
        title: str,
        mode: str,
        category: str,
        brand: str,
        condition: str,
        size: str | None,
        estimated_value: float,
        city: str,
        image: str | None,
        images: list[str],
        wants: str,
        tags: list[str],
        source_item_id: str | None,
        analysis: dict | None,
        status: str,
    ) -> str:
        created_at = utc_now_iso()
        self.execute(
            f"""INSERT INTO listings
            (listing_id, owner_subject, owner_name, title, mode, category, brand, condition, size,
             estimated_value, city, image, images_json, wants, tags_json, source_item_id, analysis_json, status, created_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param},
                    {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                listing_id,
                owner_subject,
                owner_name,
                title,
                mode,
                category,
                brand,
                condition,
                size,
                float(estimated_value),
                city,
                image,
                json.dumps(images),
                wants,
                json.dumps(tags),
                source_item_id,
                json.dumps(analysis) if analysis is not None else None,
                status,
                created_at,
            ),
        )
        self.commit()
        return created_at

    def list_recent_listings(
        self,
        limit: int = 50,
        include_analysis: bool = True,
        include_media: bool = True,
    ) -> list[dict]:
        analysis_select = "analysis_json" if include_analysis else "NULL AS analysis_json"
        image_select = "image" if include_media else "NULL AS image"
        images_select = "images_json" if include_media else "'[]' AS images_json"
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, {image_select}, {images_select}, wants, tags_json, source_item_id, {analysis_select}, status, created_at "
            f"FROM listings ORDER BY created_at DESC LIMIT {self.param}"
        )
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (limit,)).fetchall()
            return [self._listing_row_to_dict(row) for row in rows]
        cur = self._pg.cursor()
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        cur.close()
        return [self._listing_row_to_dict(row) for row in rows]

    def list_owner_listings(self, owner_subject: str, limit: int = 50) -> list[dict]:
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, image, images_json, wants, tags_json, source_item_id, analysis_json, status, created_at "
            f"FROM listings WHERE owner_subject = {self.param} ORDER BY created_at DESC LIMIT {self.param}"
        )
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (owner_subject, limit)).fetchall()
            return [self._listing_row_to_dict(row) for row in rows]
        cur = self._pg.cursor()
        cur.execute(query, (owner_subject, limit))
        rows = cur.fetchall()
        cur.close()
        return [self._listing_row_to_dict(row) for row in rows]

    def update_listing(
        self,
        *,
        listing_id: str,
        owner_subject: str,
        title: str,
        mode: str,
        category: str,
        brand: str,
        condition: str,
        size: str | None,
        estimated_value: float,
        city: str,
        image: str | None,
        images: list[str],
        wants: str,
        tags: list[str],
        source_item_id: str | None,
        analysis: dict | None,
        status: str,
    ) -> bool:
        sql = f"""UPDATE listings
            SET title = {self.param},
                mode = {self.param},
                category = {self.param},
                brand = {self.param},
                condition = {self.param},
                size = {self.param},
                estimated_value = {self.param},
                city = {self.param},
                image = {self.param},
                images_json = {self.param},
                wants = {self.param},
                tags_json = {self.param},
                source_item_id = {self.param},
                analysis_json = {self.param},
                status = {self.param}
            WHERE listing_id = {self.param} AND owner_subject = {self.param}"""
        params = (
            title,
            mode,
            category,
            brand,
            condition,
            size,
            float(estimated_value),
            city,
            image,
            json.dumps(images),
            wants,
            json.dumps(tags),
            source_item_id,
            json.dumps(analysis) if analysis is not None else None,
            status,
            listing_id,
            owner_subject,
        )
        if self._sqlite_conn is not None:
            self._sqlite_conn.execute(sql, params)
            changed_row = self._sqlite_conn.execute("SELECT changes() AS n").fetchone()
            changed = int(changed_row["n"] if isinstance(changed_row, sqlite3.Row) else changed_row[0]) > 0
        else:
            cur = self._pg.cursor()
            try:
                cur.execute(sql, params)
                changed = int(cur.rowcount or 0) > 0
            except Exception:
                self._pg.rollback()
                raise
            finally:
                cur.close()
        self.commit()
        return changed

    def _analysis_row_to_dict(self, row) -> dict:
        analysis_id = row["analysis_id"] if isinstance(row, sqlite3.Row) else row[0]
        item_id = row["item_id"] if isinstance(row, sqlite3.Row) else row[1]
        response_json = row["response_json"] if isinstance(row, sqlite3.Row) else row[2]
        created_at = row["created_at"] if isinstance(row, sqlite3.Row) else row[3]
        payload = json.loads(response_json)
        return {
            "analysis_id": analysis_id,
            "item_id": item_id,
            "created_at": created_at,
            "response": payload,
        }

    def _listing_row_to_dict(self, row) -> dict:
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = [
                "listing_id",
                "owner_subject",
                "owner_name",
                "title",
                "mode",
                "category",
                "brand",
                "condition",
                "size",
                "estimated_value",
                "city",
                "image",
                "images_json",
                "wants",
                "tags_json",
                "source_item_id",
                "analysis_json",
                "status",
                "created_at",
            ]
            data = {k: row[idx] for idx, k in enumerate(keys)}
        image_raw = data["image"]
        image = image_raw if isinstance(image_raw, str) else None
        if image and (image.startswith("data:") or image.startswith("blob:")):
            image = None

        images = json.loads(data["images_json"]) if data.get("images_json") else []
        safe_images = []
        for value in images:
            if not isinstance(value, str):
                continue
            if value.startswith("data:") or value.startswith("blob:"):
                continue
            safe_images.append(value)

        return {
            "listing_id": data["listing_id"],
            "owner_subject": data["owner_subject"],
            "owner_name": data["owner_name"],
            "title": data["title"],
            "mode": data["mode"],
            "category": data["category"],
            "brand": data["brand"],
            "condition": data["condition"],
            "size": data.get("size"),
            "estimated_value": float(data["estimated_value"]),
            "city": data["city"],
            "image": image,
            "images": safe_images,
            "wants": data["wants"],
            "tags": json.loads(data["tags_json"]) if data["tags_json"] else [],
            "source_item_id": data["source_item_id"],
            "analysis": json.loads(data["analysis_json"]) if data["analysis_json"] else None,
            "status": data.get("status") or "Review",
            "created_at": data["created_at"],
        }
