import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.db import get_db
from app.learning import mark_item_complete, own_assignment
from app.models import (AnswerReview, AnswerSubmission, AssignmentCampaign, AttemptAllowance, AttemptQuestion, CourseItem,
                        Employee, ReviewTask, RevisionAcknowledgement, TestAttempt, TestDefinition, TestOption, TestQuestion)
from app.test_rewards import award_passed_test

router = APIRouter(tags=["tests-learning"])


class SubmitAttempt(BaseModel):
    answers: dict[uuid.UUID, dict]


class CorrectAnswers(BaseModel):
    answers: dict[uuid.UUID, str]


def correction_state(db: Session, questions: list[AttemptQuestion]) -> tuple[dict, dict]:
    submissions = db.scalars(select(AnswerSubmission).where(AnswerSubmission.attempt_question_id.in_(
        [question.id for question in questions])).order_by(AnswerSubmission.version)).all() if questions else []
    latest = {}
    for row in submissions:
        latest[row.attempt_question_id] = row
    reviews = db.scalars(select(AnswerReview).where(AnswerReview.submission_id.in_(
        [row.id for row in latest.values()])).order_by(AnswerReview.created_at)).all() if latest else []
    latest_reviews = {}
    for review in reviews:
        latest_reviews[review.submission_id] = review
    return latest, latest_reviews


def attempt_data(db: Session, attempt: TestAttempt) -> dict:
    questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt.id)
        .order_by(AttemptQuestion.position)).all()
    latest, latest_reviews = correction_state(db, questions)
    return {"id": str(attempt.id), "assignment_id": str(attempt.assignment_id),
            "course_item_id": str(attempt.course_item_id) if attempt.course_item_id else None,
            "attempt_no": attempt.attempt_no, "status": attempt.status,
            "started_at": attempt.started_at.isoformat(),
            "deadline_at": attempt.deadline_at.isoformat() if attempt.deadline_at else None,
            "correction_deadline_at": attempt.correction_deadline_at.isoformat() if attempt.correction_deadline_at else None,
            "reward_points": attempt.reward_points_snapshot,
            "correct_count": attempt.correct_count if attempt.show_results_snapshot else None,
            "auto_count": attempt.auto_count if attempt.show_results_snapshot else None,
            "questions": [{"id": str(question.id), "kind": question.kind, "prompt": question.prompt,
                "image_asset_id": str(question.image_asset_id) if question.image_asset_id else None,
                "required": question.required, "options": question.options_snapshot,
                "answer": latest[question.id].value if question.id in latest else None,
                "correction_required": bool(attempt.status == "returned" and
                    question.id in latest and latest[question.id].id in latest_reviews and
                    latest_reviews[latest[question.id].id].decision == "rejected"),
                "review_comment": latest_reviews[latest[question.id].id].comment
                    if question.id in latest and latest[question.id].id in latest_reviews else None}
                for question in questions]}


@router.post("/my/assignments/{assignment_id}/items/{item_id}/attempts", status_code=201)
def begin_attempt(assignment_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db),
                  employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    if assignment.status not in ("in_progress", "returned"):
        raise HTTPException(409, "Start assignment first")
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "course":
        raise HTTPException(404)
    item = db.scalar(select(CourseItem).where(CourseItem.id == item_id,
        CourseItem.course_id == campaign.target_id, CourseItem.kind == "test"))
    if item is None:
        raise HTTPException(404)
    test = db.get(TestDefinition, item.test_id)
    if test is None:
        raise HTTPException(404)
    return start_test_attempt(db, assignment, test, item_id)


