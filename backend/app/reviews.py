import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.learning import mark_item_complete
from app.models import (AnswerReview, AnswerSubmission, Assignment, AssignmentCampaign,
    AttemptAllowance, AttemptQuestion, CourseItem, Employee, ReviewAction, ReviewTask,
    TestAttempt, TestDefinition)
from app.permissions import require_role
from app.test_rewards import award_passed_test

router = APIRouter(prefix="/admin", tags=["reviews"])


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    comment: str = Field(default="", max_length=20000)


class SaveDraft(BaseModel):
    row_version: int = Field(ge=1)
    decisions: dict[uuid.UUID, ReviewDecision]


class CompleteReview(BaseModel):
    row_version: int = Field(ge=1)
    return_mode: str | None = Field(default=None, pattern="^(full_retake|answer_correction)$")
    confirmed: bool


class GrantAttempts(BaseModel):
    delta: int = Field(ge=1, le=100)
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool


def review_detail(db: Session, task: ReviewTask) -> dict:
    attempt = db.get(TestAttempt, task.attempt_id)
    assignment = db.get(Assignment, attempt.assignment_id)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    learner = db.get(Employee, assignment.employee_id)
    test = db.get(TestDefinition, attempt.test_id)
    questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt.id)
        .order_by(AttemptQuestion.position)).all()
    submissions = db.scalars(select(AnswerSubmission).where(AnswerSubmission.attempt_question_id.in_(
        [question.id for question in questions])).order_by(AnswerSubmission.version)).all() if questions else []
    reviews = db.scalars(select(AnswerReview).where(AnswerReview.submission_id.in_(
        [submission.id for submission in submissions])).order_by(AnswerReview.created_at)).all() if submissions else []
    return {"id": str(task.id), "attempt_id": str(attempt.id), "assignment_id": str(assignment.id),
            "course_item_id": str(attempt.course_item_id) if attempt.course_item_id else None,
            "target_type": campaign.target_type,
            "context": "courses" if campaign.target_type == "course" else "materials",
            "campaign_title": campaign.title, "learner_name": f"{learner.first_name} {learner.last_name}".strip(),
            "test_title": test.title if test else "Тест", "status": task.status,
            "claimed_by": str(task.claimed_by) if task.claimed_by else None,
            "row_version": task.row_version, "draft": task.draft,
            "correct_count": attempt.correct_count, "auto_count": attempt.auto_count,
            "questions": [{"id": str(question.id), "kind": question.kind, "prompt": question.prompt,
                "image_asset_id": str(question.image_asset_id) if question.image_asset_id else None,
                "required": question.required, "options": question.options_snapshot,
                "correct_option_ids": question.correct_option_ids,
                "submissions": [{"id": str(row.id), "version": row.version, "value": row.value,
                    "is_correct": row.is_correct,
                    "reviews": [{"decision": review.decision, "comment": review.comment,
                                 "created_at": review.created_at.isoformat()}
                                for review in reviews if review.submission_id == row.id]}
                    for row in submissions if row.attempt_question_id == question.id]}
                for question in questions]}


@router.get("/reviews")
def list_reviews(context: str = Query(default="courses", pattern="^(courses|materials)$"),
                 db: Session = Depends(get_db), _actor: Employee = Depends(require_role("teacher"))):
    rows = db.scalars(select(ReviewTask).where(ReviewTask.status.in_(["pending", "claimed"]))
        .order_by(ReviewTask.created_at.desc()).limit(100)).all()
    result = []
    for task in rows:
        attempt = db.get(TestAttempt, task.attempt_id)
        assignment = db.get(Assignment, attempt.assignment_id)
        campaign = db.get(AssignmentCampaign, assignment.campaign_id)
        if (campaign.target_type == "course") != (context == "courses"):
            continue
        learner = db.get(Employee, assignment.employee_id)
        test = db.get(TestDefinition, attempt.test_id)
        result.append({"id": str(task.id), "status": task.status,
            "learner_name": f"{learner.first_name} {learner.last_name}".strip(),
            "campaign_title": campaign.title, "test_title": test.title if test else "Тест",
            "created_at": task.created_at.isoformat()})
    return result


@router.get("/reviews/{task_id}")
def get_review(task_id: uuid.UUID, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("teacher"))):
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(404)
    return review_detail(db, task)


