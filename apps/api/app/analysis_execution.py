"""Serialize deliveries of one analysis job, including across production workers."""
from contextvars import ContextVar
from functools import wraps

from .db import Database
from .logging_utils import log_json

_held_jobs = ContextVar("held_analysis_jobs", default=frozenset())


class AnalysisJobBusy(RuntimeError):
    pass


def recover_analysis_success(db, job_id, owner_subject):
    """Recover a crash between committing the listing and marking its job done."""
    job = db.get_listing_analysis_job(job_id, owner_subject)
    if not job or job.get("status") == "succeeded":
        return job
    listing = db.get_listing_by_id(job["listing_id"])
    if not listing or listing.get("owner_subject") != owner_subject:
        return job
    analysis = listing.get("analysis") or {}
    checkpoint = (analysis.get("debug") or {}).get("analysis_execution") or {}
    if (checkpoint.get("job_id") == job_id and analysis.get("item_id")
            and listing.get("source_item_id") == analysis["item_id"]):
        return db.update_listing_analysis_job(job_id=job_id, owner_subject=owner_subject,
            status="succeeded", stage="completed_recovered", result_item_id=analysis["item_id"], error="", completed=True)
    return job


def guard_analysis_job(function=None, *, resume_components=False):
    if function is None:
        return lambda wrapped: guard_analysis_job(wrapped, resume_components=resume_components)
    @wraps(function)
    def guarded(**kwargs):
        job_id = kwargs.get("job_id")
        if not job_id:
            return function(**kwargs)
        key = (kwargs["settings"].database_url, job_id)
        if key in _held_jobs.get():
            return function(**kwargs)
        db = Database(key[0])
        try:
            with db.analysis_execution_lock(job_id) as acquired:
                if not acquired:
                    raise AnalysisJobBusy(f"Analysis job already executing: {job_id}")
                job = db.get_listing_analysis_job(job_id, kwargs["owner_subject"])
                db.commit()  # Never leave an idle transaction open during model calls.
                if not job or job["listing_id"] != kwargs["listing_id"]:
                    raise ValueError("Analysis job does not belong to this listing/owner")
                job = recover_analysis_success(db, job_id, kwargs["owner_subject"])
                db.commit()
                if job["status"] == "succeeded":
                    pending = resume_components and any(component["status"] in {"queued", "running", "retrying"}
                        for component in db.list_pipeline_components(job_id))
                    if not pending:
                        log_json("listing_analysis_duplicate_skipped", job_id=job_id, listing_id=job["listing_id"])
                        return
                token = _held_jobs.set(_held_jobs.get() | {key})
                try:
                    return function(**kwargs)
                finally:
                    _held_jobs.reset(token)
        finally:
            db.close()
    return guarded
