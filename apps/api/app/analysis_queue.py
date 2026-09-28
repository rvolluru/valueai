from __future__ import annotations

import json
from typing import Any

import boto3

from .logging_utils import log_json
from .settings import Settings

ANALYSIS_MESSAGE_TYPE = "listing_analysis"


def enqueue_listing_analysis(settings: Settings, payload: dict[str, Any]) -> bool:
    queue_url = str(settings.sqs_analysis_queue_url or "").strip()
    if not queue_url:
        return False

    message = {"type": ANALYSIS_MESSAGE_TYPE, "version": 1, **payload}
    boto3.client("sqs", region_name=settings.aws_region).send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message, separators=(",", ":")),
    )
    log_json(
        "listing_analysis_sqs_enqueued",
        listing_id=payload.get("listing_id"),
        actor=payload.get("owner_subject"),
        job_id=payload.get("job_id"),
    )
    return True
