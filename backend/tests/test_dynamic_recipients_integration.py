import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app import directory
from app.campaigns import sync_new_employee_assignments
from app.db import SessionLocal
from app.main import app
from app.models import Assignment, AssignmentAction, AssignmentCampaign, BrowserSession, Course, Department, Employee, OutboxJob


def test_new_department_employees_are_assigned_once_after_rule_enabled(monkeypatch):
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    parent_id = 1_300_000_000 + marker
    child_id = parent_id + 1
    teacher_bitrix_id = parent_id + 100
    old_id, new_id, disabled_id, late_id = (parent_id + n for n in (101, 102, 103, 104))
    token = f"dynamic-{marker}"
    with SessionLocal() as db:
        teacher = Employee(bitrix_id=teacher_bitrix_id, first_name="Test", last_name="Teacher", local_role="teacher")
        old = Employee(bitrix_id=old_id, first_name="Old", last_name="Learner", department_ids=[parent_id])
        db.add_all([teacher, old,
            Department(bitrix_id=parent_id, parent_id=None, title="Parent", updated_at=datetime.now(timezone.utc)),
            Department(bitrix_id=child_id, parent_id=parent_id, title="Child", updated_at=datetime.now(timezone.utc))])
        db.flush()
        course = Course(title="Dynamic recipients test", status="active", created_by=teacher.id)
        db.add(course)
        db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=teacher.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
        course_id = course.id
    client = TestClient(app)
    headers = {"Cookie": f"rtm_next_session={token}"}
    campaign_id = None

    def sync_people(*extra_ids):
        rows = [{"ID": str(old_id), "NAME": "Old", "LAST_NAME": "Learner", "ACTIVE": True,
                 "UF_DEPARTMENT": [parent_id]}]
        rows.extend({"ID": str(bitrix_id), "NAME": "New", "LAST_NAME": str(bitrix_id),
                     "ACTIVE": True, "UF_DEPARTMENT": [child_id]} for bitrix_id in extra_ids)
        monkeypatch.setattr(directory, "list_users", lambda _token: rows)
        with SessionLocal() as db:
            directory.sync_directory(db, "test-token")
            return sync_new_employee_assignments(db)

    try:
        draft = client.post("/admin/campaigns", headers=headers, json={
            "target_type": "course", "target_id": str(course_id), "title": "Dynamic campaign",
            "department_ids": [parent_id], "include_subdepartments": True,
            "include_new_employees": True, "due_mode": "relative", "due_days": 7,
            "notify_enabled": True, "task_enabled": True,
            "task_title": "Read {course}", "task_description": "Open {link}"})
        assert draft.status_code == 201, draft.text
        campaign_id = uuid.UUID(draft.json()["id"])
        assert draft.json()["include_new_employees"] is True
        launched = client.post(f"/admin/campaigns/{campaign_id}/launch", headers=headers,
            json={"confirmed": True})
        assert launched.status_code == 200, launched.text
        assert sync_people(new_id) == 1
        assert sync_people(new_id) == 0
        with SessionLocal() as db:
            assignment = db.scalar(select(Assignment).join(Employee).where(
                Assignment.campaign_id == campaign_id, Employee.bitrix_id == new_id))
            assert assignment is not None
            assert assignment.recipient_source["type"] == "new_employee_department"
            assert assignment.recipient_source["department_ids"] == [child_id]
            assert db.scalar(select(func.count()).select_from(OutboxJob).where(
                OutboxJob.idempotency_key.like(f"{assignment.id}:%"))) == 2
            assert db.scalar(select(func.count()).select_from(AssignmentAction).where(
                AssignmentAction.assignment_id == assignment.id)) == 1
        disabled = client.put(f"/admin/campaigns/{campaign_id}/new-employees", headers=headers,
            json={"enabled": False, "reason": "Pause onboarding intake", "confirmed": True})
        assert disabled.status_code == 200 and disabled.json()["include_new_employees"] is False
        assert sync_people(new_id, disabled_id) == 0
        enabled = client.put(f"/admin/campaigns/{campaign_id}/new-employees", headers=headers,
            json={"enabled": True, "reason": "Resume onboarding intake", "confirmed": True})
        assert enabled.status_code == 200 and enabled.json()["include_new_employees"] is True
        assert sync_people(new_id, disabled_id, late_id) == 1
        with SessionLocal() as db:
            ids = db.scalars(select(Employee.bitrix_id).join(Assignment).where(
                Assignment.campaign_id == campaign_id)).all()
            assert sorted(ids) == sorted([old_id, new_id, late_id])
            campaign = db.get(AssignmentCampaign, campaign_id)
            assert len(campaign.recipient_policy["changes"]) == 2
    finally:
        with SessionLocal() as db:
            if campaign_id:
                assignments = db.scalars(select(Assignment).where(Assignment.campaign_id == campaign_id)).all()
                for assignment in assignments:
                    db.execute(delete(AssignmentAction).where(AssignmentAction.assignment_id == assignment.id))
                    db.execute(delete(OutboxJob).where(OutboxJob.idempotency_key.like(f"{assignment.id}:%")))
                db.execute(delete(Assignment).where(Assignment.campaign_id == campaign_id))
                db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id))
            db.execute(delete(Course).where(Course.id == course_id))
            employee_ids = [teacher_bitrix_id, old_id, new_id, disabled_id, late_id]
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(
                select(Employee.id).where(Employee.bitrix_id.in_(employee_ids)))))
            db.execute(delete(Employee).where(Employee.bitrix_id.in_(employee_ids)))
            db.execute(delete(Department).where(Department.bitrix_id.in_([parent_id, child_id])))
            db.commit()
