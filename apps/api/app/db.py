from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlparse


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_public_listing_image_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urlparse(s)
        hostname = (parsed.hostname or "").lower()
        if parsed.path.startswith("/v1/images/") and (
            hostname.endswith(".elb.amazonaws.com")
            or hostname in {"jouft.com", "www.jouft.com", "api.jouft.com"}
        ):
            return parsed.path
        return s
    if s.startswith("/"):
        return s
    return None


def listing_image_dedupe_key(value: object) -> str:
    normalized = normalize_public_listing_image_url(value)
    return normalized or str(value or "").strip()


def is_generic_trade_note(value: object) -> bool:
    normalized = str(value or "").strip().lower().rstrip(".! ")
    return normalized in {
        "open to similar-value offers",
        "open to similar value offers",
        "no description provided",
    }


def _image_id_from_api_url(value: object) -> str | None:
    normalized = normalize_public_listing_image_url(value)
    if not isinstance(normalized, str):
        return None
    marker = "/v1/images/"
    if marker not in normalized:
        return None
    image_id = normalized.split(marker, 1)[1].split("/", 1)[0].strip()
    return image_id or None


def _remove_analysis_uploads_when_display_gallery_exists(images: list[str], analysis: object) -> list[str]:
    if not images or not isinstance(analysis, dict):
        return images
    uploaded_images = analysis.get("uploaded_images")
    if not isinstance(uploaded_images, list):
        return images

    analysis_keys: set[str] = set()
    for entry in uploaded_images:
        if not isinstance(entry, dict):
            continue
        image_url = entry.get("image_url")
        image_id = entry.get("image_id")
        storage_uri = entry.get("storage_uri")
        for value in (
            image_url,
            f"/v1/images/{image_id.strip()}" if isinstance(image_id, str) and image_id.strip() else None,
            storage_uri,
        ):
            key = listing_image_dedupe_key(value)
            if key:
                analysis_keys.add(key)

    if not analysis_keys:
        return images
    display_images = [url for url in images if listing_image_dedupe_key(url) not in analysis_keys]
    return display_images or images


def _upload_path_from_public_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    path = urlparse(s).path if s.startswith(("http://", "https://")) else s
    marker = "/uploads/"
    if marker not in path:
        return None
    rel = path.split(marker, 1)[1].strip("/")
    return f".data/uploads/{rel}" if rel else None


def _image_id_from_upload_path(value: object) -> str | None:
    storage_uri = _upload_path_from_public_url(value)
    if not storage_uri:
        return None
    stem = PurePosixPath(storage_uri).stem.strip()
    return stem or None


@dataclass(slots=True)
class PersistedImage:
    image_id: str
    item_id: str
    storage_uri: str
    filename: str
    role_hint: str | None
    content_hash: str | None = None