@router.post("/my/assignments/{assignment_id}/revision/attempts", status_code=201)
def begin_revision_attempt(assignment_id: uuid.UUID, db: Session = Depends(get_db),
                           employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    if assignment.status not in ("in_progress", "returned"):
        raise HTTPException(409, "Start assignment first")
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "article_revision":
        raise HTTPException(404)
    if not db.scalar(select(RevisionAcknowledgement.id).where(
            RevisionAcknowledgement.assignment_id == assignment_id)):
        raise HTTPException(409, "Read and acknowledge the revision first")
    test = db.scalar(select(TestDefinition).where(TestDefinition.article_revision_id == campaign.target_id))
    if test is None:
        raise HTTPException(404)
    return start_test_attempt(db, assignment, test, None)


@router.post("/my/assignments/{assignment_id}/test/attempts", status_code=201)
def begin_standalone_attempt(assignment_id: uuid.UUID, db: Session = Depends(get_db),
                             employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    if assignment.status not in ("in_progress", "returned"):
        raise HTTPException(409, "Start assignment first")
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "course_test":
        raise HTTPException(404)
    test = db.get(TestDefinition, campaign.target_id)
    if test is None or test.owner_course_id is None:
        raise HTTPException(404)
    return start_test_attempt(db, assignment, test, None)


def start_test_attempt(db: Session, assignment, test: TestDefinition,
                       item_id: uuid.UUID | None) -> dict:
    assignment_id = assignment.id
    attempts = db.scalars(select(TestAttempt).where(TestAttempt.assignment_id == assignment_id,
        TestAttempt.course_item_id == item_id).order_by(TestAttempt.attempt_no)).all()
    active = next((row for row in attempts if row.status == "in_progress"), None)
    if active:
        return attempt_data(db, active)
    if any(row.status == "pending_review" for row in attempts):
        raise HTTPException(409, "Previous attempt awaits review")
    correction = next((row for row in reversed(attempts) if row.status == "returned" and
        row.correction_deadline_at is not None), None)
    if correction and datetime.now(timezone.utc) <= correction.correction_deadline_at:
        return attempt_data(db, correction)
    extra = db.scalar(select(func.coalesce(func.sum(AttemptAllowance.delta), 0)).where(
        AttemptAllowance.assignment_id == assignment_id, AttemptAllowance.course_item_id == item_id)) or 0
    if len(attempts) >= test.max_attempts + extra:
        raise HTTPException(409, "No attempts left")
    questions = db.scalars(select(TestQuestion).where(TestQuestion.test_id == test.id)
        .order_by(TestQuestion.position)).all()
    if not questions:
        raise HTTPException(409, "Test has no questions")
    now = datetime.now(timezone.utc)
    attempt = TestAttempt(assignment_id=assignment_id, course_item_id=item_id, test_id=test.id,
        attempt_no=len(attempts) + 1, status="in_progress", started_at=now,
        deadline_at=now + timedelta(minutes=test.time_limit_minutes) if test.time_limit_minutes else None,
        min_correct_snapshot=test.min_correct, show_results_snapshot=test.show_results,
        reward_points_snapshot=test.reward_points, correction_days_snapshot=test.correction_days)
    db.add(attempt)
    if assignment.status == "returned":
        assignment.status = "in_progress"
    db.flush()
    rng = random.SystemRandom()
    if test.shuffle_questions:
        rng.shuffle(questions)
    for position, question in enumerate(questions):
        options = db.scalars(select(TestOption).where(TestOption.question_id == question.id)
            .order_by(TestOption.position)).all()
        if test.shuffle_options:
            rng.shuffle(options)
        db.add(AttemptQuestion(attempt_id=attempt.id, source_question_id=question.id,
            position=position, kind=question.kind, prompt=question.prompt, required=question.required,
            image_asset_id=question.image_asset_id,
            options_snapshot=[{"id": str(option.id), "text": option.text,
                               "image_asset_id": str(option.image_asset_id) if option.image_asset_id else None}
                              for option in options],
            correct_option_ids=[str(option.id) for option in options if option.correct]))
    db.commit()
    return attempt_data(db, attempt)


@router.get("/my/attempts/{attempt_id}")
def get_attempt(attempt_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    attempt = db.get(TestAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(404)
    own_assignment(db, attempt.assignment_id, employee)
    return attempt_data(db, attempt)


@router.post("/my/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: uuid.UUID, payload: SubmitAttempt, db: Session = Depends(get_db),
                   employee: Employee = Depends(current_employee)):
    attempt = db.scalar(select(TestAttempt).where(TestAttempt.id == attempt_id).with_for_update())
    if attempt is None:
        raise HTTPException(404)
    assignment = own_assignment(db, attempt.assignment_id, employee, lock=True)
    if attempt.status != "in_progress":
        raise HTTPException(409, "Attempt already submitted")
    now = datetime.now(timezone.utc)
    if attempt.deadline_at and now > attempt.deadline_at:
        attempt.status = "expired"
        db.commit()
        raise HTTPException(409, "Attempt time expired")
    questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt.id)
        .order_by(AttemptQuestion.position)).all()
    question_ids = {question.id for question in questions}
    if not set(payload.answers) <= question_ids:
        raise HTTPException(422, "Unknown question")
    correct_count = 0
    auto_count = 0
    pending_free = False
    submissions: list[AnswerSubmission] = []
    for question in questions:
        answer = payload.answers.get(question.id, {})
        if question.kind == "free_text":
            text = answer.get("text", "")
            if not isinstance(text, str) or len(text) > 20000:
                raise HTTPException(422, "Invalid free answer")
            text = text.strip()
            if question.required and not text:
                raise HTTPException(422, "Required free answer is empty")
            pending_free = pending_free or bool(text)
            submissions.append(AnswerSubmission(attempt_question_id=question.id,
                version=1, value={"text": text}, is_correct=None, submitted_at=now))
            continue
        auto_count += 1
        selected = answer.get("option_ids", [])
        if not isinstance(selected, list) or not all(isinstance(value, str) for value in selected):
            raise HTTPException(422, "Invalid selected options")
        if question.kind == "single" and len(selected) > 1:
            raise HTTPException(422, "Single-choice accepts one option")
        if len(selected) != len(set(selected)):
            raise HTTPException(422, "Duplicate option")
        known = {option["id"] for option in question.options_snapshot}
        if not set(selected) <= known:
            raise HTTPException(422, "Unknown option")
        correct = set(selected) == set(question.correct_option_ids)
        correct_count += int(correct)
        submissions.append(AnswerSubmission(attempt_question_id=question.id,
            version=1, value={"option_ids": selected}, is_correct=correct, submitted_at=now))
    db.add_all(submissions)
    attempt.correct_count = correct_count
    attempt.auto_count = auto_count
    attempt.submitted_at = now
    if correct_count < attempt.min_correct_snapshot:
        attempt.status = "failed"
    elif pending_free:
        attempt.status = "pending_review"
        assignment.status = "pending_review"
        db.add(ReviewTask(attempt_id=attempt.id, status="pending", draft={}))
    else:
        attempt.status = "passed"
        award_passed_test(db, attempt, now)
        item = db.get(CourseItem, attempt.course_item_id) if attempt.course_item_id else None
        if item is not None:
            mark_item_complete(db, assignment, item, "test", now)
        else:
            assignment.status = "completed"
            assignment.completed_at = now
    db.commit()
    return {"id": str(attempt.id), "status": attempt.status,
            "correct_count": correct_count if attempt.show_results_snapshot else None,
            "auto_count": auto_count if attempt.show_results_snapshot else None}


@router.post("/my/attempts/{attempt_id}/correct")
def correct_answers(attempt_id: uuid.UUID, payload: CorrectAnswers, db: Session = Depends(get_db),
                    employee: Employee = Depends(current_employee)):
    attempt = db.scalar(select(TestAttempt).where(TestAttempt.id == attempt_id).with_for_update())
    if attempt is None:
        raise HTTPException(404)
    assignment = own_assignment(db, attempt.assignment_id, employee, lock=True)
    now = datetime.now(timezone.utc)
    if attempt.status != "returned" or attempt.correction_deadline_at is None:
        raise HTTPException(409, "No correction requested")
    if now > attempt.correction_deadline_at:
        raise HTTPException(409, "Correction window expired")
    questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt.id,
        AttemptQuestion.kind == "free_text")).all()
    latest, latest_reviews = correction_state(db, questions)
    rejected = {question.id for question in questions if question.id in latest and
        latest[question.id].id in latest_reviews and
        latest_reviews[latest[question.id].id].decision == "rejected"}
    if not rejected or set(payload.answers) != rejected:
        raise HTTPException(422, "Provide exactly the returned answers")
    for question_id, value in payload.answers.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 20000:
            raise HTTPException(422, "Invalid corrected answer")
        db.add(AnswerSubmission(attempt_question_id=question_id,
            version=latest[question_id].version + 1, value={"text": value.strip()},
            is_correct=None, submitted_at=now))
    task = db.scalar(select(ReviewTask).where(ReviewTask.attempt_id == attempt.id).with_for_update())
    if task is None or task.status != "returned":
        raise HTTPException(409, "Review state changed")
    task.status = "pending"
    task.claimed_by = None
    task.draft = {str(question.id): {"decision": "accepted", "comment": ""}
        for question in questions if question.id in latest and question.id not in rejected and
        latest[question.id].id in latest_reviews and
        latest_reviews[latest[question.id].id].decision == "accepted"}
    task.row_version += 1
    task.updated_at = now
    attempt.status = "pending_review"
    attempt.correction_deadline_at = None
    assignment.status = "pending_review"
    db.commit()
    return {"id": str(attempt.id), "status": attempt.status}
