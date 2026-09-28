from __future__ import annotations

import json

from app.analysis_queue import enqueue_listing_analysis
from app.settings import Settings


class _SqsClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


def test_enqueue_is_disabled_without_queue_url(monkeypatch):
    monkeypatch.setattr("app.analysis_queue.boto3.client", lambda *_args, **_kwargs: None)

    queued = enqueue_listing_analysis(Settings(sqs_analysis_queue_url=None), {"job_id": "job-1"})

    assert queued is False


def test_enqueue_sends_versioned_listing_message(monkeypatch):
    client = _SqsClient()
    monkeypatch.setattr("app.analysis_queue.boto3.client", lambda *_args, **_kwargs: client)
    settings = Settings(
        aws_region="us-east-1",
        sqs_analysis_queue_url="https://sqs.us-east-1.amazonaws.com/123/analysis",
    )

    queued = enqueue_listing_analysis(
        settings,
        {
            "listing_id": "listing-1",
            "owner_subject": "user-1",
            "job_id": "job-1",
        },
    )

    assert queued is True
    assert client.messages[0]["QueueUrl"] == settings.sqs_analysis_queue_url
    body = json.loads(client.messages[0]["MessageBody"])
    assert body == {
        "type": "listing_analysis",
        "version": 1,
        "listing_id": "listing-1",
        "owner_subject": "user-1",
        "job_id": "job-1",
    }