class Database:
    def __init__(self, url: str):
        self.url = url
        self._sqlite_conn: sqlite3.Connection | None = None
        self._sqlite_lock = threading.RLock()
        self._pg = None
        if url.startswith("sqlite:///"):
            path = url.replace("sqlite:///", "", 1)
            self._sqlite_conn = sqlite3.connect(path, check_same_thread=False)
            self._sqlite_conn.row_factory = sqlite3.Row
            self.param = "?"
        elif url.startswith("postgresql://"):
            self._connect_pg()
            self.param = "%s"
        else:
            raise ValueError(f"Unsupported DATABASE_URL: {url}")

    def _connect_pg(self) -> None:
        try:
            import psycopg
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for PostgreSQL DATABASE_URL") from exc
        self._pg = psycopg.connect(self.url, connect_timeout=5)
        cur = self._pg.cursor()
        try:
            cur.execute("SET lock_timeout = '1500ms'")
            cur.execute("SET statement_timeout = '5000ms'")
            self._pg.commit()
        except Exception:
            self._pg.rollback()
            raise
        finally:
            cur.close()

    def _ensure_pg_connection(self):
        if self._sqlite_conn is not None:
            return None
        if self._pg is None or bool(getattr(self._pg, "closed", False)):
            self._connect_pg()
        return self._pg

    def _pg_cursor(self):
        conn = self._ensure_pg_connection()
        try:
            return conn.cursor()
        except Exception:
            self._connect_pg()
            return self._pg.cursor()

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
              content_hash TEXT,
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
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
              owner_subject TEXT PRIMARY KEY,
              first_name TEXT,
              last_name TEXT,
              email TEXT,
              gender TEXT,
              birthday TEXT,
              tops_size TEXT,
              dresses_size TEXT,
              bottoms_size TEXT,
              shoes_size TEXT,
              category_preferences_json TEXT NOT NULL DEFAULT '[]',
              style_descriptors_json TEXT NOT NULL DEFAULT '[]',
              jouft_goals_json TEXT NOT NULL DEFAULT '[]',
              shipping_full_name TEXT,
              shipping_address_line1 TEXT,
              shipping_address_line2 TEXT,
              shipping_city TEXT,
              shipping_state TEXT,
              shipping_postal_code TEXT,
              shipping_country TEXT,
              shipping_email TEXT,
              shipping_phone TEXT,
              shipping_addresses_json TEXT NOT NULL DEFAULT '[]',
              subscription_plan TEXT,
              subscription_billing_cycle TEXT,
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
              selected_offered_listing_id TEXT,
              from_subject TEXT NOT NULL,
              to_subject TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              accepted_by_from INTEGER NOT NULL DEFAULT 0,
              accepted_by_to INTEGER NOT NULL DEFAULT 0,
              from_receive_address_json TEXT,
              to_receive_address_json TEXT,
              message TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trade_matches (
              match_id TEXT PRIMARY KEY,
              viewer_subject TEXT NOT NULL,
              target_listing_id TEXT NOT NULL,
              candidate_listing_id TEXT NOT NULL,
              score REAL NOT NULL,
              confidence REAL NOT NULL,
              rationale TEXT NOT NULL,
              risk_flags_json TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'suggested',
              agent_version TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(viewer_subject, target_listing_id, candidate_listing_id)
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
            CREATE TABLE IF NOT EXISTS user_client_state (
              owner_subject TEXT PRIMARY KEY,
              alert_preferences_json TEXT NOT NULL DEFAULT '{}',
              liked_listing_ids_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_notifications (
              notification_id TEXT PRIMARY KEY,
              owner_subject TEXT NOT NULL,
              actor_subject TEXT,
              type TEXT NOT NULL,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              entity_id TEXT,
              action_tab TEXT,
              created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_billing_profiles (
              owner_subject TEXT PRIMARY KEY,
              stripe_customer_id TEXT,
              stripe_subscription_id TEXT,
              subscription_plan TEXT,
              subscription_billing_cycle TEXT,
              subscription_status TEXT,
              subscription_renewal_date TEXT,
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
              tracking_status TEXT,
              tracking_status_details TEXT,
              tracking_status_updated_at TEXT,
              tracking_eta TEXT,
              tracking_history_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ]
        for stmt in statements:
            self.execute(stmt)
        # PostgreSQL runs DDL inside transactions by default.
        # Commit base CREATE TABLE statements first so a later optional ALTER
        # failure cannot roll back newly created tables.
        self.commit()
        for alter in (
            "ALTER TABLE images ADD COLUMN content_hash TEXT",
            "ALTER TABLE listings ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE listings ADD COLUMN status TEXT NOT NULL DEFAULT 'Review'",
            "ALTER TABLE listings ADD COLUMN size TEXT",
            "ALTER TABLE listings ADD COLUMN description TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE listings ADD COLUMN updated_at TEXT",
            "ALTER TABLE user_profiles ADD COLUMN gender TEXT",
            "ALTER TABLE user_profiles ADD COLUMN first_name TEXT",
            "ALTER TABLE user_profiles ADD COLUMN last_name TEXT",
            "ALTER TABLE user_profiles ADD COLUMN email TEXT",
            "ALTER TABLE user_profiles ADD COLUMN birthday TEXT",
            "ALTER TABLE user_profiles ADD COLUMN style_descriptors_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE user_profiles ADD COLUMN jouft_goals_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE user_profiles ADD COLUMN shipping_full_name TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_address_line1 TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_address_line2 TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_city TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_state TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_postal_code TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_country TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_email TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_phone TEXT",
            "ALTER TABLE user_profiles ADD COLUMN shipping_addresses_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE user_profiles ADD COLUMN subscription_plan TEXT",
            "ALTER TABLE user_profiles ADD COLUMN subscription_billing_cycle TEXT",
            "ALTER TABLE user_profiles ADD COLUMN subscription_status TEXT",
            "ALTER TABLE user_profiles ADD COLUMN subscription_renewal_date TEXT",
            "ALTER TABLE user_profiles ADD COLUMN payment_methods_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE trade_offers ADD COLUMN offered_listing_ids_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE trade_offers ADD COLUMN selected_offered_listing_id TEXT",
            "ALTER TABLE trade_offers ADD COLUMN accepted_by_from INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE trade_offers ADD COLUMN accepted_by_to INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE trade_offers ADD COLUMN from_receive_address_json TEXT",
            "ALTER TABLE trade_offers ADD COLUMN to_receive_address_json TEXT",
            "ALTER TABLE user_payment_methods ADD COLUMN email TEXT",
            "ALTER TABLE user_billing_profiles ADD COLUMN stripe_subscription_id TEXT",
            "ALTER TABLE user_billing_profiles ADD COLUMN subscription_plan TEXT",
            "ALTER TABLE user_billing_profiles ADD COLUMN subscription_billing_cycle TEXT",
            "ALTER TABLE user_billing_profiles ADD COLUMN subscription_status TEXT",
            "ALTER TABLE user_billing_profiles ADD COLUMN subscription_renewal_date TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN shipped_at TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN last_ship_reminder_at TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN ship_reminder_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE trade_shipments ADD COLUMN tracking_status TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN tracking_status_details TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN tracking_status_updated_at TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN tracking_eta TEXT",
            "ALTER TABLE trade_shipments ADD COLUMN tracking_history_json TEXT NOT NULL DEFAULT '[]'",
        ):
            try:
                self.execute(alter)
                self.commit()
            except Exception:
                if self._pg is not None:
                    self._pg.rollback()
                pass
        self.commit()

    @staticmethod
    def _normalize_shipping_addresses(raw: object) -> list[dict[str, object]]:
        if not isinstance(raw, list):
            return []
        normalized: list[dict[str, object]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "label": item.get("label") if isinstance(item.get("label"), str) else None,
                "full_name": item.get("full_name") if isinstance(item.get("full_name"), str) else None,
                "address_line1": item.get("address_line1") if isinstance(item.get("address_line1"), str) else None,
                "address_line2": item.get("address_line2") if isinstance(item.get("address_line2"), str) else None,
                "city": item.get("city") if isinstance(item.get("city"), str) else None,
                "state": item.get("state") if isinstance(item.get("state"), str) else None,
                "postal_code": item.get("postal_code") if isinstance(item.get("postal_code"), str) else None,
                "country": item.get("country") if isinstance(item.get("country"), str) else None,
                "is_default": bool(item.get("is_default")),
            })
        return normalized

    def get_listing_by_id(self, listing_id: str) -> dict | None:
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at, COALESCE(updated_at, created_at) AS updated_at "
            f"FROM listings WHERE listing_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (listing_id,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (listing_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        return self._listing_row_to_dict(row)

    def get_listings_by_ids(self, listing_ids: list[str]) -> dict[str, dict]:
        unique_ids = [x for x in dict.fromkeys(listing_ids) if isinstance(x, str) and x.strip()]
        if not unique_ids:
            return {}
        placeholders = ", ".join([self.param] * len(unique_ids))
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at, COALESCE(updated_at, created_at) AS updated_at "
            f"FROM listings WHERE listing_id IN ({placeholders})"
        )
        params = tuple(unique_ids)
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, params).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
        out: dict[str, dict] = {}
        for row in rows:
            listing = self._listing_row_to_dict(row)
            out[str(listing["listing_id"])] = listing
        return out

    def expire_suggested_trade_matches(self, viewer_subject: str) -> int:
        now = utc_now_iso()
        sql = (
            f"UPDATE trade_matches SET status = {self.param}, updated_at = {self.param} "
            f"WHERE viewer_subject = {self.param} AND status = {self.param}"
        )
        params = ("expired", now, viewer_subject, "suggested")
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(sql, params)
                changed_row = self._sqlite_conn.execute("SELECT changes() AS n").fetchone()
            changed = int(changed_row["n"] if isinstance(changed_row, sqlite3.Row) else changed_row[0])
        else:
            cur = self._pg_cursor()
            try:
                cur.execute(sql, params)
                changed = int(cur.rowcount or 0)
            except Exception:
                self._pg.rollback()
                raise
            finally:
                cur.close()
        self.commit()
        return changed

    def upsert_trade_matches(self, records: list[dict]) -> list[dict]:
        if not records:
            return []
        now = utc_now_iso()
        viewer_subject = str(records[0].get("viewer_subject") or "")
        sql = (
            f"INSERT INTO trade_matches "
            f"(match_id, viewer_subject, target_listing_id, candidate_listing_id, score, confidence, rationale, risk_flags_json, status, agent_version, created_at, updated_at) "
            f"VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}) "
            f"ON CONFLICT(viewer_subject, target_listing_id, candidate_listing_id) DO UPDATE SET "
            f"score = excluded.score, confidence = excluded.confidence, rationale = excluded.rationale, "
            f"risk_flags_json = excluded.risk_flags_json, status = excluded.status, agent_version = excluded.agent_version, updated_at = excluded.updated_at"
        )
        for record in records:
            match_id = str(record.get("match_id") or "")
            if not match_id:
                continue
            self.execute(
                sql,
                (
                    match_id,
                    record["viewer_subject"],
                    record["target_listing_id"],
                    record["candidate_listing_id"],
                    float(record["score"]),
                    float(record["confidence"]),
                    record.get("rationale") or "",
                    json.dumps(record.get("risk_flags") or []),
                    record.get("status") or "suggested",
                    record.get("agent_version") or "trade-match-agent-mvp-1",
                    record.get("created_at") or now,
                    now,
                ),
            )
        self.commit()
        if not viewer_subject:
            return []
        return self.list_trade_matches(viewer_subject, limit=len(records), status="suggested")

    def list_trade_matches_by_ids(self, match_ids: list[str]) -> list[dict]:
        unique_ids = [x for x in dict.fromkeys(match_ids) if isinstance(x, str) and x.strip()]
        if not unique_ids:
            return []
        placeholders = ", ".join([self.param] * len(unique_ids))
        query = (
            f"SELECT match_id, viewer_subject, target_listing_id, candidate_listing_id, score, confidence, rationale, "
            f"risk_flags_json, status, agent_version, created_at, updated_at "
            f"FROM trade_matches WHERE match_id IN ({placeholders}) ORDER BY score DESC, updated_at DESC"
        )
        params = tuple(unique_ids)
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, params).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
        return [self._trade_match_row_to_dict(row) for row in rows]

    def list_trade_matches(self, viewer_subject: str, limit: int = 50, status: str | None = "suggested") -> list[dict]:
        safe_limit = max(1, min(int(limit), 200))
        if status:
            query = (
                f"SELECT match_id, viewer_subject, target_listing_id, candidate_listing_id, score, confidence, rationale, "
                f"risk_flags_json, status, agent_version, created_at, updated_at "
                f"FROM trade_matches WHERE viewer_subject = {self.param} AND status = {self.param} "
                f"ORDER BY score DESC, updated_at DESC LIMIT {self.param}"
            )
            params = (viewer_subject, status, safe_limit)
        else:
            query = (
                f"SELECT match_id, viewer_subject, target_listing_id, candidate_listing_id, score, confidence, rationale, "
                f"risk_flags_json, status, agent_version, created_at, updated_at "
                f"FROM trade_matches WHERE viewer_subject = {self.param} "
                f"ORDER BY score DESC, updated_at DESC LIMIT {self.param}"
            )
            params = (viewer_subject, safe_limit)
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, params).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
        return [self._trade_match_row_to_dict(row) for row in rows]

    def set_trade_match_status(self, *, match_id: str, viewer_subject: str, status: str) -> dict | None:
        now = utc_now_iso()
        sql = (
            f"UPDATE trade_matches SET status = {self.param}, updated_at = {self.param} "
            f"WHERE match_id = {self.param} AND viewer_subject = {self.param}"
        )
        params = (status, now, match_id, viewer_subject)
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(sql, params)
                changed_row = self._sqlite_conn.execute("SELECT changes() AS n").fetchone()
            changed = int(changed_row["n"] if isinstance(changed_row, sqlite3.Row) else changed_row[0]) > 0
        else:
            cur = self._pg_cursor()
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
        matches = self.list_trade_matches_by_ids([match_id])
        return matches[0] if matches else None

    def create_trade_offer(
        self,
        *,
        offer_id: str,
        target_listing_id: str,
        offered_listing_id: str,
        offered_listing_ids: list[str],
        from_subject: str,
        to_subject: str,
        from_receive_address: dict | None = None,
        message: str,
    ) -> dict:
        now = utc_now_iso()
        from_receive = self._normalize_offer_address(from_receive_address or {})
        self.execute(
            f"""INSERT INTO trade_offers
            (offer_id, target_listing_id, offered_listing_id, offered_listing_ids_json, selected_offered_listing_id, from_subject, to_subject, status, accepted_by_from, accepted_by_to, from_receive_address_json, to_receive_address_json, message, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                offer_id,
                target_listing_id,
                offered_listing_id,
                json.dumps(offered_listing_ids),
                None,
                from_subject,
                to_subject,
                "pending",
                1,
                0,
                json.dumps(from_receive) if from_receive else None,
                None,
                message or "",
                now,
                now,
            ),
        )
        self.commit()
        return self.get_trade_offer_by_id(offer_id) or {
            "offer_id": offer_id,
            "target_listing_id": target_listing_id,
            "offered_listing_id": offered_listing_id,
            "offered_listing_ids": offered_listing_ids,
            "selected_offered_listing_id": None,
            "from_subject": from_subject,
            "to_subject": to_subject,
            "status": "pending",
            "accepted_by_from": True,
            "accepted_by_to": False,
            "from_receive_address": from_receive,
            "to_receive_address": None,
            "message": message or "",
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _normalize_offer_address(raw: object) -> dict | None:
        if not isinstance(raw, dict):
            return None
        out = {
            "label": raw.get("label") if isinstance(raw.get("label"), str) else None,
            "full_name": raw.get("full_name") if isinstance(raw.get("full_name"), str) else None,
            "address_line1": raw.get("address_line1") if isinstance(raw.get("address_line1"), str) else None,
            "address_line2": raw.get("address_line2") if isinstance(raw.get("address_line2"), str) else None,
            "city": raw.get("city") if isinstance(raw.get("city"), str) else None,
            "state": raw.get("state") if isinstance(raw.get("state"), str) else None,
            "postal_code": raw.get("postal_code") if isinstance(raw.get("postal_code"), str) else None,
            "country": raw.get("country") if isinstance(raw.get("country"), str) else None,
            "is_default": bool(raw.get("is_default")),
        }
        if not any(isinstance(out.get(k), str) and out.get(k) for k in ("full_name", "address_line1", "city", "state", "postal_code", "country")):
            return None
        return out

    def _trade_offer_row_to_dict(self, row) -> dict:
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = [
                "offer_id", "target_listing_id", "offered_listing_id", "selected_offered_listing_id", "from_subject", "to_subject", "status",
                "accepted_by_from", "accepted_by_to", "from_receive_address_json", "to_receive_address_json",
                "message", "created_at", "updated_at", "offered_listing_ids_json",
            ]
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
        try:
            from_receive = self._normalize_offer_address(json.loads(data.get("from_receive_address_json") or "null"))
        except Exception:
            from_receive = None
        try:
            to_receive = self._normalize_offer_address(json.loads(data.get("to_receive_address_json") or "null"))
        except Exception:
            to_receive = None
        status = str(data.get("status") or "pending")
        accepted_by_from = bool(data.get("accepted_by_from"))
        accepted_by_to = bool(data.get("accepted_by_to"))
        if status == "accepted":
            accepted_by_from = True
            accepted_by_to = True
        return {
            "offer_id": data.get("offer_id"),
            "target_listing_id": data.get("target_listing_id"),
            "offered_listing_id": data.get("offered_listing_id"),
            "offered_listing_ids": offered_ids,
            "selected_offered_listing_id": data.get("selected_offered_listing_id") or None,
            "from_subject": data.get("from_subject"),
            "to_subject": data.get("to_subject"),
            "status": status,
            "accepted_by_from": accepted_by_from,
            "accepted_by_to": accepted_by_to,
            "from_receive_address": from_receive,
            "to_receive_address": to_receive,
            "message": data.get("message") or "",
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def _trade_match_row_to_dict(self, row) -> dict:
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = [
                "match_id",
                "viewer_subject",
                "target_listing_id",
                "candidate_listing_id",
                "score",
                "confidence",
                "rationale",
                "risk_flags_json",
                "status",
                "agent_version",
                "created_at",
                "updated_at",
            ]
            data = {k: row[idx] for idx, k in enumerate(keys)}
        try:
            risk_flags = json.loads(data.get("risk_flags_json") or "[]")
            if not isinstance(risk_flags, list):
                risk_flags = []
        except Exception:
            risk_flags = []
        return {
            "match_id": data.get("match_id"),
            "viewer_subject": data.get("viewer_subject"),
            "target_listing_id": data.get("target_listing_id"),
            "candidate_listing_id": data.get("candidate_listing_id"),
            "score": float(data.get("score") or 0),
            "confidence": float(data.get("confidence") or 0),
            "rationale": data.get("rationale") or "",
            "risk_flags": [str(x) for x in risk_flags if isinstance(x, str) and x.strip()],
            "status": data.get("status") or "suggested",
            "agent_version": data.get("agent_version") or "trade-match-agent-mvp-1",
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def list_trade_offers_for_subject(self, subject: str, limit: int = 50, status: str | None = None) -> list[dict]:
        safe_limit = max(1, min(int(limit), 200))
        if status:
            query = (
                f"SELECT offer_id, target_listing_id, offered_listing_id, selected_offered_listing_id, from_subject, to_subject, status, accepted_by_from, accepted_by_to, from_receive_address_json, to_receive_address_json, message, created_at, updated_at, offered_listing_ids_json "
                f"FROM trade_offers WHERE (to_subject = {self.param} OR from_subject = {self.param}) AND status = {self.param} "
                f"ORDER BY created_at DESC LIMIT {self.param}"
            )
            params = (subject, subject, status, safe_limit)
        else:
            query = (
                f"SELECT offer_id, target_listing_id, offered_listing_id, selected_offered_listing_id, from_subject, to_subject, status, accepted_by_from, accepted_by_to, from_receive_address_json, to_receive_address_json, message, created_at, updated_at, offered_listing_ids_json "
                f"FROM trade_offers WHERE (to_subject = {self.param} OR from_subject = {self.param}) "
                f"ORDER BY created_at DESC LIMIT {self.param}"
            )
            params = (subject, subject, safe_limit)

        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, params).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()

        return [self._trade_offer_row_to_dict(row) for row in rows]

    def list_incoming_trade_offers(self, to_subject: str, limit: int = 50, status: str | None = None) -> list[dict]:
        return self.list_trade_offers_for_subject(to_subject, limit=limit, status=status)

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
            cur = self._pg_cursor()
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
            f"SELECT offer_id, target_listing_id, offered_listing_id, selected_offered_listing_id, from_subject, to_subject, status, accepted_by_from, accepted_by_to, from_receive_address_json, to_receive_address_json, message, created_at, updated_at, offered_listing_ids_json "
            f"FROM trade_offers WHERE offer_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (offer_id,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (offer_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        return self._trade_offer_row_to_dict(row)

    def set_trade_offer_participant_action(
        self,
        *,
        offer_id: str,
        actor_subject: str,
        status: str,
        receive_address: dict | None = None,
        selected_offered_listing_id: str | None = None,
    ) -> dict | None:
        offer = self.get_trade_offer_by_id(offer_id)
        if not offer:
            return None
        from_subject = str(offer.get("from_subject") or "")
        to_subject = str(offer.get("to_subject") or "")
        if actor_subject not in {from_subject, to_subject}:
            return None

        now = utc_now_iso()
        status_norm = str(status or "").strip().lower()
        accepted_by_from = bool(offer.get("accepted_by_from"))
        accepted_by_to = bool(offer.get("accepted_by_to"))
        from_receive = self._normalize_offer_address(offer.get("from_receive_address"))
        to_receive = self._normalize_offer_address(offer.get("to_receive_address"))
        selected_offered_id = str(offer.get("selected_offered_listing_id") or "").strip() or None

        if status_norm == "accepted":
            normalized_addr = self._normalize_offer_address(receive_address or {})
            accepted_by_from = True
            if actor_subject == from_subject:
                accepted_by_from = True
                if normalized_addr:
                    from_receive = normalized_addr
                next_status = "pending"
            else:
                accepted_by_to = True
                if normalized_addr:
                    to_receive = normalized_addr
                offered_ids = [str(x).strip() for x in (offer.get("offered_listing_ids") or []) if isinstance(x, str) and str(x).strip()]
                if not offered_ids and isinstance(offer.get("offered_listing_id"), str) and offer.get("offered_listing_id").strip():
                    offered_ids = [offer["offered_listing_id"].strip()]
                candidate_selected_id = str(selected_offered_listing_id or "").strip()
                if not candidate_selected_id and len(offered_ids) == 1:
                    candidate_selected_id = offered_ids[0]
                if candidate_selected_id not in offered_ids:
                    return None
                selected_offered_id = candidate_selected_id
                next_status = "accepted"
        else:
            next_status = status_norm
            accepted_by_from = False
            accepted_by_to = False
            from_receive = None
            to_receive = None
            selected_offered_id = None

        sql = (
            f"UPDATE trade_offers SET status = {self.param}, accepted_by_from = {self.param}, accepted_by_to = {self.param}, "
            f"from_receive_address_json = {self.param}, to_receive_address_json = {self.param}, selected_offered_listing_id = {self.param}, updated_at = {self.param} "
            f"WHERE offer_id = {self.param}"
        )
        self.execute(
            sql,
            (
                next_status,
                1 if accepted_by_from else 0,
                1 if accepted_by_to else 0,
                json.dumps(from_receive) if from_receive else None,
                json.dumps(to_receive) if to_receive else None,
                selected_offered_id,
                now,
                offer_id,
            ),
        )
        self.commit()
        return self.get_trade_offer_by_id(offer_id)

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
            f"SELECT offer_id, target_listing_id, offered_listing_id, selected_offered_listing_id, from_subject, to_subject, status, accepted_by_from, accepted_by_to, from_receive_address_json, to_receive_address_json, message, created_at, updated_at, offered_listing_ids_json "
            f"FROM trade_offers WHERE offer_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (offer_id,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (offer_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        return self._trade_offer_row_to_dict(row)

    def execute(self, sql: str, params: tuple = ()) -> None:
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(sql, params)
            return
        cur = self._pg_cursor()
        try:
            cur.execute(sql, params)
        except Exception:
            self._pg.rollback()
            raise
        finally:
            cur.close()

    def commit(self) -> None:
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.commit()
        else:
            conn = self._ensure_pg_connection()
            conn.commit()

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
            (image_id, item_id, filename, role_hint, storage_uri, content_hash, created_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
            (
                record.image_id,
                record.item_id,
                record.filename,
                record.role_hint,
                record.storage_uri,
                record.content_hash,
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
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (limit,)).fetchall()
            return [self._analysis_row_to_dict(row) for row in rows]
        cur = self._pg_cursor()
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        cur.close()
        return [self._analysis_row_to_dict(row) for row in rows]

    def get_image_storage_uri(self, image_id: str) -> str | None:
        query = f"SELECT storage_uri FROM images WHERE image_id = {self.param} LIMIT 1"
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (image_id,)).fetchone()
            if not row:
                return None
            return row["storage_uri"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg_cursor()
        cur.execute(query, (image_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return row[0]

    def get_image_id_by_storage_uri(self, storage_uri: str) -> str | None:
        query = f"SELECT image_id FROM images WHERE storage_uri = {self.param} ORDER BY created_at ASC LIMIT 1"
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (storage_uri,)).fetchone()
            if not row:
                return None
            return row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg_cursor()
        cur.execute(query, (storage_uri,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return row[0]

    def get_image_id_by_public_url(self, value: object, source_item_id: str | None = None) -> str | None:
        api_image_id = _image_id_from_api_url(value)
        if api_image_id:
            return api_image_id

        storage_uri = _upload_path_from_public_url(value)
        if storage_uri:
            image_id = self.get_image_id_by_storage_uri(storage_uri)
            if image_id:
                return image_id

        upload_image_id = _image_id_from_upload_path(value)
        if not upload_image_id:
            return None
        if source_item_id:
            query = (
                f"SELECT image_id FROM images WHERE image_id = {self.param} AND item_id = {self.param} LIMIT 1"
            )
            params = (upload_image_id, source_item_id)
        else:
            query = f"SELECT image_id FROM images WHERE image_id = {self.param} LIMIT 1"
            params = (upload_image_id,)
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, params).fetchone()
            if not row:
                return None
            return row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg_cursor()
        cur.execute(query, params)
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return row[0]

    def _canonical_listing_image_url(self, value: object, source_item_id: str | None = None) -> str | None:
        image_id = self.get_image_id_by_public_url(value, source_item_id)
        if image_id:
            return f"/v1/images/{image_id}"
        if isinstance(value, str) and value.strip().startswith("s3://"):
            image_id = self.get_image_id_by_storage_uri(value.strip())
            if image_id:
                return f"/v1/images/{image_id}"
            return None
        return normalize_public_listing_image_url(value)

    def _canonical_listing_images(
        self,
        *,
        image: object,
        images: list[object] | None,
        source_item_id: str | None,
    ) -> tuple[str | None, list[str]]:
        normalized_images: list[object] = []
        seen: set[str] = set()
        for value in images or []:
            if isinstance(value, dict):
                original = self._canonical_listing_image_url(
                    value.get("p_img") or value.get("original_image") or value.get("source_image"),
                    source_item_id,
                )
                display = self._canonical_listing_image_url(
                    value.get("d_img") or value.get("display_image") or value.get("image") or original,
                    source_item_id,
                )
                if not display:
                    continue
                key = listing_image_dedupe_key(display)
                if key in seen:
                    continue
                normalized_images.append({
                    "p_img": original or display,
                    "d_img": display,
                    "is_hero": bool(value.get("is_hero")),
                })
                seen.add(key)
                continue
            normalized = self._canonical_listing_image_url(value, source_item_id)
            key = listing_image_dedupe_key(normalized)
            if normalized and key not in seen:
                normalized_images.append(normalized)
                seen.add(key)

        normalized_image = self._canonical_listing_image_url(image, source_item_id)
        key = listing_image_dedupe_key(normalized_image)
        if normalized_image and key not in seen:
            normalized_images.insert(0, normalized_image)
            seen.add(key)
        if not normalized_image and normalized_images:
            first = normalized_images[0]
            normalized_image = first.get("d_img") if isinstance(first, dict) else first
        return normalized_image, normalized_images

    def get_first_image_id_for_item(self, item_id: str) -> str | None:
        query = (
            f"SELECT image_id FROM images WHERE item_id = {self.param} "
            f"ORDER BY created_at ASC LIMIT 1"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (item_id,)).fetchone()
            if not row:
                return None
            return row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
        cur = self._pg_cursor()
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
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (item_id, safe_limit)).fetchall()
            result: list[str] = []
            for row in rows:
                image_id = row["image_id"] if isinstance(row, sqlite3.Row) else row[0]
                if isinstance(image_id, str) and image_id.strip():
                    result.append(image_id)
            return result
        cur = self._pg_cursor()
        cur.execute(query, (item_id, safe_limit))
        rows = cur.fetchall()
        cur.close()
        result: list[str] = []
        for row in rows:
            image_id = row[0]
            if isinstance(image_id, str) and image_id.strip():
                result.append(image_id)
        return result

    def list_image_records_for_item(self, item_id: str, limit: int = 20) -> list[dict]:
        safe_limit = max(1, min(int(limit), 20))
        query = (
            f"SELECT image_id, item_id, filename, role_hint, storage_uri, content_hash, created_at "
            f"FROM images WHERE item_id = {self.param} ORDER BY created_at ASC LIMIT {self.param}"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (item_id, safe_limit)).fetchall()
            return [dict(row) if isinstance(row, sqlite3.Row) else {
                "image_id": row[0],
                "item_id": row[1],
                "filename": row[2],
                "role_hint": row[3],
                "storage_uri": row[4],
                "content_hash": row[5],
                "created_at": row[6],
            } for row in rows]
        cur = self._pg_cursor()
        cur.execute(query, (item_id, safe_limit))
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "image_id": row[0],
                "item_id": row[1],
                "filename": row[2],
                "role_hint": row[3],
                "storage_uri": row[4],
                "content_hash": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def list_image_content_hashes_for_item(self, item_id: str, limit: int = 20) -> list[str]:
        hashes: list[str] = []
        for record in self.list_image_records_for_item(item_id, limit=limit):
            value = record.get("content_hash")
            if isinstance(value, str) and value.strip():
                hashes.append(value.strip())
        return hashes

    def _item_has_listing_owner(self, item_id: str, owner_subject: str) -> bool:
        if not item_id or not owner_subject:
            return False
        query = (
            f"SELECT owner_subject FROM listings WHERE source_item_id = {self.param}"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (item_id,)).fetchall()
            if not rows:
                return True
            return any(
                (row["owner_subject"] if isinstance(row, sqlite3.Row) else row[0]) == owner_subject
                for row in rows
            )
        cur = self._pg_cursor()
        cur.execute(query, (item_id,))
        rows = cur.fetchall()
        cur.close()
        if not rows:
            return True
        return any(row[0] == owner_subject for row in rows)

    def find_recent_analysis_by_image_hashes(
        self,
        hashes: list[str],
        limit: int = 50,
        owner_subject: str | None = None,
    ) -> dict | None:
        target = sorted(h.strip() for h in hashes if isinstance(h, str) and h.strip())
        if not target:
            return None
        for analysis in self.list_recent_analyses(limit=limit):
            item_id = str(analysis.get("item_id") or "").strip()
            if not item_id:
                continue
            if owner_subject and not self._item_has_listing_owner(item_id, owner_subject):
                continue
            candidate = sorted(self.list_image_content_hashes_for_item(item_id, limit=20))
            if candidate and candidate == target:
                return analysis
        return None

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
        images: list[object],
        description: str,
        wants: str,
        tags: list[str],
        source_item_id: str | None,
        analysis: dict | None,
        status: str,
    ) -> str:
        created_at = utc_now_iso()
        updated_at = created_at
        image, images = self._canonical_listing_images(
            image=image,
            images=images,
            source_item_id=source_item_id,
        )
        self.execute(
            f"""INSERT INTO listings
            (listing_id, owner_subject, owner_name, title, mode, category, brand, condition, size,
             estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param},
                    {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})""",
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
                updated_at,
            ),
        )
        self.commit()
        return created_at

    def list_recent_listings(
        self,
        limit: int = 50,
        offset: int = 0,
        include_analysis: bool = True,
        include_media: bool = True,
        active_only: bool = False,
    ) -> list[dict]:
        analysis_select = "analysis_json" if include_analysis else "NULL AS analysis_json"
        image_select = "image" if include_media else "NULL AS image"
        images_select = "images_json" if include_media else "'[]' AS images_json"
        where_clause = "WHERE LOWER(status) = 'active'" if active_only else ""
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, {image_select}, {images_select}, description, wants, tags_json, source_item_id, {analysis_select}, status, created_at, COALESCE(updated_at, created_at) AS updated_at "
            f"FROM listings {where_clause} ORDER BY created_at DESC LIMIT {self.param} OFFSET {self.param}"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (limit, offset)).fetchall()
            return [self._listing_row_to_dict(row) for row in rows]
        cur = self._pg_cursor()
        cur.execute(query, (limit, offset))
        rows = cur.fetchall()
        cur.close()
        return [self._listing_row_to_dict(row) for row in rows]

    def list_owner_listings(self, owner_subject: str, limit: int = 50, offset: int = 0) -> list[dict]:
        query = (
            f"SELECT listing_id, owner_subject, owner_name, title, mode, category, brand, condition, "
            f"size, estimated_value, city, image, images_json, description, wants, tags_json, source_item_id, analysis_json, status, created_at, COALESCE(updated_at, created_at) AS updated_at "
            f"FROM listings WHERE owner_subject = {self.param} ORDER BY created_at DESC LIMIT {self.param} OFFSET {self.param}"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (owner_subject, limit, offset)).fetchall()
            return [self._listing_row_to_dict(row) for row in rows]
        cur = self._pg_cursor()
        cur.execute(query, (owner_subject, limit, offset))
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
        images: list[object],
        description: str,
        wants: str,
        tags: list[str],
        source_item_id: str | None,
        analysis: dict | None,
        status: str,
    ) -> bool:
        updated_at = utc_now_iso()
        image, images = self._canonical_listing_images(
            image=image,
            images=images,
            source_item_id=source_item_id,
        )
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
                status = {self.param},
                updated_at = {self.param}
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
            updated_at,
            listing_id,
            owner_subject,
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(sql, params)
                changed_row = self._sqlite_conn.execute("SELECT changes() AS n").fetchone()
            changed = int(changed_row["n"] if isinstance(changed_row, sqlite3.Row) else changed_row[0]) > 0
        else:
            cur = self._pg_cursor()
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

    def mark_stale_analyzing_listings_failed(self, cutoff_updated_at: str) -> int:
        sql = (
            f"UPDATE listings SET status = {self.param}, tags_json = {self.param} "
            f"WHERE LOWER(status) = {self.param} AND COALESCE(updated_at, created_at) < {self.param}"
        )
        params = ("AnalysisFailed", json.dumps(["Analysis failed"]), "analyzing", cutoff_updated_at)
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(sql, params)
                changed_row = self._sqlite_conn.execute("SELECT changes() AS n").fetchone()
            changed = int(changed_row["n"] if isinstance(changed_row, sqlite3.Row) else changed_row[0])
        else:
            cur = self._pg_cursor()
            try:
                cur.execute(sql, params)
                changed = int(cur.rowcount or 0)
            except Exception:
                self._pg.rollback()
                raise
            finally:
                cur.close()
        self.commit()
        return changed

    def list_trade_offers_for_listing(self, listing_id: str, active_only: bool = False) -> list[dict]:
        listing_id = str(listing_id or "").strip()
        if not listing_id:
            return []
        statuses = ("pending", "accepted", "countered") if active_only else None
        like_value = f"%{listing_id}%"
        base_query = (
            f"SELECT offer_id, target_listing_id, offered_listing_id, selected_offered_listing_id, from_subject, to_subject, status, accepted_by_from, accepted_by_to, from_receive_address_json, to_receive_address_json, message, created_at, updated_at, offered_listing_ids_json "
            f"FROM trade_offers WHERE (target_listing_id = {self.param} OR offered_listing_id = {self.param} OR offered_listing_ids_json LIKE {self.param})"
        )
        params: tuple = (listing_id, listing_id, like_value)
        if statuses:
            placeholders = ", ".join([self.param] * len(statuses))
            base_query = f"{base_query} AND status IN ({placeholders})"
            params = (*params, *statuses)
        query = f"{base_query} ORDER BY updated_at DESC"
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, params).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
        offers = [self._trade_offer_row_to_dict(row) for row in rows]
        filtered: list[dict] = []
        for offer in offers:
            if listing_id == str(offer.get("target_listing_id") or ""):
                filtered.append(offer)
                continue
            selected_offered_id = str(offer.get("selected_offered_listing_id") or "").strip()
            if str(offer.get("status") or "").lower() == "accepted" and selected_offered_id:
                if listing_id == selected_offered_id:
                    filtered.append(offer)
                continue
            if listing_id == str(offer.get("offered_listing_id") or "") or listing_id in [str(x) for x in (offer.get("offered_listing_ids") or [])]:
                filtered.append(offer)
        return filtered

    def listing_has_active_trade(self, listing_id: str) -> bool:
        return bool(self.list_trade_offers_for_listing(listing_id, active_only=True))

    def delete_listing(self, *, listing_id: str, owner_subject: str) -> bool:
        listing = self.get_listing_by_id(listing_id)
        if not listing or str(listing.get("owner_subject") or "") != str(owner_subject or ""):
            return False
        if self.listing_has_active_trade(listing_id):
            return False
        self.execute(
            f"DELETE FROM trade_matches WHERE target_listing_id = {self.param} OR candidate_listing_id = {self.param}",
            (listing_id, listing_id),
        )
        sql = f"DELETE FROM listings WHERE listing_id = {self.param} AND owner_subject = {self.param}"
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(sql, (listing_id, owner_subject))
                changed_row = self._sqlite_conn.execute("SELECT changes() AS n").fetchone()
            changed = int(changed_row["n"] if isinstance(changed_row, sqlite3.Row) else changed_row[0]) > 0
        else:
            cur = self._pg_cursor()
            try:
                cur.execute(sql, (listing_id, owner_subject))
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
            cur = self._pg_cursor()
            cur.execute("SELECT listing_id, image, images_json, source_item_id, analysis_json, description, wants FROM listings")
            rows = cur.fetchall()
            cur.close()

        def resolve(url: object, source_item_id: str | None) -> str | None:
            if not isinstance(url, str):
                return None
            return self._canonical_listing_image_url(url, source_item_id)

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
            try:
                analysis = json.loads(analysis_json) if analysis_json else None
            except Exception:
                analysis = None

            normalized_images: list[object] = []
            seen_image_keys: set[str] = set()
            # Analysis uploads are the model inputs, not an additional display gallery.
            # Only fall back to them when the listing has no explicit images; otherwise
            # PhotoRoom/display images plus original analysis uploads can double-count.
            image_candidates = (
                _remove_analysis_uploads_when_display_gallery_exists(images, analysis)
                if images
                else self._image_urls_from_analysis_uploads(analysis)
            )
            for url in image_candidates:
                if isinstance(url, dict):
                    original = resolve(url.get("p_img") or url.get("original_image") or url.get("source_image"), source_item_id)
                    display = resolve(url.get("d_img") or url.get("display_image") or url.get("image") or original, source_item_id)
                    key = listing_image_dedupe_key(display)
                    if display and key not in seen_image_keys:
                        normalized_images.append({
                            "p_img": original or display,
                            "d_img": display,
                            "is_hero": bool(url.get("is_hero")),
                        })
                        seen_image_keys.add(key)
                    continue
                resolved = resolve(url, source_item_id)
                key = listing_image_dedupe_key(resolved)
                if resolved and key not in seen_image_keys:
                    normalized_images.append(resolved)
                    seen_image_keys.add(key)
            normalized_image = resolve(image, source_item_id)
            if not normalized_images and normalized_image:
                normalized_images = [normalized_image]
            if not normalized_images and isinstance(source_item_id, str) and source_item_id.strip():
                normalized_images = [f"/v1/images/{image_id}" for image_id in self.list_image_ids_for_item(source_item_id, limit=20)]
            if not normalized_image and normalized_images:
                first = normalized_images[0]
                normalized_image = first.get("d_img") if isinstance(first, dict) else first

            normalized_description = (description or "").strip() if isinstance(description, str) else ""
            if not normalized_description and analysis_json:
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
            if not normalized_description and wants_text and not is_generic_trade_note(wants_text):
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

    def _image_urls_from_analysis_uploads(self, analysis: object) -> list[str]:
        if not isinstance(analysis, dict):
            return []
        entries: list[object] = []
        uploaded_images = analysis.get("uploaded_images")
        if isinstance(uploaded_images, list):
            entries.extend(uploaded_images)
        debug = analysis.get("debug")
        if isinstance(debug, dict) and isinstance(debug.get("uploads"), list):
            entries.extend(debug.get("uploads") or [])

        urls: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = entry.get("image_url")
            if isinstance(url, str) and url.strip():
                normalized = self._canonical_listing_image_url(url)
                if normalized:
                    key = listing_image_dedupe_key(normalized)
                    if key not in seen:
                        urls.append(normalized)
                        seen.add(key)
                    continue
            image_id = entry.get("image_id")
            if isinstance(image_id, str) and image_id.strip():
                normalized = f"/v1/images/{image_id.strip()}"
                key = listing_image_dedupe_key(normalized)
                if key not in seen:
                    urls.append(normalized)
                    seen.add(key)
                continue
            storage_uri = entry.get("storage_uri")
            if isinstance(storage_uri, str) and storage_uri.strip():
                normalized = self._canonical_listing_image_url(storage_uri.strip())
                if normalized:
                    key = listing_image_dedupe_key(normalized)
                    if key not in seen:
                        urls.append(normalized)
                        seen.add(key)
        return urls

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
                "updated_at",
            ]
            data = {k: row[idx] for idx, k in enumerate(keys)}
        source_item_id = data.get("source_item_id")
        image = self._canonical_listing_image_url(data["image"], source_item_id)

        try:
            images = json.loads(data.get("images_json") or "[]")
        except Exception:
            images = []
        safe_images = []
        safe_listed_images = []
        seen_image_keys: set[str] = set()
        for value in images:
            if isinstance(value, dict):
                original = self._canonical_listing_image_url(
                    value.get("p_img") or value.get("original_image") or value.get("source_image"),
                    source_item_id,
                )
                display = self._canonical_listing_image_url(
                    value.get("d_img") or value.get("display_image") or value.get("image") or original,
                    source_item_id,
                )
                key = listing_image_dedupe_key(display)
                if display and key not in seen_image_keys:
                    safe_images.append(display)
                    safe_listed_images.append({
                        "p_img": original or display,
                        "d_img": display,
                        "is_hero": False,
                    })
                    seen_image_keys.add(key)
                continue
            normalized = self._canonical_listing_image_url(value, source_item_id)
            key = listing_image_dedupe_key(normalized)
            if normalized and key not in seen_image_keys:
                safe_images.append(normalized)
                safe_listed_images.append({"p_img": normalized, "d_img": normalized, "is_hero": False})
                seen_image_keys.add(key)

        description = (data.get("description") or "").strip() if isinstance(data.get("description"), str) else ""
        wants = data["wants"]
        if not description and isinstance(wants, str):
            wants_text = wants.strip()
            if wants_text and not is_generic_trade_note(wants_text):
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
        if not safe_images:
            safe_images = self._image_urls_from_analysis_uploads(analysis)
        else:
            safe_images = _remove_analysis_uploads_when_display_gallery_exists(safe_images, analysis)
        if not safe_images and isinstance(source_item_id, str) and source_item_id.strip():
            safe_images = [f"/v1/images/{image_id}" for image_id in self.list_image_ids_for_item(source_item_id, limit=20)]
            safe_listed_images = [{"p_img": url, "d_img": url, "is_hero": False} for url in safe_images]
        elif not safe_listed_images:
            safe_listed_images = [{"p_img": url, "d_img": url, "is_hero": False} for url in safe_images]
        if not image and safe_images:
            image = safe_images[0]
        for entry in safe_listed_images:
            entry["is_hero"] = bool(image and entry.get("d_img") == image)

        return {
            "listing_id": data["listing_id"],
            "owner_subject": data["owner_subject"],
            "owner_name": data["owner_name"],
            "title": data["title"],
            "mode": "trade",
            "category": data["category"],
            "brand": data["brand"],
            "condition": data["condition"],
            "size": data.get("size"),
            "estimated_value": estimated_value,
            "city": data["city"],
            "image": image,
            "images": safe_images,
            "listed_images": safe_listed_images,
            "description": description,
            "wants": wants,
            "tags": tags,
            "source_item_id": source_item_id,
            "analysis": analysis,
            "status": data.get("status") or "Review",
            "created_at": data["created_at"],
            "updated_at": data.get("updated_at") or data["created_at"],
        }

    def get_user_profile_quiz(self, owner_subject: str) -> dict | None:
        query = (
            f"SELECT owner_subject, first_name, last_name, email, gender, birthday, tops_size, dresses_size, bottoms_size, shoes_size, "
            f"category_preferences_json, style_descriptors_json, jouft_goals_json, shipping_full_name, shipping_address_line1, shipping_address_line2, "
            f"shipping_city, shipping_state, shipping_postal_code, shipping_country, shipping_email, shipping_phone, shipping_addresses_json, "
            f"subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, payment_methods_json, "
            f"created_at, updated_at "
            f"FROM user_profiles WHERE owner_subject = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (owner_subject,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (owner_subject,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = [
                "owner_subject", "first_name", "last_name", "email", "gender", "birthday", "tops_size", "dresses_size", "bottoms_size", "shoes_size",
                "category_preferences_json", "style_descriptors_json", "jouft_goals_json", "shipping_full_name", "shipping_address_line1", "shipping_address_line2",
                "shipping_city", "shipping_state", "shipping_postal_code", "shipping_country",
                "shipping_email", "shipping_phone", "shipping_addresses_json",
                "subscription_plan", "subscription_billing_cycle", "subscription_status", "subscription_renewal_date", "payment_methods_json",
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
            style_descriptors = json.loads(data.get("style_descriptors_json") or "[]")
            if not isinstance(style_descriptors, list):
                style_descriptors = []
        except Exception:
            style_descriptors = []
        try:
            jouft_goals = json.loads(data.get("jouft_goals_json") or "[]")
            if not isinstance(jouft_goals, list):
                jouft_goals = []
        except Exception:
            jouft_goals = []
        try:
            payment_methods = json.loads(data.get("payment_methods_json") or "[]")
            if not isinstance(payment_methods, list):
                payment_methods = []
        except Exception:
            payment_methods = []
        try:
            shipping_addresses = self._normalize_shipping_addresses(json.loads(data.get("shipping_addresses_json") or "[]"))
        except Exception:
            shipping_addresses = []
        if not shipping_addresses:
            legacy_address = {
                "label": "Primary",
                "full_name": data.get("shipping_full_name"),
                "address_line1": data.get("shipping_address_line1"),
                "address_line2": data.get("shipping_address_line2"),
                "city": data.get("shipping_city"),
                "state": data.get("shipping_state"),
                "postal_code": data.get("shipping_postal_code"),
                "country": data.get("shipping_country"),
                "is_default": True,
            }
            has_any_legacy = any(
                isinstance(legacy_address.get(k), str) and legacy_address.get(k)
                for k in ("full_name", "address_line1", "address_line2", "city", "state", "postal_code", "country")
            )
            if has_any_legacy:
                shipping_addresses = [legacy_address]
        primary_address = shipping_addresses[0] if shipping_addresses else {}
        return {
            "owner_subject": data["owner_subject"],
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "email": data.get("email"),
            "gender": data.get("gender"),
            "birthday": data.get("birthday"),
            "tops_size": data.get("tops_size"),
            "dresses_size": data.get("dresses_size"),
            "bottoms_size": data.get("bottoms_size"),
            "shoes_size": data.get("shoes_size"),
            "category_preferences": [p for p in prefs if isinstance(p, str)],
            "style_descriptors": [p for p in style_descriptors if isinstance(p, str)],
            "jouft_goals": [p for p in jouft_goals if isinstance(p, str)],
            "shipping_full_name": primary_address.get("full_name") or data.get("shipping_full_name"),
            "shipping_address_line1": primary_address.get("address_line1") or data.get("shipping_address_line1"),
            "shipping_address_line2": primary_address.get("address_line2") or data.get("shipping_address_line2"),
            "shipping_city": primary_address.get("city") or data.get("shipping_city"),
            "shipping_state": primary_address.get("state") or data.get("shipping_state"),
            "shipping_postal_code": primary_address.get("postal_code") or data.get("shipping_postal_code"),
            "shipping_country": primary_address.get("country") or data.get("shipping_country"),
            "shipping_email": data.get("shipping_email"),
            "shipping_phone": data.get("shipping_phone"),
            "shipping_addresses": shipping_addresses,
            "subscription_plan": data.get("subscription_plan"),
            "subscription_billing_cycle": data.get("subscription_billing_cycle"),
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
        first_name: str | None,
        last_name: str | None,
        email: str | None,
        gender: str | None,
        birthday: str | None,
        tops_size: str | None,
        dresses_size: str | None,
        bottoms_size: str | None,
        shoes_size: str | None,
        category_preferences: list[str],
        style_descriptors: list[str],
        jouft_goals: list[str],
        shipping_full_name: str | None,
        shipping_address_line1: str | None,
        shipping_address_line2: str | None,
        shipping_city: str | None,
        shipping_state: str | None,
        shipping_postal_code: str | None,
        shipping_country: str | None,
        shipping_email: str | None,
        shipping_phone: str | None,
        shipping_addresses: list[dict[str, object]],
        subscription_plan: str | None,
        subscription_billing_cycle: str | None,
        subscription_status: str | None,
        subscription_renewal_date: str | None,
        payment_methods: list[str],
    ) -> dict:
        now = utc_now_iso()
        cats = json.dumps([c for c in category_preferences if isinstance(c, str)])
        styles = json.dumps([s for s in style_descriptors if isinstance(s, str) and s.strip()])
        goals = json.dumps([g for g in jouft_goals if isinstance(g, str) and g.strip()])
        payment_methods_json = json.dumps([m for m in payment_methods if isinstance(m, str) and m.strip()])
        shipping_addresses_json = json.dumps(self._normalize_shipping_addresses(shipping_addresses))
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(
                    """INSERT INTO user_profiles
                    (owner_subject, first_name, last_name, email, gender, birthday, tops_size, dresses_size, bottoms_size, shoes_size, category_preferences_json, style_descriptors_json, jouft_goals_json, shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_postal_code, shipping_country, shipping_email, shipping_phone, shipping_addresses_json, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, payment_methods_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(owner_subject) DO UPDATE SET
                      first_name=excluded.first_name,
                      last_name=excluded.last_name,
                      email=excluded.email,
                      gender=excluded.gender,
                      birthday=excluded.birthday,
                      tops_size=excluded.tops_size,
                      dresses_size=excluded.dresses_size,
                      bottoms_size=excluded.bottoms_size,
                      shoes_size=excluded.shoes_size,
                      category_preferences_json=excluded.category_preferences_json,
                      style_descriptors_json=excluded.style_descriptors_json,
                  jouft_goals_json=excluded.jouft_goals_json,
                  shipping_full_name=excluded.shipping_full_name,
                  shipping_address_line1=excluded.shipping_address_line1,
                  shipping_address_line2=excluded.shipping_address_line2,
                  shipping_city=excluded.shipping_city,
                  shipping_state=excluded.shipping_state,
                  shipping_postal_code=excluded.shipping_postal_code,
                  shipping_country=excluded.shipping_country,
                  shipping_email=excluded.shipping_email,
                  shipping_phone=excluded.shipping_phone,
                  shipping_addresses_json=excluded.shipping_addresses_json,
                  subscription_plan=excluded.subscription_plan,
                  subscription_billing_cycle=excluded.subscription_billing_cycle,
                  subscription_status=excluded.subscription_status,
                  subscription_renewal_date=excluded.subscription_renewal_date,
                  payment_methods_json=excluded.payment_methods_json,
                  updated_at=excluded.updated_at
                """,
                (
                    owner_subject, first_name, last_name, email, gender, birthday, tops_size, dresses_size, bottoms_size, shoes_size, cats, styles, goals,
                    shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state,
                    shipping_postal_code, shipping_country, shipping_email, shipping_phone, shipping_addresses_json, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date,
                    payment_methods_json, now, now,
                ),
            )
                self._sqlite_conn.commit()
        else:
            cur = self._pg_cursor()
            cur.execute(
                f"""INSERT INTO user_profiles
                (owner_subject, first_name, last_name, email, gender, birthday, tops_size, dresses_size, bottoms_size, shoes_size, category_preferences_json, style_descriptors_json, jouft_goals_json, shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state, shipping_postal_code, shipping_country, shipping_email, shipping_phone, shipping_addresses_json, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, payment_methods_json, created_at, updated_at)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT (owner_subject) DO UPDATE SET
                  first_name=EXCLUDED.first_name,
                  last_name=EXCLUDED.last_name,
                  email=EXCLUDED.email,
                  gender=EXCLUDED.gender,
                  birthday=EXCLUDED.birthday,
                  tops_size=EXCLUDED.tops_size,
                  dresses_size=EXCLUDED.dresses_size,
                  bottoms_size=EXCLUDED.bottoms_size,
                  shoes_size=EXCLUDED.shoes_size,
                  category_preferences_json=EXCLUDED.category_preferences_json,
                  style_descriptors_json=EXCLUDED.style_descriptors_json,
                  jouft_goals_json=EXCLUDED.jouft_goals_json,
                  shipping_full_name=EXCLUDED.shipping_full_name,
                  shipping_address_line1=EXCLUDED.shipping_address_line1,
                  shipping_address_line2=EXCLUDED.shipping_address_line2,
                  shipping_city=EXCLUDED.shipping_city,
                  shipping_state=EXCLUDED.shipping_state,
                  shipping_postal_code=EXCLUDED.shipping_postal_code,
                  shipping_country=EXCLUDED.shipping_country,
                  shipping_email=EXCLUDED.shipping_email,
                  shipping_phone=EXCLUDED.shipping_phone,
                  shipping_addresses_json=EXCLUDED.shipping_addresses_json,
                  subscription_plan=EXCLUDED.subscription_plan,
                  subscription_billing_cycle=EXCLUDED.subscription_billing_cycle,
                  subscription_status=EXCLUDED.subscription_status,
                  subscription_renewal_date=EXCLUDED.subscription_renewal_date,
                  payment_methods_json=EXCLUDED.payment_methods_json,
                  updated_at=EXCLUDED.updated_at
                """,
                (
                    owner_subject, first_name, last_name, email, gender, birthday, tops_size, dresses_size, bottoms_size, shoes_size, cats, styles, goals,
                    shipping_full_name, shipping_address_line1, shipping_address_line2, shipping_city, shipping_state,
                    shipping_postal_code, shipping_country, shipping_email, shipping_phone, shipping_addresses_json, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date,
                    payment_methods_json, now, now,
                ),
            )
            cur.close()
            self._pg.commit()
        return self.get_user_profile_quiz(owner_subject) or {
            "owner_subject": owner_subject,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "gender": gender,
            "birthday": birthday,
            "tops_size": tops_size,
            "dresses_size": dresses_size,
            "bottoms_size": bottoms_size,
            "shoes_size": shoes_size,
            "category_preferences": category_preferences,
            "style_descriptors": [s for s in style_descriptors if isinstance(s, str) and s.strip()],
            "jouft_goals": [g for g in jouft_goals if isinstance(g, str) and g.strip()],
            "shipping_full_name": shipping_full_name,
            "shipping_address_line1": shipping_address_line1,
            "shipping_address_line2": shipping_address_line2,
            "shipping_city": shipping_city,
            "shipping_state": shipping_state,
            "shipping_postal_code": shipping_postal_code,
            "shipping_country": shipping_country,
            "shipping_email": shipping_email,
            "shipping_phone": shipping_phone,
            "shipping_addresses": self._normalize_shipping_addresses(shipping_addresses),
            "subscription_plan": subscription_plan,
            "subscription_billing_cycle": subscription_billing_cycle,
            "subscription_status": subscription_status,
            "subscription_renewal_date": subscription_renewal_date,
            "payment_methods": [m for m in payment_methods if isinstance(m, str) and m.strip()],
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _normalize_alert_preferences(raw: object) -> dict[str, bool]:
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): bool(value)
            for key, value in raw.items()
            if isinstance(key, str) and key.strip()
        }

    @staticmethod
    def _normalize_liked_listing_ids(raw: object) -> list[str]:
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for entry in raw:
            listing_id = str(entry or "").strip()
            if not listing_id or listing_id in seen:
                continue
            seen.add(listing_id)
            out.append(listing_id)
        return out

    def get_user_client_state(self, owner_subject: str) -> dict | None:
        query = (
            f"SELECT owner_subject, alert_preferences_json, liked_listing_ids_json, created_at, updated_at "
            f"FROM user_client_state WHERE owner_subject = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (owner_subject,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (owner_subject,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            data = dict(row)
        else:
            keys = ["owner_subject", "alert_preferences_json", "liked_listing_ids_json", "created_at", "updated_at"]
            data = {k: row[idx] for idx, k in enumerate(keys)}
        try:
            alert_preferences = self._normalize_alert_preferences(json.loads(data.get("alert_preferences_json") or "{}"))
        except Exception:
            alert_preferences = {}
        try:
            liked_listing_ids = self._normalize_liked_listing_ids(json.loads(data.get("liked_listing_ids_json") or "[]"))
        except Exception:
            liked_listing_ids = []
        return {
            "owner_subject": data["owner_subject"],
            "alert_preferences": alert_preferences,
            "liked_listing_ids": liked_listing_ids,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }

    def upsert_user_client_state(
        self,
        *,
        owner_subject: str,
        alert_preferences: dict[str, bool],
        liked_listing_ids: list[str],
    ) -> dict:
        now = utc_now_iso()
        alert_preferences_json = json.dumps(self._normalize_alert_preferences(alert_preferences))
        liked_listing_ids_json = json.dumps(self._normalize_liked_listing_ids(liked_listing_ids))
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(
                    """INSERT INTO user_client_state
                    (owner_subject, alert_preferences_json, liked_listing_ids_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(owner_subject) DO UPDATE SET
                      alert_preferences_json=excluded.alert_preferences_json,
                      liked_listing_ids_json=excluded.liked_listing_ids_json,
                      updated_at=excluded.updated_at
                    """,
                    (owner_subject, alert_preferences_json, liked_listing_ids_json, now, now),
                )
                self._sqlite_conn.commit()
        else:
            cur = self._pg_cursor()
            cur.execute(
                f"""INSERT INTO user_client_state
                (owner_subject, alert_preferences_json, liked_listing_ids_json, created_at, updated_at)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT (owner_subject) DO UPDATE SET
                  alert_preferences_json=EXCLUDED.alert_preferences_json,
                  liked_listing_ids_json=EXCLUDED.liked_listing_ids_json,
                  updated_at=EXCLUDED.updated_at
                """,
                (owner_subject, alert_preferences_json, liked_listing_ids_json, now, now),
            )
            cur.close()
            self._pg.commit()
        return self.get_user_client_state(owner_subject) or {
            "owner_subject": owner_subject,
            "alert_preferences": self._normalize_alert_preferences(alert_preferences),
            "liked_listing_ids": self._normalize_liked_listing_ids(liked_listing_ids),
            "created_at": now,
            "updated_at": now,
        }

    def create_user_notification(
        self,
        *,
        notification_id: str,
        owner_subject: str,
        actor_subject: str | None,
        type: str,
        title: str,
        body: str,
        entity_id: str | None = None,
        action_tab: str | None = None,
    ) -> dict:
        now = utc_now_iso()
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(
                    """INSERT INTO user_notifications
                    (notification_id, owner_subject, actor_subject, type, title, body, entity_id, action_tab, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (notification_id, owner_subject, actor_subject, type, title, body, entity_id, action_tab, now),
                )
                self._sqlite_conn.commit()
        else:
            cur = self._pg_cursor()
            cur.execute(
                f"""INSERT INTO user_notifications
                (notification_id, owner_subject, actor_subject, type, title, body, entity_id, action_tab, created_at)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                """,
                (notification_id, owner_subject, actor_subject, type, title, body, entity_id, action_tab, now),
            )
            cur.close()
            self._pg.commit()
        return {
            "notification_id": notification_id,
            "owner_subject": owner_subject,
            "actor_subject": actor_subject,
            "type": type,
            "title": title,
            "body": body,
            "entity_id": entity_id,
            "action_tab": action_tab,
            "created_at": now,
        }

    def list_user_notifications(self, owner_subject: str, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(int(limit or 50), 100))
        query = (
            f"SELECT notification_id, owner_subject, actor_subject, type, title, body, entity_id, action_tab, created_at "
            f"FROM user_notifications WHERE owner_subject = {self.param} ORDER BY created_at DESC LIMIT {safe_limit}"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (owner_subject,)).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (owner_subject,))
            rows = cur.fetchall()
            cur.close()
        keys = ["notification_id", "owner_subject", "actor_subject", "type", "title", "body", "entity_id", "action_tab", "created_at"]
        out: list[dict] = []
        for row in rows:
            if isinstance(row, sqlite3.Row):
                out.append(dict(row))
            else:
                out.append({key: row[idx] for idx, key in enumerate(keys)})
        return out

    def delete_user_notification(self, owner_subject: str, notification_id: str) -> bool:
        query = f"DELETE FROM user_notifications WHERE owner_subject = {self.param} AND notification_id = {self.param}"
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                cur = self._sqlite_conn.execute(query, (owner_subject, notification_id))
                self._sqlite_conn.commit()
                return cur.rowcount > 0
        cur = self._pg_cursor()
        cur.execute(query, (owner_subject, notification_id))
        deleted = cur.rowcount > 0
        cur.close()
        self._pg.commit()
        return deleted

    def delete_user_notifications(self, owner_subject: str) -> int:
        query = f"DELETE FROM user_notifications WHERE owner_subject = {self.param}"
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                cur = self._sqlite_conn.execute(query, (owner_subject,))
                self._sqlite_conn.commit()
                return int(cur.rowcount or 0)
        cur = self._pg_cursor()
        cur.execute(query, (owner_subject,))
        deleted = int(cur.rowcount or 0)
        cur.close()
        self._pg.commit()
        return deleted

    def list_payment_methods(self, owner_subject: str) -> list[dict]:
        query = (
            f"SELECT payment_method_id, owner_subject, provider, method_type, label, last4, brand, exp_month, exp_year, email, is_default, created_at, updated_at "
            f"FROM user_payment_methods WHERE owner_subject = {self.param} ORDER BY is_default DESC, created_at DESC"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                rows = self._sqlite_conn.execute(query, (owner_subject,)).fetchall()
        else:
            cur = self._pg_cursor()
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
            with self._sqlite_lock:
                cur = self._sqlite_conn.execute(query, (owner_subject, payment_method_id))
                deleted = cur.rowcount > 0
                self._sqlite_conn.commit()
            return deleted
        cur = self._pg_cursor()
        cur.execute(query, (owner_subject, payment_method_id))
        deleted = cur.rowcount > 0
        cur.close()
        self._pg.commit()
        return deleted

    def get_payment_method(self, owner_subject: str, payment_method_id: str) -> dict | None:
        query = (
            f"SELECT payment_method_id, owner_subject, provider, method_type, label, last4, brand, exp_month, exp_year, email, is_default, provider_token, created_at, updated_at "
            f"FROM user_payment_methods WHERE owner_subject = {self.param} AND payment_method_id = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (owner_subject, payment_method_id)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (owner_subject, payment_method_id))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        keys = [
            "payment_method_id", "owner_subject", "provider", "method_type", "label", "last4",
            "brand", "exp_month", "exp_year", "email", "is_default", "provider_token", "created_at", "updated_at",
        ]
        data = dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)}
        return {
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
            "provider_token": data.get("provider_token"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

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
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (owner_subject,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (owner_subject,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        if isinstance(row, sqlite3.Row):
            return row["stripe_customer_id"] if row["stripe_customer_id"] else None
        return row[0] if row and row[0] else None

    def set_stripe_customer_id(self, owner_subject: str, stripe_customer_id: str) -> None:
        now = utc_now_iso()
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
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
        cur = self._pg_cursor()
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

    def get_billing_profile(self, owner_subject: str) -> dict | None:
        query = (
            f"SELECT owner_subject, stripe_customer_id, stripe_subscription_id, subscription_plan, "
            f"subscription_billing_cycle, subscription_status, subscription_renewal_date, created_at, updated_at "
            f"FROM user_billing_profiles WHERE owner_subject = {self.param} LIMIT 1"
        )
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                row = self._sqlite_conn.execute(query, (owner_subject,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (owner_subject,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        keys = [
            "owner_subject", "stripe_customer_id", "stripe_subscription_id", "subscription_plan",
            "subscription_billing_cycle", "subscription_status", "subscription_renewal_date",
            "created_at", "updated_at",
        ]
        data = dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)}
        return {
            "owner_subject": data.get("owner_subject"),
            "stripe_customer_id": data.get("stripe_customer_id"),
            "stripe_subscription_id": data.get("stripe_subscription_id"),
            "subscription_plan": data.get("subscription_plan"),
            "subscription_billing_cycle": data.get("subscription_billing_cycle"),
            "subscription_status": data.get("subscription_status"),
            "subscription_renewal_date": data.get("subscription_renewal_date"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }

    def set_billing_subscription(
        self,
        owner_subject: str,
        *,
        stripe_subscription_id: str | None,
        subscription_plan: str | None,
        subscription_billing_cycle: str | None,
        subscription_status: str | None,
        subscription_renewal_date: str | None,
    ) -> None:
        now = utc_now_iso()
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(
                    """INSERT INTO user_billing_profiles
                    (owner_subject, stripe_subscription_id, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(owner_subject) DO UPDATE SET
                      stripe_subscription_id=excluded.stripe_subscription_id,
                      subscription_plan=excluded.subscription_plan,
                      subscription_billing_cycle=excluded.subscription_billing_cycle,
                      subscription_status=excluded.subscription_status,
                      subscription_renewal_date=excluded.subscription_renewal_date,
                      updated_at=excluded.updated_at
                    """,
                    (
                        owner_subject, stripe_subscription_id, subscription_plan, subscription_billing_cycle,
                        subscription_status, subscription_renewal_date, now, now,
                    ),
                )
                self._sqlite_conn.commit()
            return
        cur = self._pg_cursor()
        cur.execute(
            f"""INSERT INTO user_billing_profiles
            (owner_subject, stripe_subscription_id, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, created_at, updated_at)
            VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
            ON CONFLICT (owner_subject) DO UPDATE SET
              stripe_subscription_id=EXCLUDED.stripe_subscription_id,
              subscription_plan=EXCLUDED.subscription_plan,
              subscription_billing_cycle=EXCLUDED.subscription_billing_cycle,
              subscription_status=EXCLUDED.subscription_status,
              subscription_renewal_date=EXCLUDED.subscription_renewal_date,
              updated_at=EXCLUDED.updated_at
            """,
            (
                owner_subject, stripe_subscription_id, subscription_plan, subscription_billing_cycle,
                subscription_status, subscription_renewal_date, now, now,
            ),
        )
        cur.close()
        self._pg.commit()

    def update_profile_subscription(
        self,
        owner_subject: str,
        *,
        subscription_plan: str | None,
        subscription_billing_cycle: str | None,
        subscription_status: str | None,
        subscription_renewal_date: str | None,
    ) -> dict:
        now = utc_now_iso()
        if self._sqlite_conn is not None:
            with self._sqlite_lock:
                self._sqlite_conn.execute(
                    """INSERT INTO user_profiles
                    (owner_subject, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(owner_subject) DO UPDATE SET
                      subscription_plan=excluded.subscription_plan,
                      subscription_billing_cycle=excluded.subscription_billing_cycle,
                      subscription_status=excluded.subscription_status,
                      subscription_renewal_date=excluded.subscription_renewal_date,
                      updated_at=excluded.updated_at
                    """,
                    (
                        owner_subject, subscription_plan, subscription_billing_cycle,
                        subscription_status, subscription_renewal_date, now, now,
                    ),
                )
                self._sqlite_conn.commit()
        else:
            cur = self._pg_cursor()
            cur.execute(
                f"""INSERT INTO user_profiles
                (owner_subject, subscription_plan, subscription_billing_cycle, subscription_status, subscription_renewal_date, created_at, updated_at)
                VALUES ({self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param}, {self.param})
                ON CONFLICT (owner_subject) DO UPDATE SET
                  subscription_plan=EXCLUDED.subscription_plan,
                  subscription_billing_cycle=EXCLUDED.subscription_billing_cycle,
                  subscription_status=EXCLUDED.subscription_status,
                  subscription_renewal_date=EXCLUDED.subscription_renewal_date,
                  updated_at=EXCLUDED.updated_at
                """,
                (
                    owner_subject, subscription_plan, subscription_billing_cycle,
                    subscription_status, subscription_renewal_date, now, now,
                ),
            )
            cur.close()
            self._pg.commit()
        return self.get_user_profile_quiz(owner_subject) or {}

    def list_shipments_for_offer(self, offer_id: str) -> list[dict]:
        query = (
            f"SELECT shipment_id, offer_id, from_subject, to_subject, from_listing_id, to_listing_id, "
            f"from_name, from_address_line1, from_address_line2, from_city, from_state, from_postal_code, from_country, "
            f"to_name, to_address_line1, to_address_line2, to_city, to_state, to_postal_code, to_country, "
            f"carrier, service_level, tracking_number, label_url, status, tracking_status, tracking_status_details, tracking_status_updated_at, tracking_eta, tracking_history_json, shipped_at, last_ship_reminder_at, ship_reminder_count, created_at, updated_at "
            f"FROM trade_shipments WHERE offer_id = {self.param} ORDER BY created_at ASC"
        )
        keys = [
            "shipment_id", "offer_id", "from_subject", "to_subject", "from_listing_id", "to_listing_id",
            "from_name", "from_address_line1", "from_address_line2", "from_city", "from_state", "from_postal_code", "from_country",
            "to_name", "to_address_line1", "to_address_line2", "to_city", "to_state", "to_postal_code", "to_country",
            "carrier", "service_level", "tracking_number", "label_url", "status", "tracking_status", "tracking_status_details", "tracking_status_updated_at", "tracking_eta", "tracking_history_json", "shipped_at", "last_ship_reminder_at", "ship_reminder_count", "created_at", "updated_at",
        ]
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query, (offer_id,)).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (offer_id,))
            rows = cur.fetchall()
            cur.close()
        out: list[dict] = []
        for row in rows:
            item = dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)}
            try:
                history = json.loads(item.get("tracking_history_json") or "[]")
                item["tracking_history"] = history if isinstance(history, list) else []
            except Exception:
                item["tracking_history"] = []
            out.append(item)
        return out

    def get_trade_shipment_by_id(self, shipment_id: str) -> dict | None:
        query = (
            f"SELECT shipment_id, offer_id, from_subject, to_subject, from_listing_id, to_listing_id, "
            f"from_name, from_address_line1, from_address_line2, from_city, from_state, from_postal_code, from_country, "
            f"to_name, to_address_line1, to_address_line2, to_city, to_state, to_postal_code, to_country, "
            f"carrier, service_level, tracking_number, label_url, status, tracking_status, tracking_status_details, tracking_status_updated_at, tracking_eta, tracking_history_json, shipped_at, last_ship_reminder_at, ship_reminder_count, created_at, updated_at "
            f"FROM trade_shipments WHERE shipment_id = {self.param} LIMIT 1"
        )
        keys = [
            "shipment_id", "offer_id", "from_subject", "to_subject", "from_listing_id", "to_listing_id",
            "from_name", "from_address_line1", "from_address_line2", "from_city", "from_state", "from_postal_code", "from_country",
            "to_name", "to_address_line1", "to_address_line2", "to_city", "to_state", "to_postal_code", "to_country",
            "carrier", "service_level", "tracking_number", "label_url", "status", "tracking_status", "tracking_status_details", "tracking_status_updated_at", "tracking_eta", "tracking_history_json", "shipped_at", "last_ship_reminder_at", "ship_reminder_count", "created_at", "updated_at",
        ]
        if self._sqlite_conn is not None:
            row = self._sqlite_conn.execute(query, (shipment_id,)).fetchone()
        else:
            cur = self._pg_cursor()
            cur.execute(query, (shipment_id,))
            row = cur.fetchone()
            cur.close()
        if not row:
            return None
        item = dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)}
        try:
            history = json.loads(item.get("tracking_history_json") or "[]")
            item["tracking_history"] = history if isinstance(history, list) else []
        except Exception:
            item["tracking_history"] = []
        return item

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

    def update_trade_shipment_status(self, *, shipment_id: str, status: str, shipped_at: str | None = None) -> dict | None:
        shipment = self.get_trade_shipment_by_id(shipment_id)
        if not shipment:
            return None
        next_shipped_at = shipped_at
        if next_shipped_at is None and str(status or "").lower() in {"shipped", "delivered"}:
            next_shipped_at = str(shipment.get("shipped_at") or "") or utc_now_iso()
        if next_shipped_at is None:
            next_shipped_at = shipment.get("shipped_at")
        self.execute(
            f"""UPDATE trade_shipments
            SET status = {self.param}, shipped_at = {self.param}, updated_at = {self.param}
            WHERE shipment_id = {self.param}""",
            (status, next_shipped_at, utc_now_iso(), shipment_id),
        )
        self.commit()
        return self.get_trade_shipment_by_id(shipment_id)

    def update_trade_shipment_tracking(
        self,
        *,
        shipment_id: str,
        status: str,
        tracking_status: str | None = None,
        tracking_status_details: str | None = None,
        tracking_status_updated_at: str | None = None,
        tracking_eta: str | None = None,
        tracking_history: list[dict] | None = None,
        shipped_at: str | None = None,
    ) -> dict | None:
        shipment = self.get_trade_shipment_by_id(shipment_id)
        if not shipment:
            return None
        next_shipped_at = shipped_at
        if next_shipped_at is None and str(status or "").lower() in {"shipped", "delivered", "out_for_delivery"}:
            next_shipped_at = str(shipment.get("shipped_at") or "") or utc_now_iso()
        if next_shipped_at is None:
            next_shipped_at = shipment.get("shipped_at")
        history_json = json.dumps(tracking_history if isinstance(tracking_history, list) else shipment.get("tracking_history") or [])
        self.execute(
            f"""UPDATE trade_shipments
            SET status = {self.param}, tracking_status = {self.param}, tracking_status_details = {self.param},
                tracking_status_updated_at = {self.param}, tracking_eta = {self.param}, tracking_history_json = {self.param},
                shipped_at = {self.param}, updated_at = {self.param}
            WHERE shipment_id = {self.param}""",
            (
                status,
                tracking_status,
                tracking_status_details,
                tracking_status_updated_at,
                tracking_eta,
                history_json,
                next_shipped_at,
                utc_now_iso(),
                shipment_id,
            ),
        )
        self.commit()
        return self.get_trade_shipment_by_id(shipment_id)

    def mark_shipment_reminder_sent(self, shipment_id: str) -> dict | None:
        shipment = self.get_trade_shipment_by_id(shipment_id)
        if not shipment:
            return None
        current_count = int(shipment.get("ship_reminder_count") or 0)
        now = utc_now_iso()
        self.execute(
            f"""UPDATE trade_shipments
            SET last_ship_reminder_at = {self.param}, ship_reminder_count = {self.param}, updated_at = {self.param}
            WHERE shipment_id = {self.param}""",
            (now, current_count + 1, now, shipment_id),
        )
        self.commit()
        return self.get_trade_shipment_by_id(shipment_id)

    def list_shipments_pending_reminder(self) -> list[dict]:
        query = (
            f"SELECT shipment_id, offer_id, from_subject, to_subject, tracking_number, label_url, status, "
            f"tracking_status, tracking_status_details, tracking_status_updated_at, tracking_eta, tracking_history_json, "
            f"carrier, service_level, created_at, shipped_at, last_ship_reminder_at, ship_reminder_count "
            f"FROM trade_shipments "
            f"WHERE COALESCE(label_url, '') <> '' "
            f"AND LOWER(COALESCE(status, '')) NOT IN ('shipped', 'delivered', 'cancelled')"
        )
        keys = [
            "shipment_id", "offer_id", "from_subject", "to_subject", "tracking_number", "label_url", "status",
            "tracking_status", "tracking_status_details", "tracking_status_updated_at", "tracking_eta", "tracking_history_json",
            "carrier", "service_level", "created_at", "shipped_at", "last_ship_reminder_at", "ship_reminder_count",
        ]
        if self._sqlite_conn is not None:
            rows = self._sqlite_conn.execute(query).fetchall()
        else:
            cur = self._pg_cursor()
            cur.execute(query)
            rows = cur.fetchall()
            cur.close()
        out: list[dict] = []
        for row in rows:
            out.append(dict(row) if isinstance(row, sqlite3.Row) else {k: row[idx] for idx, k in enumerate(keys)})
        return out

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
            "shipped_at": None,
            "last_ship_reminder_at": None,
            "ship_reminder_count": 0,
            "created_at": now,
            "updated_at": now,
        }
