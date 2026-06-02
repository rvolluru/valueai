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
              description TEXT NOT NULL DEFAULT '',
              wants TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              source_item_id TEXT,
              analysis_json TEXT,
              status TEXT NOT NULL DEFAULT 'Review',
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
              owner_subject TEXT PRIMARY KEY,
              gender TEXT,
              tops_size TEXT,
              dresses_size TEXT,
              bottoms_size TEXT,
              shoes_size TEXT,
              category_preferences_json TEXT NOT NULL DEFAULT '[]',
              shipping_full_name TEXT,
              shipping_address_line1 TEXT,
              shipping_address_line2 TEXT,
              shipping_city TEXT,
              shipping_state TEXT,
              shipping_postal_code TEXT,
              shipping_country TEXT,
              shipping_email TEXT,
              shipping_phone TEXT,
              subscription_plan TEXT,
              subscription_status TEXT,
              subscription_renewal_date TEXT,
              payment_methods_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trade_offers (
              offer_id TEXT PRIMARY KEY,
              target_listing_id TEXT NOT NULL,
              offered_listing_id TEXT NOT NULL,
              offered_listing_ids_json TEXT NOT NULL DEFAULT '[]',
              from_subject TEXT NOT NULL,
              to_subject TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              message TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_payment_methods (
              payment_method_id TEXT PRIMARY KEY,
              owner_subject TEXT NOT NULL,
              provider TEXT NOT NULL,
              method_type TEXT NOT NULL,
              label TEXT,
              last4 TEXT,
              brand TEXT,
              exp_month INTEGER,
              exp_year INTEGER,
              email TEXT,
              is_default INTEGER NOT NULL DEFAULT 0,
              provider_token TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_billing_profiles (
              owner_subject TEXT PRIMARY KEY,
              stripe_customer_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trade_shipments (
              shipment_id TEXT PRIMARY KEY,
              offer_id TEXT NOT NULL,
              from_subject TEXT NOT NULL,
              to_subject TEXT NOT NULL,
              from_listing_id TEXT NOT NULL,
              to_listing_id TEXT NOT NULL,
              from_name TEXT,
              from_address_line1 TEXT,
              from_address_line2 TEXT,
              from_city TEXT,
              from_state TEXT,
              from_postal_code TEXT,
              from_country TEXT,
              to_name TEXT,
              to_address_line1 TEXT,
              to_address_line2 TEXT,
              to_city TEXT,
              to_state TEXT,
              to_postal_code TEXT,
              to_country TEXT,
              carrier TEXT NOT NULL DEFAULT 'USPS',
              service_level TEXT NOT NULL DEFAULT 'Priority Mail',
              tracking_number TEXT,
              label_url TEXT,
              status TEXT NOT NULL DEFAULT 'label_created',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ]
        for stmt in statements:
            self.execute(stmt)
        for alter in (
            "ALTER TABLE listings ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE listings ADD COLUMN status TEXT NOT NULL DEFAULT 'Review'",
            "ALTER TABLE listings ADD COLUMN size TEXT",
            "ALTER TABLE listings ADD COLUMN description TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE user_profiles ADD COLUMN gender TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_full_name TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_address_line1 TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_address_line2 TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_city TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_state TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_postal_code TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_country TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_email TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_phone TEXT",
            "ALTER TABLE user_profiles ADD COLUMN subscription_plan TEXT",
            "ALTER TABLE user_profiles ADD COLUMN subscription_status TEXT",
            "ALTER TABLE user_profiles ADD COLUMN subscription_renewal_date TEXT",
            "ALTER TABLE user_profiles ADD COLUMN payment_methods_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE trade_offers ADD COLUMN offered_listing_ids_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE user_payment_methods ADD COLUMN email TEXT",
        ):
            try:
                self.execute(alter)
            except Exception:
                if self._pg is not None:
                    self._pg.rollback()
                pass
        self.commit()

    def get_listing_by_id(self, listing_id: str) -> dict | None:
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at "
            f"FROM listings WHERE listing_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (listing_id,)).fetchone()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (listing_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        return self._listing_row_to_dict(row)

    def create_trade_offer(
        self,
        *,
        offer_id: str,
        target_listing_id: str,
        offered_listing_id: str,
        offered_listing_ids: list[str],
        from_subject: str,
        to_subject: str,
        message: str,
    ) -> dict:
        now = utc_now_iso()
        self.execute(
            f"""INSERT INTO trade_offers
            (offer_id, target_listing_id, offered_listing_id, offered_listing_ids_json, from_subject, to_subject, status, message, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                offer_id,
                target_listing_id,
                offered_listing_id,
                json.dumps(offered_listing_ids),
                from_subject,
                to_subject,
                "pending",
                message or "",
                now,
                now,
            ),
        )
        self.commit()
        return {
            "offer_id": offer_id,
            "target_listing_id": target_listing_id,
            "offered_listing_id": offered_listing_id,
            "offered_listing_ids": offered_listing_ids,
            "from_subject": from_subject,
            "to_subject": to_subject,
            "status": "pending",
            "message": message or "",
            "created_at": now,
            "updated_at": now,
        }

    def list_incoming_trade_offers(self, to_subject: str, limit: int = 50, status: str | None = None) -> list[dict]:
        safe_limit = max(1, min(int(limit), 200))
        if status:
            query = (
                f"SELECT offer_id, target_listing_id, offered_listing_id, from_subject, to_subject, status, message, created_at, updated_at "
                f", offered_listing_ids_json "
                f"FROM trade_offers WHERE to_subject = {self.param} AND status = {self.param} "
                f"ORDER BY created_at DESC LIMIT {self.param}"
            )
            params = (to_subject, status, safe_limit)
        else:
            query = (
                f"SELECT offer_id, target_listing_id, offered_listing_id, from_subject, to_subject, status, message, created_at, updated_at "
                f", offered_listing_ids_json "
                f"FROM trade_offers WHERE to_subject = {self.param} "
                f"ORDER BY created_at DESC LIMIT {self.param}"
            )
            params = (to_subject, safe_limit)

        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, params).fetchall()
        else:
            cur = self._pg.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()

        offers: list[dict] = []
        for row in rows:
            if isinstance(row, sqlite3.Row):
                data = dict(row)
            else:
                keys = ["offer_id", "target_listing_id", "offered_listing_id", "from_subject", "to_subject", "status", "message", "created_at", "updated_at", "offered_listing_ids_json"]
                data = {k: row[idx] for idx, k in enumerate(keys)}
            try:
                offered_ids = json.loads(data.get("offered_listing_ids_json") or "[]")
                if not isinstance(offered_ids, list):
                    offered_ids = []
            except Exception:
                offered_ids = []
            offered_ids = [x for x in offered_ids if isinstance(x, str) and x.strip()]
            if not offered_ids and isinstance(data.get("offered_listing_id"), str):
                offered_ids = [data["offered_listing_id"]]
            data["offered_listing_ids"] = offered_ids
            offers.append(data)
        return offers

    def set_trade_offer_status(self, *, offer_id: str, to_subject: str, status: str) -> dict | None:
        now = utc_now_iso()
        sql = (
            f"UPDATE trade_offers SET status = {self.param}, updated_at = {self.param} "
            f"WHERE offer_id = {self.param} AND to_subject = {self.param}"
        )
        params = (status, now, offer_id, to_subject)
        changed = False
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
        if not changed:
            return None
        self.commit()
        query = (
            f"SELECT offer_id, target_listing_id, offered_listing_id, from_subject, to_subject, status, message, created_at, updated_at, offered_listing_ids_json "
            f"FROM trade_offers WHERE offer_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (offer_id,)).fetchone()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (offer_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            data = dict(row)
            try:
                offered_ids = json.loads(data.get("offered_listing_ids_json") or "[]")
                if not isinstance(offered_ids, list):
                    offered_ids = []
            except Exception:
                offered_ids = []
            offered_ids = [x for x in offered_ids if isinstance(x, str) and x.strip()]
            if not offered_ids and isinstance(data.get("offered_listing_id"), str):
                offered_ids = [data["offered_listing_id"]]
            data["offered_listing_ids"] = offered_ids
            return data
        keys = ["offer_id", "target_listing_id", "offered_listing_id", "from_subject", "to_subject", "status", "message", "created_at", "updated_at", "offered_listing_ids_json"]
        data = {k: row[idx] for idx, k in enumerate(keys)}
        try:
            offered_ids = json.loads(data.get("offered_listing_ids_json") or "[]")
            if not isinstance(offered_ids, list):
                offered_ids = []
        except Exception:
            offered_ids = []
        offered_ids = [x for x in offered_ids if isinstance(x, str) and x.strip()]
        if not offered_ids and isinstance(data.get("offered_listing_id"), str):
            offered_ids = [data["offered_listing_id"]]
        data["offered_listing_ids"] = offered_ids
        return data

    def mark_listings_traded(self, listing_ids: list[str]) -> None:
        if not listing_ids:
            return
        unique_ids = [x for x in dict.fromkeys(listing_ids) if isinstance(x, str) and x.strip()]
        if not unique_ids:
            return
        placeholders = ", ".join([self.param] * len(unique_ids))
        sql = f"UPDATE listings SET status = {self.param} WHERE listing_id IN ({placeholders})"
        params = tuple(["Traded", *unique_ids])
        self.execute(sql, params)
        self.commit()

    def get_trade_offer_by_id(self, offer_id: str) -> dict | None:
        query = (
            f"SELECT offer_id, target_listing_id, offered_listing_id, from_subject, to_subject, status, message, created_at, updated_at, offered_listing_ids_json "
            f"FROM trade_offers WHERE offer_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (offer_id,)).fetchone()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (offer_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = ["offer_id", "target_listing_id", "offered_listing_id", "from_subject", "to_subject", "status", "message", "created_at", "updated_at", "offered_listing_ids_json"]
            data = {k: row[idx] for idx, k in enumerate(keys)}
        try:
            offered_ids = json.loads(data.get("offered_listing_ids_json") or "[]")
            if not isinstance(offered_ids, list):
                offered_ids = []
        except Exception:
            offered_ids = []
        offered_ids = [x for x in offered_ids if isinstance(x, str) and x.strip()]
        if not offered_ids and isinstance(data.get("offered_listing_id"), str):
            offered_ids = [data["offered_listing_id"]]
        data["offered_listing_ids"] = offered_ids
        return data

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

    def get_image_id_by_storage_uri(self, storage_uri: str) -> str | None:
        query = f"SELECT image_id FROM images WHERE storage_uri = {self.param} ORDER BY created_at ASC LIMIT 1"
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (storage_uri,)).fetchone()
            if not row:
                return None
            return row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg.cursor()
        cur.execute(query, (storage_uri,))
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
        description: str,
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
             estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param},
                    {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
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
                description or "",
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
            f"size, estimated_value, city, {image_select}, {images_select}, description, wants, tags_json, source_item_id, {analysis_select}, status, created_at "
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
            f"size, estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at "
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
        description: str,
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
                description = {self.param},
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
            description or "",
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

    def migrate_listing_media_urls_to_http(self) -> int:
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(
                "SELECT listing_id, image, images_json, source_item_id, analysis_json, description, wants FROM listings"
            ).fetchall()
        else:
            cur = self._pg.cursor()
            cur.execute("SELECT listing_id, image, images_json, source_item_id, analysis_json, description, wants FROM listings")
            rows = cur.fetchall()
            cur.close()

        def resolve(url: object, source_item_id: str | None) -> str | None:
            if not isinstance(url, str):
                return None
            s = url.strip()
            if not s or s.startswith("blob:") or s.startswith("data:"):
                return None
            if s.startswith("http://") or s.startswith("https://") or s.startswith("/"):
                return s
            if s.startswith("s3://"):
                image_id = self.get_image_id_by_storage_uri(s)
                if isinstance(image_id, str) and image_id.strip():
                    return f"/v1/images/{image_id}"
            return None

        changed = 0
        for row in rows:
            if isinstance(row, sqlite3.Row):
                listing_id = row["listing_id"]
                image = row["image"]
                images_json = row["images_json"]
                source_item_id = row["source_item_id"]
                analysis_json = row["analysis_json"]
                description = row["description"]
                wants = row["wants"]
            else:
                listing_id, image, images_json, source_item_id, analysis_json, description, wants = row[0], row[1], row[2], row[3], row[4], row[5], row[6]

            try:
                images = json.loads(images_json) if images_json else []
            except Exception:
                images = []
            if not isinstance(images, list):
                images = []

            normalized_images: list[str] = []
            for url in images:
                resolved = resolve(url, source_item_id)
                if resolved:
                    normalized_images.append(resolved)
            normalized_image = resolve(image, source_item_id)
            if not normalized_images and normalized_image:
                normalized_images = [normalized_image]
            if not normalized_image and normalized_images:
                normalized_image = normalized_images[0]

            normalized_description = (description or "").strip() if isinstance(description, str) else ""
            if not normalized_description and analysis_json:
                try:
                    analysis = json.loads(analysis_json)
                except Exception:
                    analysis = None
                if isinstance(analysis, dict):
                    profile = analysis.get("item_profile")
                    if isinstance(profile, dict):
                        mid = profile.get("model_identification")
                        if isinstance(mid, dict):
                            name = mid.get("name")
                            attrs = mid.get("attributes")
                            parts = []
                            if isinstance(name, str) and name.strip():
                                parts.append(name.strip())
                            if isinstance(attrs, list):
                                clean_attrs = [a.strip() for a in attrs if isinstance(a, str) and a.strip()]
                                if clean_attrs:
                                    parts.append(f"Key details: {', '.join(clean_attrs[:6])}.")
                            if parts:
                                normalized_description = ". ".join(parts).replace("..", ".")
            wants_text = wants.strip() if isinstance(wants, str) else ""
            if not normalized_description and wants_text and wants_text != "No description provided.":
                normalized_description = wants_text

            old_images = images if isinstance(images, list) else []
            old_desc = description if isinstance(description, str) else ""
            if (image or None) == normalized_image and old_images == normalized_images and old_desc == normalized_description:
                continue

            self.execute(
                f"UPDATE listings SET image = {self.param}, images_json = {self.param}, description = {self.param} WHERE listing_id = {self.param}",
                (normalized_image, json.dumps(normalized_images), normalized_description, listing_id),
            )
            changed += 1

        if changed:
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
                "description",
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

        try:
            images = json.loads(data.get("images_json") or "[]")
        except Exception:
            images = []
        safe_images = []
        for value in images:
            if not isinstance(value, str):
                continue
            if value.startswith("data:") or value.startswith("blob:"):
                continue
            safe_images.append(value)

        description = (data.get("description") or "").strip() if isinstance(data.get("description"), str) else ""
        wants = data["wants"]
        if not description and isinstance(wants, str):
            wants_text = wants.strip()
            if wants_text and wants_text != "No description provided.":
                description = wants_text

        try:
            estimated_value = float(data["estimated_value"])
        except Exception:
            estimated_value = 0.0
        try:
            tags = json.loads(data.get("tags_json") or "[]")
            if not isinstance(tags, list):
                tags = []
        except Exception:
            tags = []
        try:
            analysis = json.loads(data["analysis_json"]) if data.get("analysis_json") else None
        except Exception:
            analysis = None

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
            "estimated_value": estimated_value,
            "city": data["city"],
            "image": image,
            "images": safe_images,
            "description": description,
            "wants": wants,
            "tags": tags,
            "source_item_id": data["source_item_id"],
            "analysis": analysis,
            "status": data.get("status") or "Review",
            "created_at": data["created_at"],
        }

    def get_user_profile_quiz(self, owner_subject: str) -> dict | None:
        query = (
            f"SELECT owner_subject, gender, tops_size, dresses_size, bottoms_size, shoes_size, "
            f"category_preferences_json, shipping_full_name, shipping_address_line1, shipping_address_line2, "
            f"shipping_city, shipping_state, shipping_postal_code, shipping_country, shipping_email, shipping_phone, "
            f"subscription_plan, subscription_status, subscription_renewal_date, payment_methods_json, "
            f"created_at, updated_at "
            f"FROM user_profiles WHERE owner_subject = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (owner_subject,)).fetchone()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (owner_subject,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = [
                "owner_subject", "gender", "tops_size", "dresses_size", "bottoms_size", "shoes_size",
                "category_preferences_json", "shipping_full_name", "shipping_address_line1", "shipping_address_line2",
                "shipping_city", "shipping_state", "shipping_postal_code", "shipping_country",
                "shipping_email", "shipping_phone",
                "subscription_plan", "subscription_status", "subscription_renewal_date", "payment_methods_json",
                "created_at", "updated_at",
            ]
            data = {k: row[idx] for idx, k in enumerate(keys)}
        try:
            prefs = json.loads(data.get("category_preferences_json") or "[]")
            if not isinstance(prefs, list):
                prefs = []
        except Exception:
            prefs = []
        try:
            payment_methods = json.loads(data.get("payment_methods_json") or "[]")
            if not isinstance(payment_methods, list):
                payment_methods = []
        except Exception:
            payment_methods = []
        return {
            "owner_subject": data["owner_subject"],
            "gender": data.get("gender"),
            "tops_size": data.get("tops_size"),
            "dresses_size": data.get("dresses_size"),
            "bottoms_size": data.get("bottoms_size"),
            "shoes_size": data.get("shoes_size"),
            "category_preferences": [p for p in prefs if isinstance(p, str)],
            "shipping_full_name": data.get("shipping_full_name"),
            "shipping_address_line1": data.get("shipping_address_line1"),
            "shipping_address_line2": data.get("shipping_address_line2"),
            "shipping_city": data.get("shipping_city"),
            "shipping_state": data.get("shipping_state"),
            "shipping_postal_code": data.get("shipping_postal_code"),
            "shipping_country": data.get("shipping_country"),
            "subscription_plan": data.get("subscription_plan"),
            "subscription_status": data.get("subscription_status"),
            "subscription_renewal_date": data.get("subscription_renewal_date"),
            "payment_methods": [m for m in payment_methods if isinstance(m, str)],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }

    def upsert_user_profile_quiz(
        self,
        *,
        owner_subject: str,
        gender: str | None,
        tops_size: str | None,
        dresses_size: str | None,
        bottoms_size: str | None,
        shoes_size: str | None,
        category_preferences: list[str],
        shipping_full_name: str | None,
        shipping_address_line1: str | None,
        shipping_address_line2: str | None,
        shipping_city: str | None,
        shipping_state: str | None,
        shipping_postal_code: str | None,
        shipping_country: str | None,
        shipping_email: str | None,
        shipping_phone: str | None,
        subscription_plan: str | None,
        subscription_status: str | None,
        subscription_renewal_date: str | None,
        payment_methods: list[str],
    ) -> dict:
        now = utc_now_iso()
        cats = json.dumps([c for c in category_preferences if isinstance(c, str)])
        payment_methods_json = json.dumps([m for m in payment_methods if isinstance(m, str) and m.strip()])
        if self._sqlite_conn is not None:
            self._sqlite_conn.execute(
                """INSERT INTO user_profiles
                (owner_subject, gender, tops_size, dresses_size, bottoms_size, shoes_size, category_preferences_json, shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_postal_code, shipping_country, shipping_email, shipping_phone, subscription_plan, subscription_status, subscription_renewal_date, payment_methods_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_subject) DO UPDATE SET
                  gender=excluded.gender,
                  tops_size=excluded.tops_size,
                  dresses_size=excluded.dresses_size,
                  bottoms_size=excluded.bottoms_size,
                  shoes_size=excluded.shoes_size,
                  category_preferences_json=excluded.category_preferences_json,
                  shipping_full_name=excluded.shipping_full_name,
                  shipping_address_line1=excluded.shipping_address_line1,
                  shipping_address_line2=excluded.shipping_address_line2,
                  shipping_city=excluded.shipping_city,
                  shipping_state=excluded.shipping_state,
                  shipping_postal_code=excluded.shipping_postal_code,
                  shipping_country=excluded.shipping_country,
                  shipping_email=excluded.shipping_email,
                  shipping_phone=excluded.shipping_phone,
                  subscription_plan=excluded.subscription_plan,
                  subscription_status=excluded.subscription_status,
                  subscription_renewal_date=excluded.subscription_renewal_date,
                  payment_methods_json=excluded.payment_methods_json,
                  updated_at=excluded.updated_at
                """,
                (
                    owner_subject, gender, tops_size, dresses_size, bottoms_size, shoes_size, cats,
                    shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state,
                    shipping_postal_code, shipping_country, shipping_email, shipping_phone, subscription_plan, subscription_status, subscription_renewal_date,
                    payment_methods_json, now, now,
                ),
            )
            self._sqlite_conn.commit()
        else:
            cur = self._pg.cursor()
            cur.execute(
                f"""INSERT INTO user_profiles
                (owner_subject, gender, tops_size, dresses_size, bottoms_size, shoes_size, category_preferences_json, shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_postal_code, shipping_country, shipping_email, shipping_phone, subscription_plan, subscription_status, subscription_renewal_date, payment_methods_json, created_at, updated_at)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT (owner_subject) DO UPDATE SET
                  gender=EXCLUDED.gender,
                  tops_size=EXCLUDED.tops_size,
                  dresses_size=EXCLUDED.dresses_size,
                  bottoms_size=EXCLUDED.bottoms_size,
                  shoes_size=EXCLUDED.shoes_size,
                  category_preferences_json=EXCLUDED.category_preferences_json,
                  shipping_full_name=EXCLUDED.shipping_full_name,
                  shipping_address_line1=EXCLUDED.shipping_address_line1,
                  shipping_address_line2=EXCLUDED.shipping_address_line2,
                  shipping_city=EXCLUDED.shipping_city,
                  shipping_state=EXCLUDED.shipping_state,
                  shipping_postal_code=EXCLUDED.shipping_postal_code,
                  shipping_country=EXCLUDED.shipping_country,
                  shipping_email=EXCLUDED.shipping_email,
                  shipping_phone=EXCLUDED.shipping_phone,
                  subscription_plan=EXCLUDED.subscription_plan,
                  subscription_status=EXCLUDED.subscription_status,
                  subscription_renewal_date=EXCLUDED.subscription_renewal_date,
                  payment_methods_json=EXCLUDED.payment_methods_json,
                  updated_at=EXCLUDED.updated_at
                """,
                (
                    owner_subject, gender, tops_size, dresses_size, bottoms_size, shoes_size, cats,
                    shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state,
                    shipping_postal_code, shipping_country, shipping_email, shipping_phone, subscription_plan, subscription_status, subscription_renewal_date,
                    payment_methods_json, now, now,
                ),
            )
            cur.close()
            self._pg.commit()
        return self.get_user_profile_quiz(owner_subject) or {
            "owner_subject": owner_subject,
            "gender": gender,
            "tops_size": tops_size,
            "dresses_size": dresses_size,
            "bottoms_size": bottoms_size,
            "shoes_size": shoes_size,
            "category_preferences": category_preferences,
            "shipping_full_name": shipping_full_name,
            "shipping_address_line1": shipping_address_line1,
            "shipping_address_line2": shipping_address_line2,
            "shipping_city": shipping_city,
            "shipping_state": shipping_state,
            "shipping_postal_code": shipping_postal_code,
            "shipping_country": shipping_country,
            "subscription_plan": subscription_plan,
            "subscription_status": subscription_status,
            "subscription_renewal_date": subscription_renewal_date,
            "payment_methods": [m for m in payment_methods if isinstance(m, str) and m.strip()],
            "created_at": now,
            "updated_at": now,
        }

    def list_payment_methods(self, owner_subject: str) -> list[dict]:
        query = (
            f"SELECT payment_method_id, owner_subject, provider, method_type, label, last4, brand, exp_month, exp_year, email, is_default, created_at, updated_at "
            f"FROM user_payment_methods WHERE owner_subject = {self.param} ORDER BY is_default DESC, created_at DESC"
        )
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (owner_subject,)).fetchall()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (owner_subject,))
            rows = cur.fetchall()
            cur.close()
        out: list[dict] = []
        keys = [
            "payment_method_id", "owner_subject", "provider", "method_type", "label", "last4",
            "brand", "exp_month", "exp_year", "email", "is_default", "created_at", "updated_at",
        ]
        for row in rows:
            data = dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)}
            out.append({
                "payment_method_id": data.get("payment_method_id"),
                "owner_subject": data.get("owner_subject"),
                "provider": data.get("provider"),
                "method_type": data.get("method_type"),
                "label": data.get("label"),
                "last4": data.get("last4"),
                "brand": data.get("brand"),
                "exp_month": data.get("exp_month"),
                "exp_year": data.get("exp_year"),
                "email": data.get("email"),
                "is_default": bool(data.get("is_default")),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            })
        return out

    def create_payment_method(
        self,
        *,
        payment_method_id: str,
        owner_subject: str,
        provider: str,
        method_type: str,
        label: str | None,
        last4: str | None,
        brand: str | None,
        exp_month: int | None,
        exp_year: int | None,
        email: str | None,
        provider_token: str | None,
        is_default: bool,
    ) -> dict:
        now = utc_now_iso()
        if is_default:
            self.execute(f"UPDATE user_payment_methods SET is_default = 0 WHERE owner_subject = {self.param}", (owner_subject,))
        self.execute(
            f"""INSERT INTO user_payment_methods
            (payment_method_id, owner_subject, provider, method_type, label, last4, brand, exp_month, exp_year, email, is_default, provider_token, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                payment_method_id, owner_subject, provider, method_type, label, last4, brand,
                exp_month, exp_year, email, 1 if is_default else 0, provider_token, now, now,
            ),
        )
        self.commit()
        methods = self.list_payment_methods(owner_subject)
        return next((m for m in methods if m.get("payment_method_id") == payment_method_id), {
            "payment_method_id": payment_method_id,
            "owner_subject": owner_subject,
            "provider": provider,
            "method_type": method_type,
            "label": label,
            "last4": last4,
            "brand": brand,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "email": email,
            "is_default": is_default,
            "created_at": now,
            "updated_at": now,
        })

    def delete_payment_method(self, owner_subject: str, payment_method_id: str) -> bool:
        query = f"DELETE FROM user_payment_methods WHERE owner_subject = {self.param} AND payment_method_id = {self.param}"
        if self._sqlite_conn is not None:
            cur = self._sqlite_conn.execute(query, (owner_subject, payment_method_id))
            deleted = cur.rowcount > 0
            self._sqlite_conn.commit()
            return deleted
        cur = self._pg.cursor()
        cur.execute(query, (owner_subject, payment_method_id))
        deleted = cur.rowcount > 0
        cur.close()
        self._pg.commit()
        return deleted

    def set_default_payment_method(self, owner_subject: str, payment_method_id: str) -> dict | None:
        self.execute(f"UPDATE user_payment_methods SET is_default = 0 WHERE owner_subject = {self.param}", (owner_subject,))
        self.execute(
            f"UPDATE user_payment_methods SET is_default = 1, updated_at = {self.param} WHERE owner_subject = {self.param} AND payment_method_id = {self.param}",
            (utc_now_iso(), owner_subject, payment_method_id),
        )
        self.commit()
        methods = self.list_payment_methods(owner_subject)
        return next((m for m in methods if m.get("payment_method_id") == payment_method_id), None)

    def delete_payment_method_by_provider_token(self, owner_subject: str, provider: str, provider_token: str) -> None:
        self.execute(
            f"DELETE FROM user_payment_methods WHERE owner_subject = {self.param} AND provider = {self.param} AND provider_token = {self.param}",
            (owner_subject, provider, provider_token),
        )
        self.commit()

    def get_stripe_customer_id(self, owner_subject: str) -> str | None:
        query = (
            f"SELECT stripe_customer_id FROM user_billing_profiles WHERE owner_subject = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (owner_subject,)).fetchone()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (owner_subject,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            return row.get("stripe_customer_id") or None
        return row[0] if row and row[0] else None

    def set_stripe_customer_id(self, owner_subject: str, stripe_customer_id: str) -> None:
        now = utc_now_iso()
        if self._sqlite_conn is not None:
            self._sqlite_conn.execute(
                """INSERT INTO user_billing_profiles (owner_subject, stripe_customer_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(owner_subject) DO UPDATE SET
                  stripe_customer_id=excluded.stripe_customer_id,
                  updated_at=excluded.updated_at
                """,
                (owner_subject, stripe_customer_id, now, now),
            )
            self._sqlite_conn.commit()
            return
        cur = self._pg.cursor()
        cur.execute(
            f"""INSERT INTO user_billing_profiles (owner_subject, stripe_customer_id, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param})
            ON CONFLICT (owner_subject) DO UPDATE SET
              stripe_customer_id=EXCLUDED.stripe_customer_id,
              updated_at=EXCLUDED.updated_at
            """,
            (owner_subject, stripe_customer_id, now, now),
        )
        cur.close()
        self._pg.commit()

    def list_shipments_for_offer(self, offer_id: str) -> list[dict]:
        query = (
            f"SELECT shipment_id, offer_id, from_subject, to_subject, from_listing_id, to_listing_id, "
            f"from_name, from_address_line1, from_address_line2, from_city, from_state, from_postal_code, from_country, "
            f"to_name, to_address_line1, to_address_line2, to_city, to_state, to_postal_code, to_country, "
            f"carrier, service_level, tracking_number, label_url, status, created_at, updated_at "
            f"FROM trade_shipments WHERE offer_id = {self.param} ORDER BY created_at ASC"
        )
        keys = [
            "shipment_id", "offer_id", "from_subject", "to_subject", "from_listing_id", "to_listing_id",
            "from_name", "from_address_line1", "from_address_line2", "from_city", "from_state", "from_postal_code", "from_country",
            "to_name", "to_address_line1", "to_address_line2", "to_city", "to_state", "to_postal_code", "to_country",
            "carrier", "service_level", "tracking_number", "label_url", "status", "created_at", "updated_at",
        ]
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (offer_id,)).fetchall()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (offer_id,))
            rows = cur.fetchall()
            cur.close()
        out: list[dict] = []
        for row in rows:
            out.append(dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)})
        return out

    def get_trade_shipment_by_id(self, shipment_id: str) -> dict | None:
        query = (
            f"SELECT shipment_id, offer_id, from_subject, to_subject, from_listing_id, to_listing_id, "
            f"from_name, from_address_line1, from_address_line2, from_city, from_state, from_postal_code, from_country, "
            f"to_name, to_address_line1, to_address_line2, to_city, to_state, to_postal_code, to_country, "
            f"carrier, service_level, tracking_number, label_url, status, created_at, updated_at "
            f"FROM trade_shipments WHERE shipment_id = {self.param} LIMIT 1"
        )
        keys = [
            "shipment_id", "offer_id", "from_subject", "to_subject", "from_listing_id", "to_listing_id",
            "from_name", "from_address_line1", "from_address_line2", "from_city", "from_state", "from_postal_code", "from_country",
            "to_name", "to_address_line1", "to_address_line2", "to_city", "to_state", "to_postal_code", "to_country",
            "carrier", "service_level", "tracking_number", "label_url", "status", "created_at", "updated_at",
        ]
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (shipment_id,)).fetchone()
        else:
            cur = self._pg.cursor()
            cur.execute(query, (shipment_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        return dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)}

    def update_trade_shipment_label(
        self,
        *,
        shipment_id: str,
        carrier: str | None = None,
        service_level: str | None = None,
        tracking_number: str | None = None,
        label_url: str | None = None,
        status: str | None = None,
    ) -> dict | None:
        shipment = self.get_trade_shipment_by_id(shipment_id)
        if not shipment:
            return None
        new_carrier = carrier if carrier is not None else shipment.get("carrier")
        new_service = service_level if service_level is not None else shipment.get("service_level")
        new_tracking = tracking_number if tracking_number is not None else shipment.get("tracking_number")
        new_label = label_url if label_url is not None else shipment.get("label_url")
        new_status = status if status is not None else shipment.get("status")
        self.execute(
            f"""UPDATE trade_shipments
            SET carrier = {self.param}, service_level = {self.param}, tracking_number = {self.param}, label_url = {self.param}, status = {self.param}, updated_at = {self.param}
            WHERE shipment_id = {self.param}""",
            (new_carrier, new_service, new_tracking, new_label, new_status, utc_now_iso(), shipment_id),
        )
        self.commit()
        return self.get_trade_shipment_by_id(shipment_id)

    def insert_trade_shipment(
        self,
        *,
        shipment_id: str,
        offer_id: str,
        from_subject: str,
        to_subject: str,
        from_listing_id: str,
        to_listing_id: str,
        from_name: str | None,
        from_address_line1: str | None,
        from_address_line2: str | None,
        from_city: str | None,
        from_state: str | None,
        from_postal_code: str | None,
        from_country: str | None,
        to_name: str | None,
        to_address_line1: str | None,
        to_address_line2: str | None,
        to_city: str | None,
        to_state: str | None,
        to_postal_code: str | None,
        to_country: str | None,
        carrier: str,
        service_level: str,
        tracking_number: str,
        label_url: str,
        status: str,
    ) -> dict:
        now = utc_now_iso()
        self.execute(
            f"""INSERT INTO trade_shipments
            (shipment_id, offer_id, from_subject, to_subject, from_listing_id, to_listing_id, from_name, from_address_line1, from_address_line2, from_city, from_state, from_postal_code, from_country, to_name, to_address_line1, to_address_line2, to_city, to_state, to_postal_code, to_country, carrier, service_level, tracking_number, label_url, status, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                shipment_id, offer_id, from_subject, to_subject, from_listing_id, to_listing_id,
                from_name, from_address_line1, from_address_line2, from_city, from_state, from_postal_code, from_country,
                to_name, to_address_line1, to_address_line2, to_city, to_state, to_postal_code, to_country,
                carrier, service_level, tracking_number, label_url, status, now, now,
            ),
        )
        self.commit()
        return {
            "shipment_id": shipment_id,
            "offer_id": offer_id,
            "from_subject": from_subject,
            "to_subject": to_subject,
            "from_listing_id": from_listing_id,
            "to_listing_id": to_listing_id,
            "from_name": from_name,
            "from_address_line1": from_address_line1,
            "from_address_line2": from_address_line2,
            "from_city": from_city,
            "from_state": from_state,
            "from_postal_code": from_postal_code,
            "from_country": from_country,
            "to_name": to_name,
            "to_address_line1": to_address_line1,
            "to_address_line2": to_address_line2,
            "to_city": to_city,
            "to_state": to_state,
            "to_postal_code": to_postal_code,
            "to_country": to_country,
            "carrier": carrier,
            "service_level": service_level,
            "tracking_number": tracking_number,
            "label_url": label_url,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }
