import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import (AnswerSubmission, Assignment, AssignmentCampaign, AttemptQuestion,
    AnswerReview, AttemptAllowance, BrowserSession, Course, CourseItem, CourseSection,
    Employee, ItemCompletion, OutboxJob, ReviewAction, ReviewTask, TestAttempt,
    TestDefinition, TestOption, TestQuestion, TestCompletionReward, MediaAsset)


def test_test_snapshot_grading_and_pending_review():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    tokens = {role: f"test-engine-{marker}-{role}" for role in ("editor", "learner")}
    with SessionLocal() as db:
        editor = Employee(bitrix_id=1_700_000_000 + marker * 2, first_name="Test", last_name="Editor", local_role="editor")
        learner = Employee(bitrix_id=1_700_000_001 + marker * 2, first_name="Test", last_name="Learner")
        db.add_all([editor, learner])
        db.flush()
        ids = [editor.id, learner.id]
        learner_bitrix_id = learner.bitrix_id
        for role, person in (("editor", editor), ("learner", learner)):
            db.add(BrowserSession(token_hash=hashlib.sha256(tokens[role].encode()).hexdigest(), employee_id=person.id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    client = TestClient(app)
    headers = {role: {"Cookie": f"rtm_next_session={token}"} for role, token in tokens.items()}
    course_id = None
    campaign_id = None
    test_id = None
    copied_course_id = None
    image_id = None
    try:
        assert client.get("/my/profile", headers=headers["learner"]).json()["points"] == 0
        course = client.post("/admin/courses", headers=headers["editor"], json={"title": "Test course"})
        course_id = uuid.UUID(course.json()["id"])
        section = client.post(f"/admin/courses/{course_id}/sections", headers=headers["editor"],
            json={"title": "Questions", "row_version": course.json()["row_version"]})
        created = client.post(f"/admin/courses/{course_id}/sections/{section.json()['id']}/tests", headers=headers["editor"],
            json={"title": "Knowledge test", "row_version": section.json()["row_version"]})
        assert created.status_code == 201, created.text
        test_id = uuid.UUID(created.json()["test_id"])
        upload = client.post("/admin/media/upload", headers=headers["editor"], data={"kind": "image"},
            files={"file": ("question.png", b"\x89PNG\r\n\x1a\n" + b"question image", "image/png")})
        assert upload.status_code == 201, upload.text
        image_id = uuid.UUID(upload.json()["id"])
        assert client.get(f"/media/{image_id}", headers=headers["learner"]).status_code == 404
        saved = client.put(f"/admin/tests/{test_id}", headers=headers["editor"], json={
            "title": "Knowledge test", "summary": "", "time_limit_minutes": 15, "max_attempts": 2,
            "min_correct": 1, "reward_points": 25, "correction_days": 7,
            "row_version": 1, "questions": [
                {"kind": "single", "prompt": "First question", "image_asset_id": str(image_id), "options": [
                    {"text": "Correct", "correct": True, "image_asset_id": str(image_id)}, {"text": "Wrong", "correct": False}]},
                {"kind": "free_text", "prompt": "Explain", "options": []},
            ]})
        assert saved.status_code == 200, saved.text
        copied_course = client.post(f"/admin/courses/{course_id}/copy", headers=headers["editor"])
        assert copied_course.status_code == 201, copied_course.text
        copied_course_id = uuid.UUID(copied_course.json()["id"])
        copied_test_id = copied_course.json()["sections"][0]["items"][0]["test_id"]
        assert copied_test_id != str(test_id)
        copied_test = client.get(f"/admin/tests/{copied_test_id}", headers=headers["editor"])
        assert copied_test.status_code == 200 and len(copied_test.json()["questions"]) == 2
        assert copied_test.json()["questions"][0]["id"] != saved.json()["questions"][0]["id"]
        assert copied_test.json()["questions"][0]["image_asset_id"] == str(image_id)
        assert client.post(f"/admin/courses/{course_id}/activate", headers=headers["editor"],
            json={"row_version": created.json()["row_version"], "confirmed": True}).status_code == 200
        campaign = client.post("/admin/campaigns", headers=headers["editor"], json={
            "target_type": "course", "target_id": str(course_id), "title": "Test campaign",
            "recipient_bitrix_ids": [learner_bitrix_id], "due_mode": "relative", "due_days": 7})
        assert campaign.status_code == 201, campaign.text
        campaign_id = uuid.UUID(campaign.json()["id"])
        assert client.post(f"/admin/campaigns/{campaign_id}/launch", headers=headers["editor"], json={"confirmed": True}).status_code == 200
        assignment_id = client.get("/my/assignments", headers=headers["learner"]).json()[0]["id"]
        item_id = created.json()["id"]
        assert client.post(f"/my/assignments/{assignment_id}/start", headers=headers["learner"]).status_code == 200
        first = client.post(f"/my/assignments/{assignment_id}/items/{item_id}/attempts", headers=headers["learner"])
        assert first.status_code == 201, first.text
        question = first.json()["questions"][0]
        assert question["image_asset_id"] == str(image_id)
        assert question["options"][0]["image_asset_id"] == str(image_id)
        assert client.get(f"/media/{image_id}", headers=headers["learner"]).status_code == 200
        free = first.json()["questions"][1]
        assert all("correct" not in option for row in first.json()["questions"] for option in row["options"])
        assert all("correct_option_ids" not in row for row in first.json()["questions"])
        wrong_option = next(option["id"] for option in question["options"] if option["text"] == "Wrong")
        failed = client.post(f"/my/attempts/{first.json()['id']}/submit", headers=headers["learner"], json={"answers": {
            question["id"]: {"option_ids": [wrong_option]}, free["id"]: {"text": "My explanation"}}})
        assert failed.status_code == 200, failed.text
        assert failed.json()["status"] == "failed"
        assert client.get(f"/my/attempts/{first.json()['id']}", headers=headers["editor"]).status_code == 404
        changed = client.put(f"/admin/tests/{test_id}", headers=headers["editor"], json={
            "title": "Knowledge test", "summary": "", "time_limit_minutes": 15, "max_attempts": 2,
            "min_correct": 1, "reward_points": 25, "correction_days": 7,
            "row_version": saved.json()["row_version"], "questions": [
                {"kind": "single", "prompt": "Changed question", "options": [
                    {"text": "New correct", "correct": True}, {"text": "New wrong", "correct": False}]},
                {"kind": "free_text", "prompt": "Explain", "options": []},
            ]})
        assert changed.status_code == 200, changed.text
        assert client.get(f"/my/attempts/{first.json()['id']}", headers=headers["learner"]).json()["questions"][0]["prompt"] == "First question"
        assert client.get(f"/my/attempts/{first.json()['id']}", headers=headers["learner"]).json()["questions"][0]["image_asset_id"] == str(image_id)
        second = client.post(f"/my/assignments/{assignment_id}/items/{item_id}/attempts", headers=headers["learner"])
        assert second.status_code == 201, second.text
        assert second.json()["attempt_no"] == 2
        second_question = second.json()["questions"][0]
        correct_option = next(option["id"] for option in second_question["options"] if option["text"] == "New correct")
        pending = client.post(f"/my/attempts/{second.json()['id']}/submit", headers=headers["learner"], json={"answers": {
            second_question["id"]: {"option_ids": [correct_option]},
            second.json()["questions"][1]["id"]: {"text": "New explanation"}}})
        assert pending.status_code == 200, pending.text
        assert pending.json()["status"] == "pending_review"
        assert client.post(f"/my/assignments/{assignment_id}/items/{item_id}/attempts", headers=headers["learner"]).status_code == 409
        queue = client.get("/admin/reviews?context=courses", headers=headers["editor"])
        assert queue.status_code == 200, queue.text
        review_id = next(row["id"] for row in queue.json() if row["campaign_title"] == "Test campaign")
        claimed = client.post(f"/admin/reviews/{review_id}/claim", headers=headers["editor"])
        assert claimed.status_code == 200, claimed.text
        assert client.post(f"/admin/reviews/{review_id}/claim", headers=headers["learner"]).status_code == 403
        free_id = second.json()["questions"][1]["id"]
        draft = client.put(f"/admin/reviews/{review_id}/draft", headers=headers["editor"], json={
            "row_version": claimed.json()["row_version"], "decisions": {
                free_id: {"decision": "rejected", "comment": "Уточните порядок действий"}}})
        assert draft.status_code == 200, draft.text
        assert client.put(f"/admin/reviews/{review_id}/draft", headers=headers["editor"], json={
            "row_version": claimed.json()["row_version"], "decisions": {}}).status_code == 409
        returned = client.post(f"/admin/reviews/{review_id}/complete", headers=headers["editor"], json={
            "row_version": draft.json()["row_version"], "return_mode": "answer_correction", "confirmed": True})
        assert returned.status_code == 200, returned.text
        same = client.post(f"/my/assignments/{assignment_id}/items/{item_id}/attempts", headers=headers["learner"])
        assert same.status_code == 201 and same.json()["id"] == second.json()["id"]
        assert same.json()["questions"][1]["correction_required"]
        assert same.json()["questions"][1]["review_comment"] == "Уточните порядок действий"
        assert client.post(f"/my/attempts/{second.json()['id']}/correct", headers=headers["editor"], json={
            "answers": {free_id: "Исправление"}}).status_code == 404
        corrected = client.post(f"/my/attempts/{second.json()['id']}/correct", headers=headers["learner"], json={
            "answers": {free_id: "Исправление первое"}})
        assert corrected.status_code == 200 and corrected.json()["status"] == "pending_review"
        reclaimed = client.post(f"/admin/reviews/{review_id}/claim", headers=headers["editor"]).json()
        assert reclaimed["questions"][1]["submissions"][-1]["version"] == 2
        redraft = client.put(f"/admin/reviews/{review_id}/draft", headers=headers["editor"], json={
            "row_version": reclaimed["row_version"], "decisions": {
                free_id: {"decision": "rejected", "comment": "Ещё уточните"}}}).json()
        assert client.post(f"/admin/reviews/{review_id}/complete", headers=headers["editor"], json={
            "row_version": redraft["row_version"], "return_mode": "answer_correction", "confirmed": True}).status_code == 200
        assert client.post(f"/my/attempts/{second.json()['id']}/correct", headers=headers["learner"], json={
            "answers": {free_id: "Исправление второе"}}).status_code == 200
        reclaimed = client.post(f"/admin/reviews/{review_id}/claim", headers=headers["editor"]).json()
        assert reclaimed["questions"][1]["submissions"][-1]["version"] == 3
        redraft = client.put(f"/admin/reviews/{review_id}/draft", headers=headers["editor"], json={
            "row_version": reclaimed["row_version"], "decisions": {
                free_id: {"decision": "accepted", "comment": ""}}}).json()
        final_review = client.post(f"/admin/reviews/{review_id}/complete", headers=headers["editor"], json={
            "row_version": redraft["row_version"], "confirmed": True})
        assert final_review.status_code == 200 and final_review.json()["status"] == "completed"
        with SessionLocal() as db:
            awards = db.scalars(select(TestCompletionReward).where(
                TestCompletionReward.assignment_id == uuid.UUID(assignment_id))).all()
            assert len(awards) == 1 and awards[0].points == 25
        learner_profile = client.get("/my/profile", headers=headers["learner"])
        assert learner_profile.status_code == 200
        assert learner_profile.json()["points"] == 25
        assert len(learner_profile.json()["rewards"]) == 1
        assert client.get("/my/profile", headers=headers["editor"]).json()["points"] == 0
        assert client.post(f"/my/attempts/{second.json()['id']}/correct", headers=headers["learner"], json={
            "answers": {free_id: "Поздно"}}).status_code == 409
        assert client.get(f"/my/assignments/{assignment_id}", headers=headers["learner"]).json()["status"] == "completed"
    finally:
        with SessionLocal() as db:
            if copied_course_id:
                duplicate_tests = db.scalars(select(TestDefinition).where(TestDefinition.owner_course_id == copied_course_id)).all()
                for duplicate in duplicate_tests:
                    duplicate_question_ids = db.scalars(select(TestQuestion.id).where(TestQuestion.test_id == duplicate.id)).all()
                    db.execute(delete(TestOption).where(TestOption.question_id.in_(duplicate_question_ids)))
                    db.execute(delete(TestQuestion).where(TestQuestion.test_id == duplicate.id))
                db.execute(delete(CourseItem).where(CourseItem.course_id == copied_course_id))
                db.execute(delete(TestDefinition).where(TestDefinition.owner_course_id == copied_course_id))
                db.execute(delete(CourseSection).where(CourseSection.course_id == copied_course_id))
                db.execute(delete(Course).where(Course.id == copied_course_id))
            if campaign_id:
                assignments = db.scalars(select(Assignment).where(Assignment.campaign_id == campaign_id)).all()
                for assignment in assignments:
                    attempts = db.scalars(select(TestAttempt).where(TestAttempt.assignment_id == assignment.id)).all()
                    for attempt in attempts:
                        qids = db.scalars(select(AttemptQuestion.id).where(AttemptQuestion.attempt_id == attempt.id)).all()
                        submission_ids = db.scalars(select(AnswerSubmission.id).where(AnswerSubmission.attempt_question_id.in_(qids))).all()
                        db.execute(delete(AnswerReview).where(AnswerReview.submission_id.in_(submission_ids)))
                        db.execute(delete(AnswerSubmission).where(AnswerSubmission.attempt_question_id.in_(qids)))
                        db.execute(delete(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt.id))
                    review_ids = db.scalars(select(ReviewTask.id).where(ReviewTask.attempt_id.in_([a.id for a in attempts]))).all()
                    db.execute(delete(ReviewAction).where(ReviewAction.review_task_id.in_(review_ids)))
                    db.execute(delete(ReviewTask).where(ReviewTask.id.in_(review_ids)))
                    db.execute(delete(TestCompletionReward).where(TestCompletionReward.assignment_id == assignment.id))
                    db.execute(delete(TestAttempt).where(TestAttempt.assignment_id == assignment.id))
                    db.execute(delete(AttemptAllowance).where(AttemptAllowance.assignment_id == assignment.id))
                    db.execute(delete(ItemCompletion).where(ItemCompletion.assignment_id == assignment.id))
                    db.execute(delete(OutboxJob).where(OutboxJob.idempotency_key.like(f"{assignment.id}:%")))
                db.execute(delete(Assignment).where(Assignment.campaign_id == campaign_id))
                db.execute(delete(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id))
            if test_id:
                qids = db.scalars(select(TestQuestion.id).where(TestQuestion.test_id == test_id)).all()
                db.execute(delete(TestOption).where(TestOption.question_id.in_(qids)))
                db.execute(delete(TestQuestion).where(TestQuestion.test_id == test_id))
            if course_id:
                db.execute(delete(CourseItem).where(CourseItem.course_id == course_id))
            if test_id:
                db.execute(delete(TestDefinition).where(TestDefinition.id == test_id))
            if course_id:
                db.execute(delete(CourseSection).where(CourseSection.course_id == course_id))
                db.execute(delete(Course).where(Course.id == course_id))
            if image_id:
                db.execute(delete(MediaAsset).where(MediaAsset.id == image_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids)))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.commit()
        if image_id:
            (Path("/media") / str(image_id)).unlink(missing_ok=True)
