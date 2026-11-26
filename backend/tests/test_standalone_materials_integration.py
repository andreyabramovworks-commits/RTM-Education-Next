import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import (AnswerSubmission, Article, Assignment, AssignmentCampaign, AttemptQuestion,
    BrowserSession, Course, Employee, TestAttempt, TestCompletionReward, TestDefinition, TestOption, TestQuestion)


def test_independent_article_and_test_assignments():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    teacher_token, learner_token = f"standalone-teacher-{marker}", f"standalone-learner-{marker}"
    with SessionLocal() as db:
        teacher = Employee(bitrix_id=1_300_000_000 + marker * 2,
            first_name="Standalone", last_name="Teacher", local_role="teacher")
        learner = Employee(bitrix_id=1_300_000_001 + marker * 2,
            first_name="Standalone", last_name="Learner", local_role="employee")
        db.add_all([teacher, learner])
        db.flush()
        ids = [teacher.id, learner.id]
        learner_bitrix_id = learner.bitrix_id
        course = Course(title="Original course", status="active", created_by=teacher.id)
        db.add(course); db.flush()
        course_id = course.id
        article = Article(owner_course_id=course_id, title="Standalone article", summary="",
            body={"type": "doc", "content": [{"type": "paragraph"}]}, created_by=teacher.id)
        test = TestDefinition(owner_course_id=course_id, title="Standalone test", min_correct=1,
            created_by=teacher.id)
        db.add_all([article, test]); db.flush()
        article_id, test_id = article.id, test.id
        question = TestQuestion(test_id=test.id, position=0, kind="single", prompt="Correct?", required=True)
        db.add(question); db.flush()
        source_question_id = question.id
        db.add(TestOption(question_id=question.id, position=0, text="Yes", correct=True))
        for token, person in ((teacher_token, teacher), (learner_token, learner)):
            db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                employee_id=person.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    client = TestClient(app)
    teacher_headers = {"Cookie": f"rtm_next_session={teacher_token}"}
    learner_headers = {"Cookie": f"rtm_next_session={learner_token}"}
    try:
        for target_type, target_id in (("course_article", article_id), ("course_test", test_id)):
            draft = client.post("/admin/campaigns", headers=teacher_headers, json={
                "target_type": target_type, "target_id": str(target_id), "title": target_type,
                "recipient_bitrix_ids": [learner_bitrix_id], "due_mode": "relative", "due_days": 3})
            assert draft.status_code == 201, draft.text
            launched = client.post(f"/admin/campaigns/{draft.json()['id']}/launch", headers=teacher_headers,
                json={"confirmed": True})
            assert launched.status_code == 200, launched.text
        assignments = client.get("/my/assignments", headers=learner_headers).json()
        assert {row["target_type"] for row in assignments} == {"course_article", "course_test"}
        by_type = {row["target_type"]: row["id"] for row in assignments}
        article_assignment = by_type["course_article"]
        assert client.get(f"/my/assignments/{article_assignment}", headers=learner_headers).json()["article"]["title"] == "Standalone article"
        assert client.post(f"/my/assignments/{article_assignment}/article/acknowledge",
            headers=learner_headers).status_code == 409
        assert client.post(f"/my/assignments/{article_assignment}/start", headers=learner_headers).status_code == 200
        acknowledged = client.post(f"/my/assignments/{article_assignment}/article/acknowledge", headers=learner_headers)
        assert acknowledged.status_code == 200 and acknowledged.json()["assignment_status"] == "completed"
        test_assignment = by_type["course_test"]
        assert client.post(f"/my/assignments/{test_assignment}/start", headers=learner_headers).status_code == 200
        attempt = client.post(f"/my/assignments/{test_assignment}/test/attempts", headers=learner_headers)
        assert attempt.status_code == 201, attempt.text
        question_id = attempt.json()["questions"][0]["id"]
        option_id = attempt.json()["questions"][0]["options"][0]["id"]
        submitted = client.post(f"/my/attempts/{attempt.json()['id']}/submit", headers=learner_headers,
            json={"answers": {question_id: {"option_ids": [option_id]}}})
        assert submitted.status_code == 200 and submitted.json()["status"] == "passed"
        assert client.get(f"/my/assignments/{test_assignment}", headers=learner_headers).json()["status"] == "completed"
        assert client.get(f"/my/assignments/{article_assignment}", headers=learner_headers).json()["status"] == "completed"
    finally:
        with SessionLocal() as db:
            campaign_ids = list(db.scalars(select(AssignmentCampaign.id).where(
                AssignmentCampaign.target_id.in_([article_id, test_id]))))
            assignment_ids = list(db.scalars(select(Assignment.id).where(Assignment.campaign_id.in_(campaign_ids))))
            attempt_ids = list(db.scalars(select(TestAttempt.id).where(TestAttempt.assignment_id.in_(assignment_ids))))
            attempt_question_ids = list(db.scalars(select(AttemptQuestion.id).where(AttemptQuestion.attempt_id.in_(attempt_ids))))
            db.execute(delete(AnswerSubmission).where(AnswerSubmission.attempt_question_id.in_(attempt_question_ids)))
            db.execute(delete(AttemptQuestion).where(AttemptQuestion.id.in_(attempt_question_ids)))
            db.execute(delete(TestCompletionReward).where(TestCompletionReward.assignment_id.in_(assignment_ids)))
            db.execute(delete(TestAttempt).where(TestAttempt.id.in_(attempt_ids)))
            db.execute(delete(Assignment).where(Assignment.id.in_(assignment_ids)))
            db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id.in_(campaign_ids)))
            db.execute(delete(TestOption).where(TestOption.question_id == source_question_id))
            db.execute(delete(TestQuestion).where(TestQuestion.id == source_question_id))
            db.execute(delete(TestDefinition).where(TestDefinition.id == test_id))
            db.execute(delete(Article).where(Article.id == article_id))
            db.execute(delete(Course).where(Course.id == course_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids)))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.commit()
