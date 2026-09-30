from __future__ import annotations

import json
import signal
import time
from typing import Any

import boto3

from .analysis_queue import ANALYSIS_MESSAGE_TYPE
from .deps import get_gpt_item_profiler, get_valuation_service
from .logging_utils import log_json
from .main import _process_shipping_reminders_once, _run_listing_analysis_for_existing_listing_job
from .settings import get_settings

_stopping = False


def _request_stop(*_: Any) -> None:
    global _stopping
    _stopping = True


def process_message(payload: dict[str, Any]) -> None:
    if payload.get("type") != ANALYSIS_MESSAGE_TYPE or int(payload.get("version") or 0) != 1:
        raise ValueError("Unsupported analysis message")

    required = ("listing_id", "owner_subject", "job_id")
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise ValueError(f"Analysis message missing: {', '.join(missing)}")

    settings = get_settings()
    _run_listing_analysis_for_existing_listing_job(
        listing_id=str(payload["listing_id"]),
        owner_subject=str(payload["owner_subject"]),
        category=payload.get("category"),
        item_size=payload.get("item_size"),
        user_condition=payload.get("user_condition"),
        item_description=payload.get("item_description"),
        brand_override=payload.get("brand_override"),
        debug=bool(payload.get("debug", True)),
        settings=settings,
        valuation_service=get_valuation_service(),
        gpt_item_profiler=get_gpt_item_profiler(),
        stage_images_after_analysis=bool(payload.get("stage_images_after_analysis")),
        job_id=str(payload["job_id"]),
    )


def run() -> None:
    settings = get_settings()
    queue_url = str(settings.sqs_analysis_queue_url or "").strip()
    if not queue_url:
        raise RuntimeError("SQS_ANALYSIS_QUEUE_URL is required")

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    log_json("analysis_worker_started", queue_url=queue_url)
    next_shipping_reminder_at = 0.0

    while not _stopping:
        now = time.monotonic()
        if settings.shipping_reminder_enabled and now >= next_shipping_reminder_at:
            try:
                _process_shipping_reminders_once(settings=settings)
            except Exception as exc:
                log_json("shipping_reminder_worker_error", error=str(exc)[:1000])
            next_shipping_reminder_at = now + max(60, settings.shipping_reminder_poll_seconds)
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=settings.sqs_analysis_wait_time_seconds,
            VisibilityTimeout=settings.sqs_analysis_visibility_timeout_seconds,
        )
        for message in response.get("Messages", []):
            receipt_handle = str(message.get("ReceiptHandle") or "")
            try:
                payload = json.loads(str(message.get("Body") or "{}"))
                if not isinstance(payload, dict):
                    raise ValueError("Analysis message must be an object")
                process_message(payload)
            except Exception as exc:
                log_json("analysis_worker_message_failed", error=str(exc)[:1000])
                continue
            if receipt_handle:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

    log_json("analysis_worker_stopped")


if __name__ == "__main__":
    run()
