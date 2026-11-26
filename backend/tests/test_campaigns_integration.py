import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.main import app
from app.models import Article, Assignment, AssignmentAction, AssignmentCampaign, BrowserSession, Course, CourseItem, CourseSection, Department, Employee, ItemCompletion, OutboxJob


def test_course_activation_campaign_launch_and_individual_visibility():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    tokens = {role: f"campaign-{marker}-{role}" for role in ("editor", "teacher", "learner", "learner2")}
    people: dict[str, Employee] = {}
    department_id = 1_400_000_000 + marker
    with SessionLocal() as db:
        db.add(Department(bitrix_id=department_id, parent_id=None, title="Test department",
                          updated_at=datetime.now(timezone.utc)))
        for index, role in enumerate(tokens):
            person = Employee(bitrix_id=1_900_000_000 + marker * 3 + index,
                first_name="Test", last_name=role, local_role=role if not role.startswith("learner") else "employee",
                department_ids=[department_id] if role == "learner" else [])
            db.add(person)
            db.flush()
            people[role] = person
            db.add(BrowserSession(token_hash=hashlib.sha256(tokens[role].encode()).hexdigest(), employee_id=person.id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        ids = {role: person.id for role, person in people.items()}
        bitrix_ids = {role: person.bitrix_id for role, person in people.items()}
        inactive = Employee(bitrix_id=1_900_000_000 + marker * 3 + len(tokens), first_name="Test",
            last_name="inactive", local_role="employee", active=False, department_ids=[department_id])
        db.add(inactive)
        db.flush()
        ids["inactive"] = inactive.id
        bitrix_ids["inactive"] = inactive.bitrix_id
        db.commit()
    client = TestClient(app)
    headers = {role: {"Cookie": f"rtm_next_session={token}"} for role, token in tokens.items()}
    course_id = None
    campaign_id = None
    department_campaign_id = None
    try:
        created = client.post("/admin/courses", headers=headers["editor"], json={"title": "Test training"})
        assert created.status_code == 201, created.text
        course_id = uuid.UUID(created.json()["id"])
        version = created.json()["row_version"]
        assert client.post(f"/admin/courses/{course_id}/activate", headers=headers["editor"],
            json={"row_version": version, "confirmed": True}).status_code == 422
        section = client.post(f"/admin/courses/{course_id}/sections", headers=headers["editor"],
            json={"title": "Start", "row_version": version})
        assert section.status_code == 201
        article = client.post(f"/admin/courses/{course_id}/sections/{section.json()['id']}/articles", headers=headers["editor"],
            json={"title": "Read me", "row_version": section.json()["row_version"]})
        assert article.status_code == 201, article.text
        body = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Important text"}]}]}
        saved = client.put(f"/admin/courses/{course_id}/articles/{article.json()['article_id']}", headers=headers["editor"],
            json={"title": "Read me", "summary": "", "body": body, "row_version": 1})
        assert saved.status_code == 200, saved.text
        activation = client.post(f"/admin/courses/{course_id}/activate", headers=headers["editor"],
            json={"row_version": article.json()["row_version"], "confirmed": True})
        assert activation.status_code == 200, activation.text
        payload = {"target_type": "course", "target_id": str(course_id), "title": "Assignment",
            "recipient_bitrix_ids": [bitrix_ids["learner"], bitrix_ids["learner"]],
            "department_ids": [department_id],
            "reviewer_bitrix_ids": [bitrix_ids["teacher"]], "due_mode": "relative", "due_days": 5,
            "notify_enabled": True, "task_enabled": True,
            "task_title": "Read {course}: {name}", "task_description": "Due {due_date}; open {link}"}
        assert client.post("/admin/campaigns", headers=headers["learner"], json=payload).status_code == 403
        draft = client.post("/admin/campaigns", headers=headers["teacher"], json=payload)
        assert draft.status_code == 201, draft.text
        campaign_id = uuid.UUID(draft.json()["id"])
        assert draft.json()["recipient_count"] == 1
        preview = client.get(f"/admin/campaigns/{campaign_id}/preview", headers=headers["teacher"])
        assert preview.status_code == 200, preview.text
        assert preview.json()["task_title"] == "Read Test training: Test learner"
        assert "https://rtmgroupdocs.fvds.ru/education-next/app" in preview.json()["task_description"]
        assert preview.json()["duplicates_excluded"] == 2
        assert preview.json()["duplicate_recipients"] == ["Test learner"]
        assert preview.json()["inactive_excluded"] == [{"bitrix_id": bitrix_ids["inactive"], "name": "Test inactive"}]
        assert preview.json()["recipients"] == [{
            "bitrix_id": bitrix_ids["learner"], "name": "Test learner", "source": "individual",
            "due_at": preview.json()["due_at"], "task_title": preview.json()["task_title"],
            "task_description": preview.json()["task_description"],
        }]
        department_only = client.post("/admin/campaigns", headers=headers["teacher"], json={
            **payload, "recipient_bitrix_ids": [], "title": "Department only"})
        assert department_only.status_code == 201, department_only.text
        assert department_only.json()["recipient_count"] == 1
        department_campaign_id = uuid.UUID(department_only.json()["id"])
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.campaign_id == campaign_id)) == 0
        launched = client.post(f"/admin/campaigns/{campaign_id}/launch", headers=headers["teacher"], json={"confirmed": True})
        assert launched.status_code == 200, launched.text
        assert client.post(f"/admin/campaigns/{campaign_id}/launch", headers=headers["teacher"], json={"confirmed": True}).status_code == 200
        learner_view = client.get("/my/assignments", headers=headers["learner"])
        assert learner_view.status_code == 200
        assert len(learner_view.json()) == 1
        assert learner_view.json()[0]["status"] == "not_started"
        assert client.get("/my/assignments", headers=headers["editor"]).json() == []
        assignment_id = learner_view.json()[0]["id"]
        delivery = client.get(f"/admin/campaigns/{campaign_id}/delivery", headers=headers["teacher"])
        assert delivery.status_code == 200 and delivery.json()["counts"]["pending"] == 2
        failed_job_id = delivery.json()["jobs"][0]["id"]
        with SessionLocal() as db:
            failed_job = db.get(OutboxJob, uuid.UUID(failed_job_id))
            failed_job.status = "failed"
            failed_job.last_error = "TEST_FAILURE"
            db.commit()
        retried = client.post(f"/admin/outbox/{failed_job_id}/retry", headers=headers["teacher"], json={
            "reason": "Retry after correcting configuration", "confirmed": True})
        assert retried.status_code == 200 and retried.json()["status"] == "retry"
        assigned_rows = client.get(f"/admin/campaigns/{campaign_id}/assignments", headers=headers["teacher"])
        assert assigned_rows.status_code == 200 and len(assigned_rows.json()) == 1
        assert client.put(f"/admin/assignments/{assignment_id}/due", headers=headers["learner"], json={
            "due_at": "2026-12-31T12:00:00+03:00", "reason": "Requested extension", "confirmed": True}).status_code == 403
        due = client.put(f"/admin/assignments/{assignment_id}/due", headers=headers["teacher"], json={
            "due_at": "2026-12-31T12:00:00+03:00", "reason": "Requested extension", "confirmed": True})
        assert due.status_code == 200, due.text
        assert client.get(f"/my/assignments/{assignment_id}", headers=headers["editor"]).status_code == 404
        detail = client.get(f"/my/assignments/{assignment_id}", headers=headers["learner"])
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == "not_started"
        assert detail.json()["course"]["sections"][0]["items"][0]["article"]["body"] == body
        assert client.post(f"/my/assignments/{assignment_id}/items/{article.json()['id']}/acknowledge",
            headers=headers["learner"]).status_code == 409
        assert client.post(f"/my/assignments/{assignment_id}/start", headers=headers["learner"]).status_code == 200
        confirmation = client.post(f"/my/assignments/{assignment_id}/items/{article.json()['id']}/acknowledge",
            headers=headers["learner"])
        assert confirmation.status_code == 200, confirmation.text
        assert confirmation.json()["assignment_status"] == "completed"
        assert client.post(f"/admin/assignments/{assignment_id}/exempt", headers=headers["teacher"], json={
            "reason": "Cannot attend now", "confirmed": True}).status_code == 409
        assert client.post(f"/my/assignments/{assignment_id}/items/{article.json()['id']}/acknowledge",
            headers=headers["learner"]).status_code == 200
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.campaign_id == campaign_id)) == 1
            assignment = db.scalar(select(Assignment).where(Assignment.campaign_id == campaign_id))
            assert assignment is not None
            task_job = db.scalar(select(OutboxJob).where(OutboxJob.idempotency_key == f"{assignment.id}:task"))
            assert task_job.payload["title"] == "Read Test training: Test learner"
            assert "{due_date}" not in task_job.payload["description"]
            assert "https://rtmgroupdocs.fvds.ru/education-next/app" in task_job.payload["description"]
            assert db.scalar(select(func.count()).select_from(OutboxJob).where(OutboxJob.idempotency_key.like(f"{assignment.id}:%"))) == 2
            assert db.scalar(select(func.count()).select_from(AssignmentAction).where(AssignmentAction.assignment_id == assignment.id)) == 2
        second_launch = client.post(f"/admin/campaigns/{department_campaign_id}/launch", headers=headers["teacher"], json={"confirmed": True})
        assert second_launch.status_code == 200, second_launch.text
        second_assignment = client.get(f"/admin/campaigns/{department_campaign_id}/assignments", headers=headers["teacher"]).json()[0]
        exempt = client.post(f"/admin/assignments/{second_assignment['id']}/exempt", headers=headers["teacher"], json={
            "reason": "Employee is excused", "confirmed": True})
        assert exempt.status_code == 200 and exempt.json()["status"] == "exempted"
        add = client.post(f"/admin/campaigns/{campaign_id}/recipients", headers=headers["teacher"], json={
            "recipient_bitrix_ids": [bitrix_ids["learner"], bitrix_ids["learner2"]],
            "reason": "New employee joined the course", "confirmed": True})
        assert add.status_code == 200, add.text
        assert add.json()["added_ids"] == [bitrix_ids["learner2"]]
        assert add.json()["already_assigned_ids"] == [bitrix_ids["learner"]]
        repeat = client.post(f"/admin/campaigns/{campaign_id}/recipients", headers=headers["teacher"], json={
            "recipient_bitrix_ids": [bitrix_ids["learner2"]],
            "reason": "Checking duplicate protection", "confirmed": True})
        assert repeat.status_code == 200 and repeat.json()["added_ids"] == []
        with SessionLocal() as db:
            new_assignment = db.scalar(select(Assignment).where(Assignment.campaign_id == campaign_id,
                Assignment.employee_id == ids["learner2"]))
            assert new_assignment.recipient_source["type"] == "manual"
            assert db.scalar(select(func.count()).select_from(OutboxJob).where(
                OutboxJob.idempotency_key.like(f"{new_assignment.id}:%"))) == 2
    finally:
        with SessionLocal() as db:
            if campaign_id:
                assignments = db.scalars(select(Assignment).where(Assignment.campaign_id == campaign_id)).all()
                for assignment in assignments:
                    db.execute(delete(AssignmentAction).where(AssignmentAction.assignment_id == assignment.id))
                    db.execute(delete(OutboxJob).where(OutboxJob.idempotency_key.like(f"{assignment.id}:%")))
                    db.execute(delete(ItemCompletion).where(ItemCompletion.assignment_id == assignment.id))
                db.execute(delete(Assignment).where(Assignment.campaign_id == campaign_id))
                db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id))
            if department_campaign_id:
                second_assignments = db.scalars(select(Assignment).where(Assignment.campaign_id == department_campaign_id)).all()
                for assignment in second_assignments:
                    db.execute(delete(AssignmentAction).where(AssignmentAction.assignment_id == assignment.id))
                    db.execute(delete(OutboxJob).where(OutboxJob.idempotency_key.like(f"{assignment.id}:%")))
                db.execute(delete(Assignment).where(Assignment.campaign_id == department_campaign_id))
                db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id == department_campaign_id))
            if course_id:
                db.execute(delete(CourseItem).where(CourseItem.course_id == course_id))
                db.execute(delete(Article).where(Article.owner_course_id == course_id))
                db.execute(delete(CourseSection).where(CourseSection.course_id == course_id))
                db.execute(delete(Course).where(Course.id == course_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids.values())))
            db.execute(delete(Employee).where(Employee.id.in_(ids.values())))
            db.execute(delete(Department).where(Department.bitrix_id == department_id))
            db.commit()
