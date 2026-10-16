import json
import threading
from types import SimpleNamespace

import pytest

from app.analysis_execution import AnalysisJobBusy, guard_analysis_job
from app.db import Database


def setup_job(tmp_path):
    settings = SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'analysis.db'}")
    db = Database(settings.database_url)
    db.initialize()
    db.create_listing_analysis_job(job_id="job", listing_id="listing", owner_subject="owner", max_attempts=2)
    return settings, db


def test_completed_delivery_is_skipped_and_owner_cannot_be_changed(tmp_path):
    settings, db = setup_job(tmp_path)
    calls = []
    @guard_analysis_job
    def run(**kwargs):
        calls.append(kwargs)
    db.update_listing_analysis_job(job_id="job", owner_subject="owner", status="succeeded", result_item_id="original-result", completed=True)
    run(settings=settings, job_id="job", listing_id="listing", owner_subject="owner")
    assert calls == []
    assert db.get_listing_analysis_job("job")["result_item_id"] == "original-result"
    with pytest.raises(ValueError):
        run(settings=settings, job_id="job", listing_id="listing", owner_subject="different-owner")


def test_two_workers_cannot_execute_the_same_job_and_guard_is_reentrant(tmp_path):
    settings, db = setup_job(tmp_path)
    entered, release = threading.Event(), threading.Event()
    calls, errors = [], []
    @guard_analysis_job
    def inner(**kwargs):
        calls.append("inner")
    @guard_analysis_job
    def outer(**kwargs):
        inner(**kwargs)
        entered.set()
        assert release.wait(5)
    args = dict(settings=settings, job_id="job", listing_id="listing", owner_subject="owner")
    def first():
        try:
            outer(**args)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(AnalysisJobBusy):
            outer(**args)
    finally:
        release.set()
        thread.join(5)
    assert not errors
    assert calls == ["inner"]
    # The lock is released after processing, including on exceptions.
    inner(**args)
    assert calls == ["inner", "inner"]


def test_postgres_execution_uses_session_advisory_lock_and_releases_on_error(monkeypatch):
    db = object.__new__(Database)
    db.url, db._sqlite_conn = "postgresql://test/database", None
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params): queries.append((sql, params))
    class Pg:
        closed = False
        def cursor(self): return Cursor()
        def commit(self): pass
    db._pg = Pg()
    monkeypatch.setattr(db, "fetchone", lambda sql, params: (queries.append((sql, params)) or (True,)))
    with pytest.raises(RuntimeError):
        with db.analysis_execution_lock("job") as acquired:
            assert acquired
            raise RuntimeError("worker failed")
    assert "pg_try_advisory_lock" in queries[0][0]
    assert "pg_advisory_unlock" in queries[1][0]
    assert queries[0][1] == queries[1][1]


@pytest.mark.parametrize("stage_error", [TimeoutError, RuntimeError])
def test_staging_failure_retries_only_staging_and_keeps_success(tmp_path, monkeypatch, stage_error):
    from app import main
    settings, db = setup_job(tmp_path)
    calls = []
    async def analyze(**kwargs):
        calls.append("analysis")
        db.update_listing_analysis_job(job_id="job", owner_subject="owner", status="succeeded", result_item_id="priced-item", completed=True)
    async def stage(**kwargs):
        calls.append("staging")
        raise stage_error("optional presentation failed")
    monkeypatch.setattr(main, "_run_listing_analysis_job", analyze)
    monkeypatch.setattr(main, "_run_listing_image_staging_job", stage)
    main._run_listing_analysis_job_threaded(
        listing_id="listing", owner_subject="owner", files=[], category="clothes", item_size="S",
        user_condition="LikeNew", item_description="Dress", debug=True, settings=settings,
        valuation_service=None, gpt_item_profiler=None, job_id="job", stage_images_after_analysis=True,
    )
    assert calls == ["analysis", "staging", "staging"]
    assert db.get_listing_analysis_job("job")["status"] == "succeeded"
    assert db.get_listing_analysis_job("job")["result_item_id"] == "priced-item"


def test_historical_item_owner_link_survives_new_analysis(tmp_path):
    settings, db = setup_job(tmp_path)
    db.insert_listing(listing_id="listing", owner_subject="owner", owner_name="Owner", title="Dress",
        mode="trade", category="clothes", brand="RHODE", condition="LikeNew", size="S",
        estimated_value=175, city="", image=None, images=[], description="", wants="", tags=[],
        source_item_id="first", analysis=None, status="Review")
    db.link_analysis_item("first", "listing", "owner", "job")
    db.execute("UPDATE listings SET source_item_id=? WHERE listing_id=?", ("second", "listing"))
    db.commit()
    assert db.get_listing_by_source_item_id("first")["owner_subject"] == "owner"
    assert db.get_listing_by_source_item_id("first")["listing_id"] == "listing"
    db.link_analysis_item("unauthorized", "listing", "other-owner", "job")
    assert db.get_listing_by_source_item_id("unauthorized") is None


def test_saved_listing_checkpoint_recovers_success_without_rerunning_models(tmp_path):
    settings, db = setup_job(tmp_path)
    db.insert_listing(listing_id="listing", owner_subject="owner", owner_name="Owner", title="Dress",
        mode="trade", category="clothes", brand="RHODE", condition="LikeNew", size="S",
        estimated_value=175, city="", image=None, images=[], description="", wants="", tags=[],
        source_item_id="priced", analysis={"item_id": "priced", "debug": {"analysis_execution": {"job_id": "job"}}}, status="Review")
    @guard_analysis_job
    def run(**kwargs):
        pytest.fail("Committed analysis must not run again")
    run(settings=settings, job_id="job", listing_id="listing", owner_subject="owner")
    result = db.get_listing_analysis_job("job")
    assert result["status"] == "succeeded"
    assert result["result_item_id"] == "priced"
    # A late timeout cannot erase the committed success or change the result ID.
    db.update_listing_analysis_job(job_id="job", owner_subject="owner", status="retrying", result_item_id="wrong")
    assert db.get_listing_analysis_job("job")["result_item_id"] == "priced"
    assert db.get_listing_analysis_job("job")["status"] == "succeeded"


@pytest.mark.parametrize("fail", [False, True])
def test_queue_visibility_renewed_and_only_completed_deliveries_acknowledged(monkeypatch, fail):
    from app import analysis_worker as worker
    renewed = threading.Event()
    class Sqs:
        def __init__(self):
            self.deleted = []
        def change_message_visibility(self, **kwargs):
            assert kwargs["VisibilityTimeout"] == 600
            renewed.set()
        def delete_message(self, **kwargs):
            self.deleted.append(kwargs)
    sqs = Sqs()
    def process(payload):
        assert renewed.wait(2)
        if fail:
            raise AnalysisJobBusy("owned by another worker")
    monkeypatch.setattr(worker, "process_message", process)
    worker.process_received_message(sqs, "queue", {"MessageId": "message", "ReceiptHandle": "receipt",
        "Body": json.dumps({"job_id": "job"}), "Attributes": {"ApproximateReceiveCount": "2"}}, 600)
    assert bool(sqs.deleted) is not fail


def test_queue_visibility_is_renewed_periodically_while_work_is_running():
    from app.analysis_worker import message_visibility_heartbeat
    renewed_twice = threading.Event()
    calls = []
    class Sqs:
        def change_message_visibility(self, **kwargs):
            calls.append(kwargs)
            if len(calls) >= 2:
                renewed_twice.set()
    with message_visibility_heartbeat(Sqs(), "queue", "receipt", 3):
        assert renewed_twice.wait(3)
    count = len(calls)
    assert count >= 2
