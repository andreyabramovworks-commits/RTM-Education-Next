import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.main import app
from app.models import (Assignment, AssignmentAction, AssignmentCampaign, BrowserSession, Course,
    CourseItem, CourseSection, Department, Employee, ItemCompletion, OutboxJob)


def test_review_center_separates_campaigns_and_deduplicates_employees():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    bitrix_base = 1_390_000_000 + marker * 3
    department_id = bitrix_base + 100
    child_id = department_id + 1
    token = f"review-center-{marker}"
    now = datetime.now(timezone.utc)
    target_id = uuid.uuid4()
    with SessionLocal() as db:
        teacher = Employee(bitrix_id=bitrix_base, first_name="Review", last_name="Teacher", local_role="teacher")
        alice = Employee(bitrix_id=bitrix_base + 1, first_name="Alice", last_name="Reader",
            department_ids=[child_id])
        bob = Employee(bitrix_id=bitrix_base + 2, first_name="Bob", last_name="Reader",
            department_ids=[department_id])
        db.add_all([teacher, alice, bob,
            Department(bitrix_id=department_id, parent_id=None, title="Parent", updated_at=now),
            Department(bitrix_id=child_id, parent_id=department_id, title="Child", updated_at=now)])
        db.flush()
        db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
            employee_id=teacher.id, expires_at=now + timedelta(hours=1)))
        first = AssignmentCampaign(target_type="article_revision", target_id=target_id, title=f"Регламент {marker}",
            status="active", due_mode="absolute", due_at=now - timedelta(days=1),
            reviewer_ids=[teacher.bitrix_id], created_by=teacher.id,
            launched_at=now - timedelta(days=3))
        second = AssignmentCampaign(target_type="article_revision", target_id=target_id, title=f"Повторное ознакомление {marker}",
            status="active", due_mode="absolute", due_at=now + timedelta(days=3), created_by=teacher.id,
            launched_at=now - timedelta(days=1))
        course = Course(title=f"Курс {marker}", created_by=teacher.id)
        db.add(course); db.flush()
        section = CourseSection(course_id=course.id, title="Раздел", position=0)
        db.add(section); db.flush()
        first_item = CourseItem(course_id=course.id, section_id=section.id, kind="test",
            test_id=uuid.uuid4(), position=0, required=True)
        second_item = CourseItem(course_id=course.id, section_id=section.id, kind="test",
            test_id=uuid.uuid4(), position=1, required=True)
        db.add_all([first_item, second_item]); db.flush()
        hidden = AssignmentCampaign(target_type="course", target_id=course.id, title="Обучение группы",
            status="active", due_mode="relative", due_days=7, created_by=teacher.id,
            launched_at=now - timedelta(days=1))
        db.add_all([first, second, hidden])
        db.flush()
        course_assignment = Assignment(campaign_id=hidden.id, employee_id=alice.id, status="in_progress",
            assigned_at=now - timedelta(days=1), due_at=now + timedelta(days=7))
        db.add_all([
            Assignment(campaign_id=first.id, employee_id=alice.id, status="completed",
                assigned_at=now - timedelta(days=3), due_at=now - timedelta(days=1), completed_at=now),
            Assignment(campaign_id=first.id, employee_id=bob.id, status="not_started",
                assigned_at=now - timedelta(days=3), due_at=now - timedelta(days=1)),
            Assignment(campaign_id=second.id, employee_id=alice.id, status="in_progress",
                assigned_at=now - timedelta(days=1), due_at=now + timedelta(days=3)),
            course_assignment,
        ])
        db.flush()
        db.add(ItemCompletion(assignment_id=course_assignment.id, course_item_id=first_item.id,
            completed_at=now, method="test"))
        db.commit()
        campaign_ids = [first.id, second.id, hidden.id]
        person_ids = [teacher.id, alice.id, bob.id]
    client = TestClient(app)
    headers = {"Cookie": f"rtm_next_session={token}"}
    try:
        targets = client.get(f"/admin/review-center/overview?context=materials&group=targets&search={marker}", headers=headers)
        assert targets.status_code == 200, targets.text
        data = targets.json()
        assert data["total"] == 1
        assert data["rows"][0]["campaign_count"] == 2
        assert {row["campaign_id"] for row in data["rows"][0]["campaigns"]} == {str(campaign_ids[0]), str(campaign_ids[1])}
        assert data["summary"]["employees"] == 2
        assert data["summary"]["assignments"] == 3
        assert data["summary"]["completed"] == 1
        assert data["summary"]["overdue"] == 1
        employees = client.get(f"/admin/review-center/overview?context=materials&group=employees&search={marker}",
            headers=headers).json()
        assert employees["total"] == 2
        alice_row = next(row for row in employees["rows"] if row["first_name"] == "Alice")
        assert alice_row["assignments"] == 2 and alice_row["completed"] == 1
        child = client.get(f"/admin/review-center/overview?department_id={department_id}&search={marker}", headers=headers).json()
        assert child["summary"]["employees"] == 2
        overdue = client.get(f"/admin/review-center/overview?status=overdue&search={marker}", headers=headers).json()
        assert overdue["summary"]["assignments"] == 1
        by_type = client.get(f"/admin/review-center/overview?target_type=article_revision&search={marker}",
            headers=headers).json()
        assert by_type["summary"]["assignments"] == 3
        reviewers = client.get("/admin/review-center/reviewers?context=materials", headers=headers).json()
        assert any(row["bitrix_id"] == bitrix_base for row in reviewers)
        by_reviewer = client.get(f"/admin/review-center/overview?reviewer_bitrix_id={bitrix_base}&search={marker}",
            headers=headers).json()
        assert by_reviewer["summary"]["assignments"] == 2
        by_button = client.get(f"/admin/review-center/overview?confirmation_method=button&search={marker}",
            headers=headers).json()
        assert by_button["summary"]["assignments"] == 1
        by_test = client.get(f"/admin/review-center/overview?confirmation_method=test&search={marker}",
            headers=headers).json()
        assert by_test["summary"]["assignments"] == 0
        invalid_type = client.get("/admin/review-center/overview?context=courses&target_type=article_revision",
            headers=headers)
        assert invalid_type.status_code == 422
        future = (now + timedelta(days=1)).isoformat()
        deadline = client.get("/admin/review-center/overview", headers=headers,
            params={"search": str(marker), "due_from": future}).json()
        assert deadline["summary"]["assignments"] == 1
        page = client.get(f"/admin/review-center/overview?group=employees&limit=1&offset=1&search={marker}",
            headers=headers).json()
        assert page["total"] == 2 and len(page["rows"]) == 1
        details = client.get(f"/admin/review-center/assignments?context=materials&campaign_id={campaign_ids[0]}&search={marker}",
            headers=headers)
        assert details.status_code == 200, details.text
        assert details.json()["total"] == 2
        assert {row["employee_name"] for row in details.json()["rows"]} == {"Alice Reader", "Bob Reader"}
        completed_row = next(row for row in details.json()["rows"] if row["employee_name"] == "Alice Reader")
        assert completed_row["confirmation_method"] == "button"
        assert completed_row["reviewer_names"] == ["Review Teacher"]
        assert next(row for row in details.json()["rows"] if row["employee_name"] == "Bob Reader")["is_overdue"]
        one = client.get(f'/admin/review-center/assignments/{details.json()["rows"][0]["id"]}', headers=headers)
        assert one.status_code == 200, one.text
        assert one.json()["campaign_id"] == str(campaign_ids[0])
        assert one.json()["department_titles"]
        assert one.json()["history"] == [] and one.json()["attempts"] == []
        bob_assignment = next(row for row in details.json()["rows"] if row["employee_name"] == "Bob Reader")
        reminder = {"request_id": str(uuid.uuid4()), "reason": "Проверка напоминания", "confirmed": True}
        remind_url = f'/admin/assignments/{bob_assignment["id"]}/remind'
        first_reminder = client.post(remind_url, headers=headers, json=reminder)
        assert first_reminder.status_code == 201, first_reminder.text
        second_reminder = client.post(remind_url, headers=headers, json=reminder)
        assert second_reminder.status_code == 201
        assert second_reminder.json()["id"] == first_reminder.json()["id"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(OutboxJob).where(
                OutboxJob.id == uuid.UUID(first_reminder.json()["id"]))) == 1
            assert db.scalar(select(func.count()).select_from(AssignmentAction).where(
                AssignmentAction.assignment_id == uuid.UUID(bob_assignment["id"]),
                AssignmentAction.action == "remind")) == 1
        assert client.get("/admin/review-center/assignments?context=materials", headers=headers).status_code == 422
        courses = client.get(f"/admin/review-center/overview?context=courses&search={marker}", headers=headers).json()
        assert courses["summary"]["assignments"] == 1
        assert courses["summary"]["progress_percent"] == 50
        assert courses["rows"][0]["progress_percent"] == 50
        assert courses["rows"][0]["target_title"] == f"Курс {marker}"
        half_progress = client.get(f"/admin/review-center/overview?context=courses&progress_band=26-50&search={marker}",
            headers=headers).json()
        assert half_progress["summary"]["assignments"] == 1
        no_progress = client.get(f"/admin/review-center/overview?context=courses&progress_band=0&search={marker}",
            headers=headers).json()
        assert no_progress["summary"]["assignments"] == 0
        person_courses = client.get(f"/admin/review-center/overview?context=courses&group=employees&search={marker}",
            headers=headers).json()
        assert person_courses["rows"][0]["progress_percent"] == 50
        course_detail = client.get(f"/admin/review-center/assignments/{course_assignment.id}", headers=headers).json()
        assert course_detail["required_done"] == 1 and course_detail["required_total"] == 2
        assert course_detail["course_updated_at"]
    finally:
        with SessionLocal() as db:
            db.execute(delete(OutboxJob).where(OutboxJob.payload["assignment_id"].astext.in_(
                [str(row) for row in db.scalars(select(Assignment.id).where(
                    Assignment.campaign_id.in_(campaign_ids))).all()])))
            db.execute(delete(AssignmentAction).where(AssignmentAction.assignment_id.in_(
                select(Assignment.id).where(Assignment.campaign_id.in_(campaign_ids)))))
            db.execute(delete(ItemCompletion).where(ItemCompletion.assignment_id.in_(
                select(Assignment.id).where(Assignment.campaign_id.in_(campaign_ids)))))
            db.execute(delete(Assignment).where(Assignment.campaign_id.in_(campaign_ids)))
            db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id.in_(campaign_ids)))
            db.execute(delete(CourseItem).where(CourseItem.course_id == course.id))
            db.execute(delete(CourseSection).where(CourseSection.course_id == course.id))
            db.execute(delete(Course).where(Course.id == course.id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(person_ids)))
            db.execute(delete(Employee).where(Employee.id.in_(person_ids)))
            db.execute(delete(Department).where(Department.bitrix_id.in_([department_id, child_id])))
            db.commit()


