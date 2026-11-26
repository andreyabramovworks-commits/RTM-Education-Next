"""Process durable outbox jobs without re-sending ambiguous Bitrix tasks."""
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bitrix_delivery import DeliveryError, configured, deliver
from app.db import SessionLocal
from app.models import Assignment, AssignmentCampaign, OutboxJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def recover_interrupted_jobs(db: Session) -> None:
    jobs = db.scalars(select(OutboxJob).where(OutboxJob.status == "sending")).all()
    for job in jobs:
        if job.kind == "bitrix_notification":
            job.status = "retry"
            job.next_run_at = datetime.now(timezone.utc)
        else:
            job.status = "uncertain"
            job.last_error = "WORKER_INTERRUPTED_RESULT_UNKNOWN"
    db.commit()


def claim_job(db: Session) -> uuid.UUID | None:
    job = db.scalar(select(OutboxJob).where(OutboxJob.status.in_(["pending", "retry"]),
        OutboxJob.next_run_at <= datetime.now(timezone.utc)).order_by(OutboxJob.created_at, OutboxJob.id)
        .with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    job.status = "sending"
    job.attempts += 1
    db.commit()
    return job.id


def process_job(db: Session, job_id: uuid.UUID) -> None:
    job = db.get(OutboxJob, job_id)
    if job is None or job.status != "sending":
        return
    assignment = db.get(Assignment, uuid.UUID(job.payload["assignment_id"]))
    campaign = db.get(AssignmentCampaign, assignment.campaign_id) if assignment else None
    if campaign is None:
        job.status = "failed"
        job.last_error = "ASSIGNMENT_UNAVAILABLE"
        db.commit()
        return
    try:
        external_id = deliver(job.kind, job.payload, job.idempotency_key, campaign.title)
    except DeliveryError as exc:
        job.last_error = str(exc)
        if exc.uncertain:
            job.status = "uncertain"
        elif exc.retryable and job.attempts < 10:
            job.status = "retry"
            job.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=min(3600, 2 ** job.attempts * 15))
        else:
            job.status = "failed"
        logger.warning("Outbox job %s: %s", job.id, job.last_error)
    else:
        job.status = "sent"
        job.external_id = external_id
        job.last_error = None
    db.commit()


def run() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is required")
    with SessionLocal() as db:
        recover_interrupted_jobs(db)
    warned = False
    while True:
        if not configured():
            if not warned:
                logger.warning("Bitrix delivery waits for client credentials and installation tokens")
                warned = True
            time.sleep(10)
            continue
        warned = False
        try:
            with SessionLocal() as db:
                job_id = claim_job(db)
                if job_id is not None:
                    process_job(db, job_id)
                else:
                    time.sleep(3)
        except Exception:
            logger.exception("Outbox worker cycle failed")
            time.sleep(5)


if __name__ == "__main__":
    run()