@router.post("/reviews/{task_id}/claim")
def claim_review(task_id: uuid.UUID, db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    task = db.scalar(select(ReviewTask).where(ReviewTask.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(404)
    if task.status == "claimed" and task.claimed_by == actor.id:
        return review_detail(db, task)
    if task.status != "pending":
        raise HTTPException(409, "Review already claimed or completed")
    task.status = "claimed"
    task.claimed_by = actor.id
    task.row_version += 1
    task.updated_at = datetime.now(timezone.utc)
    db.add(ReviewAction(review_task_id=task.id, actor_id=actor.id, action="claim",
        details={}, occurred_at=task.updated_at))
    db.commit()
    return review_detail(db, task)


@router.put("/reviews/{task_id}/draft")
def save_review_draft(task_id: uuid.UUID, payload: SaveDraft, db: Session = Depends(get_db),
                      actor: Employee = Depends(require_role("teacher"))):
    task = db.scalar(select(ReviewTask).where(ReviewTask.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(404)
    if task.status != "claimed" or task.claimed_by != actor.id:
        raise HTTPException(403, "Claim this review first")
    if task.row_version != payload.row_version:
        raise HTTPException(409, "Review changed")
    questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id == task.attempt_id,
        AttemptQuestion.kind == "free_text")).all()
    if not set(payload.decisions) <= {question.id for question in questions}:
        raise HTTPException(422, "Unknown free question")
    task.draft = {str(question_id): decision.model_dump() for question_id, decision in payload.decisions.items()}
    task.row_version += 1
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    return review_detail(db, task)


@router.post("/reviews/{task_id}/complete")
def complete_review(task_id: uuid.UUID, payload: CompleteReview, db: Session = Depends(get_db),
                    actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed:
        raise HTTPException(422, "Confirmation required")
    task = db.scalar(select(ReviewTask).where(ReviewTask.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(404)
    if task.status != "claimed" or task.claimed_by != actor.id:
        raise HTTPException(403, "Claim this review first")
    if task.row_version != payload.row_version:
        raise HTTPException(409, "Review changed")
    attempt = db.get(TestAttempt, task.attempt_id)
    if attempt is None or attempt.status != "pending_review":
        raise HTTPException(409, "Attempt is not pending review")
    questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt.id,
        AttemptQuestion.kind == "free_text")).all()
    if not questions:
        raise HTTPException(409, "No free answers")
    submissions = db.scalars(select(AnswerSubmission).where(AnswerSubmission.attempt_question_id.in_(
        [question.id for question in questions]))).all()
    latest = {}
    for row in submissions:
        if row.attempt_question_id not in latest or row.version > latest[row.attempt_question_id].version:
            latest[row.attempt_question_id] = row
    decisions = task.draft
    if any(question.required and str(question.id) not in decisions for question in questions):
        raise HTTPException(422, "All required free answers need decisions")
    rejected = [question for question in questions if decisions.get(str(question.id), {}).get("decision") == "rejected"]
    for question in rejected:
        if not decisions[str(question.id)].get("comment", "").strip():
            raise HTTPException(422, "Rejected answer needs a comment")
    if rejected and payload.return_mode is None:
        raise HTTPException(422, "Select a return mode")
    assignment = db.scalar(select(Assignment).where(Assignment.id == attempt.assignment_id).with_for_update())
    if rejected and payload.return_mode == "full_retake":
        test = db.get(TestDefinition, attempt.test_id)
        count = db.scalar(select(func.count()).select_from(TestAttempt).where(
            TestAttempt.assignment_id == assignment.id, TestAttempt.course_item_id == attempt.course_item_id)) or 0
        extra = db.scalar(select(func.coalesce(func.sum(AttemptAllowance.delta), 0)).where(
            AttemptAllowance.assignment_id == assignment.id,
            AttemptAllowance.course_item_id == attempt.course_item_id)) or 0
        if count >= test.max_attempts + extra:
            raise HTTPException(409, "Grant an additional attempt before full retake")
    now = datetime.now(timezone.utc)
    for question in questions:
        decision = decisions.get(str(question.id))
        if decision and question.id in latest:
            db.add(AnswerReview(submission_id=latest[question.id].id, reviewer_id=actor.id,
                decision=decision["decision"], comment=decision.get("comment", ""), created_at=now))
    if rejected:
        attempt.status = "returned"
        assignment.status = "returned"
        task.status = "returned"
        attempt.correction_deadline_at = (now + timedelta(days=attempt.correction_days_snapshot)
            if payload.return_mode == "answer_correction" else None)
    else:
        attempt.status = "passed"
        attempt.correction_deadline_at = None
        award_passed_test(db, attempt, now)
        assignment.status = "in_progress"
        task.status = "completed"
        item = db.get(CourseItem, attempt.course_item_id) if attempt.course_item_id else None
        if item:
            mark_item_complete(db, assignment, item, "test_review", now)
        else:
            assignment.status = "completed"
            assignment.completed_at = now
    task.row_version += 1
    task.updated_at = now
    db.add(ReviewAction(review_task_id=task.id, actor_id=actor.id,
        action=("return_answer_correction" if payload.return_mode == "answer_correction" else "return_full_retake")
        if rejected else "complete_passed",
        details={"question_ids": [str(question.id) for question in questions]}, occurred_at=now))
    db.commit()
    return review_detail(db, task)


@router.post("/assignments/{assignment_id}/items/{item_id}/attempt-allowances", status_code=201)
def grant_attempts(assignment_id: uuid.UUID, item_id: uuid.UUID, payload: GrantAttempts,
                   db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    reason = payload.reason.strip()
    if not payload.confirmed or len(reason) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    assignment = db.get(Assignment, assignment_id)
    item = db.get(CourseItem, item_id)
    if assignment is None or item is None or item.kind != "test":
        raise HTTPException(404)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "course" or campaign.target_id != item.course_id:
        raise HTTPException(404)
    grant = AttemptAllowance(assignment_id=assignment_id, course_item_id=item_id,
        delta=payload.delta, actor_id=actor.id, reason=reason, granted_at=datetime.now(timezone.utc))
    db.add(grant)
    db.commit()
    return {"id": str(grant.id), "delta": grant.delta}


@router.post("/assignments/{assignment_id}/revision/attempt-allowances", status_code=201)
@router.post("/assignments/{assignment_id}/test/attempt-allowances", status_code=201)
def grant_revision_attempts(assignment_id: uuid.UUID, payload: GrantAttempts,
                            db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    reason = payload.reason.strip()
    if not payload.confirmed or len(reason) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(404)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type not in ("article_revision", "course_test"):
        raise HTTPException(404)
    test = (db.scalar(select(TestDefinition.id).where(TestDefinition.article_revision_id == campaign.target_id))
            if campaign.target_type == "article_revision" else db.get(TestDefinition, campaign.target_id))
    if test is None:
        raise HTTPException(404)
    grant = AttemptAllowance(assignment_id=assignment_id, course_item_id=None,
        delta=payload.delta, actor_id=actor.id, reason=reason, granted_at=datetime.now(timezone.utc))
    db.add(grant)
    db.commit()
    return {"id": str(grant.id), "delta": grant.delta}
