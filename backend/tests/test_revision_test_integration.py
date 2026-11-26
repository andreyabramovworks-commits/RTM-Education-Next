import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import (AnswerSubmission, Article, ArticleRevision, Assignment, AssignmentCampaign, AttemptAllowance,
    AttemptQuestion, BrowserSession, Employee, RevisionAcknowledgement, TestAttempt, TestCompletionReward,
    TestDefinition, TestOption, TestQuestion)


def test_revision_full_test_and_independent_copy():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    editor_token = f"revision-editor-{marker}"
    learner_token = f"revision-learner-{marker}"
    with SessionLocal() as db:
        editor = Employee(bitrix_id=1_600_000_000 + marker * 2,
            first_name="Revision", last_name="Editor", local_role="editor")
        learner = Employee(bitrix_id=1_600_000_001 + marker * 2,
            first_name="Revision", last_name="Learner", local_role="employee")
        db.add_all([editor, learner])
        db.flush()
        ids = [editor.id, learner.id]
        learner_bitrix_id = learner.bitrix_id
        body = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Read this"}]}]}
        article = Article(title="Policy", summary="", body=body, created_by=editor.id)
        db.add(article)
        db.flush()
        article_id = article.id
        for token, person in ((editor_token, editor), (learner_token, learner)):
            db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                employee_id=person.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    client = TestClient(app)
    editor_headers = {"Cookie": f"rtm_next_session={editor_token}"}
    learner_headers = {"Cookie": f"rtm_next_session={learner_token}"}
    try:
        published = client.post(f"/admin/knowledge/articles/{article_id}/revisions", headers=editor_headers,
            json={"revision_date": "2026-11-25", "description": "Full test edition",
                  "row_version": 1, "completion_mode": "full_test"})
        assert published.status_code == 201, published.text
        revision_id = published.json()["id"]
        test_id = published.json()["test_id"]
        assert test_id
        edited = client.put(f"/admin/tests/{test_id}", headers=editor_headers, json={
            "title": "Policy test", "summary": "", "row_version": 1, "min_correct": 1,
            "questions": [{"kind": "single", "prompt": "Understood?", "required": True,
                "options": [{"text": "Yes", "correct": True}, {"text": "No", "correct": False}]}]})
        assert edited.status_code == 200, edited.text
        correct_id = next(option["id"] for option in edited.json()["questions"][0]["options"] if option["correct"])
        campaign = client.post("/admin/campaigns", headers=editor_headers, json={
            "target_type": "article_revision", "target_id": revision_id, "title": "Policy update",
            "recipient_bitrix_ids": [learner_bitrix_id], "due_mode": "relative", "due_days": 5})
        assert campaign.status_code == 201, campaign.text
        campaign_id = campaign.json()["id"]
        assert client.post(f"/admin/campaigns/{campaign_id}/launch", headers=editor_headers,
            json={"confirmed": True}).status_code == 200
        assignment_id = client.get("/my/assignments", headers=learner_headers).json()[0]["id"]
        detail = client.get(f"/my/assignments/{assignment_id}", headers=learner_headers)
        assert detail.status_code == 200 and detail.json()["revision"]["test_id"] == test_id
        assert client.post(f"/my/assignments/{assignment_id}/revision/attempts",
            headers=learner_headers).status_code == 409
        assert client.post(f"/my/assignments/{assignment_id}/start", headers=learner_headers).status_code == 200
        grant = client.post(f"/admin/assignments/{assignment_id}/revision/attempt-allowances",
            headers=editor_headers, json={"delta": 1, "reason": "Extra attempt for revision test", "confirmed": True})
        assert grant.status_code == 201, grant.text
        acknowledged = client.post(f"/my/assignments/{assignment_id}/revision/acknowledge", headers=learner_headers)
        assert acknowledged.status_code == 200 and acknowledged.json()["assignment_status"] == "in_progress"
        attempt = client.post(f"/my/assignments/{assignment_id}/revision/attempts", headers=learner_headers)
        assert attempt.status_code == 201, attempt.text
        question_id = attempt.json()["questions"][0]["id"]
        submitted = client.post(f"/my/attempts/{attempt.json()['id']}/submit", headers=learner_headers,
            json={"answers": {question_id: {"option_ids": [correct_id]}}})
        assert submitted.status_code == 200 and submitted.json()["status"] == "passed"
        assert client.get(f"/my/assignments/{assignment_id}", headers=learner_headers).json()["status"] == "completed"
        copied = client.post(f"/admin/knowledge/articles/{article_id}/revisions", headers=editor_headers,
            json={"revision_date": "2026-11-26", "description": "Copied test",
                  "row_version": 1, "completion_mode": "full_test", "copy_test_id": test_id})
        assert copied.status_code == 201, copied.text
        duplicate_id = copied.json()["test_id"]
        assert duplicate_id != test_id
        duplicate = client.get(f"/admin/tests/{duplicate_id}", headers=editor_headers)
        assert duplicate.status_code == 200
        assert duplicate.json()["questions"][0]["id"] != edited.json()["questions"][0]["id"]
        assert duplicate.json()["questions"][0]["options"][0]["id"] != edited.json()["questions"][0]["options"][0]["id"]
    finally:
        with SessionLocal() as db:
            revision_ids = list(db.scalars(select(ArticleRevision.id).where(ArticleRevision.article_id == article_id)))
            test_ids = list(db.scalars(select(TestDefinition.id).where(TestDefinition.article_revision_id.in_(revision_ids))))
            question_ids = list(db.scalars(select(TestQuestion.id).where(TestQuestion.test_id.in_(test_ids))))
            campaign_ids = list(db.scalars(select(AssignmentCampaign.id).where(
                AssignmentCampaign.target_type == "article_revision", AssignmentCampaign.target_id.in_(revision_ids))))
            assignment_ids = list(db.scalars(select(Assignment.id).where(Assignment.campaign_id.in_(campaign_ids))))
            attempt_ids = list(db.scalars(select(TestAttempt.id).where(TestAttempt.assignment_id.in_(assignment_ids))))
            attempt_question_ids = list(db.scalars(select(AttemptQuestion.id).where(AttemptQuestion.attempt_id.in_(attempt_ids))))
            db.execute(delete(AnswerSubmission).where(AnswerSubmission.attempt_question_id.in_(attempt_question_ids)))
            db.execute(delete(AttemptQuestion).where(AttemptQuestion.id.in_(attempt_question_ids)))
            db.execute(delete(TestCompletionReward).where(TestCompletionReward.assignment_id.in_(assignment_ids)))
            db.execute(delete(TestAttempt).where(TestAttempt.id.in_(attempt_ids)))
            db.execute(delete(AttemptAllowance).where(AttemptAllowance.assignment_id.in_(assignment_ids)))
            db.execute(delete(RevisionAcknowledgement).where(RevisionAcknowledgement.assignment_id.in_(assignment_ids)))
            db.execute(delete(Assignment).where(Assignment.id.in_(assignment_ids)))
            db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id.in_(campaign_ids)))
            db.execute(delete(TestOption).where(TestOption.question_id.in_(question_ids)))
            db.execute(delete(TestQuestion).where(TestQuestion.id.in_(question_ids)))
            db.execute(delete(TestDefinition).where(TestDefinition.id.in_(test_ids)))
            db.execute(delete(ArticleRevision).where(ArticleRevision.id.in_(revision_ids)))
            db.execute(delete(Article).where(Article.id == article_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids)))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.commit()
