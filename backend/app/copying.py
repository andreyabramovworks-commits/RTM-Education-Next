"""Create independent course materials without learner history."""
import uuid
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CourseItem, Employee, TestDefinition, TestOption, TestQuestion


def clone_item_content(db: Session, item: CourseItem, target_course_id: uuid.UUID,
                       actor: Employee) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if item.kind == "article":
        article = db.get(Article, item.article_id)
        if article is None:
            raise HTTPException(409, "Source article is missing")
        duplicate = Article(owner_course_id=target_course_id, copied_from_article_id=article.id,
            title=article.title, summary=article.summary, body=deepcopy(article.body), created_by=actor.id)
        db.add(duplicate)
        db.flush()
        return duplicate.id, None
    if item.kind != "test":
        raise HTTPException(409, "Unknown source item")
    test = db.get(TestDefinition, item.test_id)
    if test is None:
        raise HTTPException(409, "Source test is missing")
    duplicate_test = clone_test_content(db, test, actor, target_course_id=target_course_id)
    return None, duplicate_test.id


def clone_test_content(db: Session, test: TestDefinition, actor: Employee,
                       target_course_id: uuid.UUID | None = None,
                       article_revision_id: uuid.UUID | None = None) -> TestDefinition:
    duplicate_test = TestDefinition(owner_course_id=target_course_id, article_revision_id=article_revision_id,
        title=test.title, summary=test.summary,
        time_limit_minutes=test.time_limit_minutes, max_attempts=test.max_attempts,
        min_correct=test.min_correct, shuffle_questions=test.shuffle_questions,
        shuffle_options=test.shuffle_options, show_results=test.show_results,
        reward_points=test.reward_points, correction_days=test.correction_days, created_by=actor.id)
    db.add(duplicate_test)
    db.flush()
    questions = db.scalars(select(TestQuestion).where(TestQuestion.test_id == test.id)
        .order_by(TestQuestion.position)).all()
    for question in questions:
        duplicate_question = TestQuestion(test_id=duplicate_test.id, position=question.position,
            kind=question.kind, prompt=question.prompt, required=question.required,
            image_asset_id=question.image_asset_id)
        db.add(duplicate_question)
        db.flush()
        options = db.scalars(select(TestOption).where(TestOption.question_id == question.id)
            .order_by(TestOption.position)).all()
        for option in options:
            db.add(TestOption(question_id=duplicate_question.id, position=option.position,
                text=option.text, correct=option.correct, image_asset_id=option.image_asset_id))
    return duplicate_test