def test_review_center_paginates_large_employee_and_campaign_lists():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    bitrix_base = 1_420_000_000 + marker * 2
    token = f"review-pages-{marker}"
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        teacher = Employee(bitrix_id=bitrix_base, first_name="Review", last_name="Teacher", local_role="teacher")
        db.add(teacher); db.flush()
        db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
            employee_id=teacher.id, expires_at=now + timedelta(hours=1)))
        campaign = AssignmentCampaign(target_type="article_revision", target_id=uuid.uuid4(),
            title=f"Большой список {marker}", status="active", due_mode="relative", due_days=7,
            reviewer_ids=[], created_by=teacher.id, launched_at=now)
        db.add(campaign); db.flush()
        people = [Employee(bitrix_id=bitrix_base + index + 1, first_name=f"Learner{index:02d}",
            last_name="Paging") for index in range(35)]
        db.add_all(people); db.flush()
        db.add_all(Assignment(campaign_id=campaign.id, employee_id=person.id, status="not_started",
            assigned_at=now, due_at=now + timedelta(days=7)) for person in people)
        db.commit()
        person_ids = [teacher.id, *(person.id for person in people)]
        campaign_id = campaign.id
    client = TestClient(app)
    headers = {"Cookie": f"rtm_next_session={token}"}
    try:
        first = client.get("/admin/review-center/overview", headers=headers,
            params={"group": "employees", "search": str(marker), "limit": 30, "offset": 0})
        second = client.get("/admin/review-center/overview", headers=headers,
            params={"group": "employees", "search": str(marker), "limit": 30, "offset": 30})
        # The search is by title, so all 35 learners match even though their names differ.
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["total"] == second.json()["total"] == 35
        assert len(first.json()["rows"]) == 30 and len(second.json()["rows"]) == 5
        ids = {row["employee_id"] for row in first.json()["rows"] + second.json()["rows"]}
        assert len(ids) == 35
        target = client.get("/admin/review-center/overview", headers=headers,
            params={"group": "targets", "search": str(marker)}).json()
        assert target["total"] == 1 and target["rows"][0]["assignments"] == 35
        participants = client.get("/admin/review-center/assignments", headers=headers,
            params={"context": "materials", "campaign_id": str(campaign_id), "limit": 30, "offset": 30}).json()
        assert participants["total"] == 35 and len(participants["rows"]) == 5
    finally:
        with SessionLocal() as db:
            db.execute(delete(Assignment).where(Assignment.campaign_id == campaign_id))
            db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id == person_ids[0]))
            db.execute(delete(Employee).where(Employee.id.in_(person_ids)))
            db.commit()
