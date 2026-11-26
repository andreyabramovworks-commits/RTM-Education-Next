import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.course_program import lock_course
from app.db import get_db
from app.models import CourseItem, CourseSection, Employee, MediaAsset, TestDefinition, TestOption, TestQuestion
from app.permissions import require_role

router = APIRouter(tags=["tests-authoring"])


class NewTest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    row_version: int = Field(ge=1)


class OptionIn(BaseModel):
    id: uuid.UUID | None = None
    text: str = Field(max_length=2000)
    correct: bool = False
    image_asset_id: uuid.UUID | None = None


class QuestionIn(BaseModel):
    id: uuid.UUID | None = None
    kind: str = Field(pattern="^(single|multiple|free_text)$")
    prompt: str = Field(max_length=20000)
    required: bool = True
    image_asset_id: uuid.UUID | None = None
    options: list[OptionIn] = Field(default_factory=list)


class EditTest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=20000)
    time_limit_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_attempts: int = Field(default=1, ge=1, le=100)
    min_correct: int = Field(default=0, ge=0)
    shuffle_questions: bool = False
    shuffle_options: bool = False
    show_results: bool = True
    reward_points: int = Field(default=0, ge=0, le=1_000_000)
    correction_days: int = Field(default=7, ge=1, le=365)
    questions: list[QuestionIn] = Field(default_factory=list)
    row_version: int = Field(ge=1)


def test_data(db: Session, test: TestDefinition) -> dict:
    questions = db.scalars(select(TestQuestion).where(TestQuestion.test_id == test.id).order_by(TestQuestion.position)).all()
    option_ids = [question.id for question in questions]
    options = db.scalars(select(TestOption).where(TestOption.question_id.in_(option_ids)).order_by(TestOption.position)).all() if option_ids else []
    return {"id": str(test.id), "owner_course_id": str(test.owner_course_id) if test.owner_course_id else None,
            "article_revision_id": str(test.article_revision_id) if test.article_revision_id else None,
            "title": test.title, "summary": test.summary, "time_limit_minutes": test.time_limit_minutes,
            "max_attempts": test.max_attempts, "min_correct": test.min_correct,
            "shuffle_questions": test.shuffle_questions, "shuffle_options": test.shuffle_options,
            "show_results": test.show_results, "reward_points": test.reward_points,
            "correction_days": test.correction_days, "row_version": test.row_version,
            "questions": [{"id": str(question.id), "kind": question.kind, "prompt": question.prompt,
                "required": question.required, "position": question.position,
                "image_asset_id": str(question.image_asset_id) if question.image_asset_id else None,
                "options": [{"id": str(option.id), "text": option.text, "correct": option.correct,
                             "position": option.position,
                             "image_asset_id": str(option.image_asset_id) if option.image_asset_id else None}
                            for option in options if option.question_id == question.id]}
                for question in questions]}


@router.post("/admin/courses/{course_id}/sections/{section_id}/tests", status_code=201)
def create_course_test(course_id: uuid.UUID, section_id: uuid.UUID, payload: NewTest,
                       db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    course = lock_course(db, course_id, payload.row_version)
    if db.scalar(select(CourseSection.id).where(CourseSection.id == section_id, CourseSection.course_id == course_id)) is None:
        raise HTTPException(404)
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    position = db.scalar(select(func.count()).select_from(CourseItem).where(CourseItem.section_id == section_id)) or 0
    test = TestDefinition(owner_course_id=course_id, title=title, created_by=actor.id)
    db.add(test)
    db.flush()
    item = CourseItem(course_id=course_id, section_id=section_id, kind="test", test_id=test.id,
        position=position, required=True)
    db.add(item)
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": str(item.id), "test_id": str(test.id), "title": test.title, "kind": "test",
            "position": item.position, "required": True, "row_version": course.row_version}


@router.get("/admin/tests/{test_id}")
def get_test(test_id: uuid.UUID, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    test = db.get(TestDefinition, test_id)
    if test is None:
        raise HTTPException(404)
    return test_data(db, test)


@router.put("/admin/tests/{test_id}")
def edit_test(test_id: uuid.UUID, payload: EditTest, db: Session = Depends(get_db),
              _actor: Employee = Depends(require_role("editor"))):
    test = db.scalar(select(TestDefinition).where(TestDefinition.id == test_id).with_for_update())
    if test is None:
        raise HTTPException(404)
    if test.row_version != payload.row_version:
        raise HTTPException(409, "Test changed; reload before saving")
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    old_questions = db.scalars(select(TestQuestion).where(TestQuestion.test_id == test_id)).all()
    old_qids = {question.id for question in old_questions}
    old_options = db.scalars(select(TestOption).where(TestOption.question_id.in_(old_qids))).all() if old_qids else []
    old_oids = {option.id for option in old_options}
    submitted_qids = [question.id for question in payload.questions if question.id]
    submitted_oids = [option.id for question in payload.questions for option in question.options if option.id]
    if len(submitted_qids) != len(set(submitted_qids)) or not set(submitted_qids) <= old_qids:
        raise HTTPException(422, "Invalid question ID")
    if len(submitted_oids) != len(set(submitted_oids)) or not set(submitted_oids) <= old_oids:
        raise HTTPException(422, "Invalid option ID")
    if payload.min_correct > sum(question.kind != "free_text" for question in payload.questions):
        raise HTTPException(422, "Threshold exceeds automatic question count")
    image_ids = {asset_id for question in payload.questions
                 for asset_id in [question.image_asset_id, *(option.image_asset_id for option in question.options)]
                 if asset_id is not None}
    if image_ids:
        valid_images = set(db.scalars(select(MediaAsset.id).where(
            MediaAsset.id.in_(image_ids), MediaAsset.kind == "image", MediaAsset.source_type == "upload")).all())
        if image_ids != valid_images:
            raise HTTPException(422, "Unknown test image")
    db.execute(delete(TestOption).where(TestOption.question_id.in_(old_qids)))
    db.execute(delete(TestQuestion).where(TestQuestion.test_id == test_id))
    db.flush()
    for position, question_in in enumerate(payload.questions):
        question = TestQuestion(id=question_in.id or uuid.uuid4(), test_id=test_id, position=position,
            kind=question_in.kind, prompt=question_in.prompt, required=question_in.required,
            image_asset_id=question_in.image_asset_id)
        db.add(question)
        db.flush()
        for option_position, option_in in enumerate(question_in.options):
            db.add(TestOption(id=option_in.id or uuid.uuid4(), question_id=question.id,
                position=option_position, text=option_in.text, correct=option_in.correct,
                image_asset_id=option_in.image_asset_id))
    test.title = title
    test.summary = payload.summary
    test.time_limit_minutes = payload.time_limit_minutes
    test.max_attempts = payload.max_attempts
    test.min_correct = payload.min_correct
    test.shuffle_questions = payload.shuffle_questions
    test.shuffle_options = payload.shuffle_options
    test.show_results = payload.show_results
    test.reward_points = payload.reward_points
    test.correction_days = payload.correction_days
    test.row_version += 1
    test.updated_at = datetime.now(timezone.utc)
    db.commit()
    return test_data(db, test)
