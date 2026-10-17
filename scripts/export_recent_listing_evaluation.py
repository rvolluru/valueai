"""Run inside the API task network: read-only DB snapshot for a bounded model evaluation."""
import json
import os
from datetime import datetime, timezone

import boto3
import psycopg
from psycopg.rows import dict_row


with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15,
                     options="-c default_transaction_read_only=on -c statement_timeout=15000",
                     row_factory=dict_row) as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT listing_id, title, category, brand, condition, size, estimated_value, "
                       "source_item_id, analysis_json, status, created_at, updated_at FROM listings "
                       "ORDER BY created_at DESC, listing_id DESC LIMIT 10")
        listings = cursor.fetchall()
snapshot = {"exported_at": datetime.now(timezone.utc).isoformat(),
            "selection": "Latest 10 by created_at DESC, listing_id DESC; no status filter",
            "listings": listings}
boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1")).put_object(
    Bucket=os.environ["EVAL_EXPORT_BUCKET"], Key=os.environ["EVAL_EXPORT_KEY"],
    Body=json.dumps(snapshot, default=str).encode(), ContentType="application/json",
    ServerSideEncryption="AES256")
print(json.dumps({"event": "read_only_evaluation_export", "count": len(listings)}))
