import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app import worker
from app.bitrix_delivery import DeliveryError
from app.db import SessionLocal
from app.models import Assignment, AssignmentCampaign, Course, Employee, OutboxJob


def test_worker_records_confirmed_delivery_and_quarantines_ambiguous_task(monkeypatch):
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    with SessionLocal() as db:
        person = Employee(bitrix_id=1_250_000_000 + marker, first_name="Test", last_name="Worker")
        db.add(person); db.flush()
        course = Course(title="Delivery", created_by=person.id)
        db.add(course); db.flush()
        campaign = AssignmentCampaign(target_type="course", target_id=course.id, title="Delivery",
            status="active", recipient_policy={"employee_ids": [person.bitrix_id]}, reviewer_ids=[],
            due_mode="relative", due_days=7, notify_enabled=True, task_enabled=True,
            task_title="Delivery task", task_description="Read", created_by=person.id)
        db.add(campaign); db.flush()
        assignment = Assignment(campaign_id=campaign.id, employee_id=person.id,
            status="not_started", assigned_at=datetime.now(timezone.utc),
            due_at=datetime.now(timezone.utc) + timedelta(days=7))
        db.add(assignment); db.flush()
        notify = OutboxJob(kind="bitrix_notification", idempotency_key=f"{assignment.id}:notification",
            payload={"assignment_id": str(assignment.id), "bitrix_id": person.bitrix_id})
        task = OutboxJob(kind="bitrix_task", idempotency_key=f"{assignment.id}:task",
            payload={"assignment_id": str(assignment.id), "bitrix_id": person.bitrix_id,
                     "title": "Delivery task", "description": "Read"})
        db.add_all([notify, task]); db.commit()
        ids = (person.id, course.id, campaign.id, assignment.id, notify.id, task.id)
    def fake_deliver(kind, payload, key, title):
        assert payload["assignment_id"] == str(ids[3]) and title == "Delivery"
        if kind == "bitrix_task":
            raise DeliveryError("NETWORK_RESULT_UNKNOWN", uncertain=True)
        return "12345"
    monkeypatch.setattr(worker, "deliver", fake_deliver)
    try:
        with SessionLocal() as db:
            first_id = worker.claim_job(db)
            assert first_id == ids[4]
            worker.process_job(db, first_id)
            second_id = worker.claim_job(db)
            assert second_id == ids[5]
            worker.process_job(db, second_id)
            assert worker.claim_job(db) is None
            sent = db.get(OutboxJob, ids[4])
            uncertain = db.get(OutboxJob, ids[5])
            assert sent.status == "sent" and sent.external_id == "12345"
            assert uncertain.status == "uncertain" and uncertain.attempts == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(OutboxJob).where(OutboxJob.id.in_(ids[4:])))
            db.execute(delete(Assignment).where(Assignment.id == ids[3]))
            db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id == ids[2]))
            db.execute(delete(Course).where(Course.id == ids[1]))
            db.execute(delete(Employee).where(Employee.id == ids[0]))
            db.commit()
