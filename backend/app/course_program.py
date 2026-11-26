import uuid
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.copying import clone_item_content
from app.models import Article, Course, CourseItem, CourseSection, Employee, TestDefinition, TestOption, TestQuestion
from app.permissions import require_role

router = APIRouter(prefix="/admin/courses", tags=["course-program"])


class RenameSection(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    row_version: int = Field(ge=1)


class ReorderSections(BaseModel):
    section_ids: list[uuid.UUID]
    row_version: int = Field(ge=1)


class OrderedSection(BaseModel):
    id: uuid.UUID
    item_ids: list[uuid.UUID]


class ReorderProgram(BaseModel):
    sections: list[OrderedSection]
    row_version: int = Field(ge=1)


class NewArticle(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    row_version: int = Field(ge=1)


class CopyItem(BaseModel):
    source_item_id: uuid.UUID
    row_version: int = Field(ge=1)


class EditArticle(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(max_length=20000)
    body: dict
    row_version: int = Field(ge=1)


class ActivateCourse(BaseModel):
    row_version: int = Field(ge=1)
    confirmed: bool


def lock_course(db: Session, course_id: uuid.UUID, version: int) -> Course:
    course = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if course is None:
        raise HTTPException(404)
    if course.row_version != version:
        raise HTTPException(409, "Course changed; reload before saving")
    return course


@router.put("/{course_id}/sections/order")
def reorder_sections(course_id: uuid.UUID, payload: ReorderSections, db: Session = Depends(get_db),
                     _actor: Employee = Depends(require_role("editor"))):
    course = lock_course(db, course_id, payload.row_version)
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course_id).order_by(CourseSection.position)).all()
    if len(payload.section_ids) != len(sections) or set(payload.section_ids) != {section.id for section in sections}:
        raise HTTPException(422, "Section list does not match course")
    by_id = {section.id: section for section in sections}
    for index, section in enumerate(sections):
        section.position = 1_000_000 + index
    db.flush()
    for index, section_id in enumerate(payload.section_ids):
        by_id[section_id].position = index
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"row_version": course.row_version}


@router.put("/{course_id}/program/order")
def reorder_program(course_id: uuid.UUID, payload: ReorderProgram, db: Session = Depends(get_db),
                    _actor: Employee = Depends(require_role("editor"))):
    course = lock_course(db, course_id, payload.row_version)
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course_id).with_for_update()).all()
    items = db.scalars(select(CourseItem).where(CourseItem.course_id == course_id).with_for_update()).all()
    section_ids = [row.id for row in payload.sections]
    item_ids = [item_id for row in payload.sections for item_id in row.item_ids]
    if (len(section_ids) != len(sections) or len(set(section_ids)) != len(section_ids)
            or set(section_ids) != {row.id for row in sections}
            or len(item_ids) != len(items) or len(set(item_ids)) != len(item_ids)
            or set(item_ids) != {row.id for row in items}):
        raise HTTPException(422, "Program order does not match course")
    by_section = {row.id: row for row in sections}
    by_item = {row.id: row for row in items}
    for index, section in enumerate(sections):
        section.position = 1_000_000 + index
    for index, item in enumerate(items):
        item.position = 1_000_000 + index
    db.flush()
    for section_index, ordered_section in enumerate(payload.sections):
        by_section[ordered_section.id].position = section_index
        for item_index, item_id in enumerate(ordered_section.item_ids):
            by_item[item_id].section_id = ordered_section.id
            by_item[item_id].position = item_index
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"row_version": course.row_version}


@router.put("/{course_id}/sections/{section_id}")
def rename_section(course_id: uuid.UUID, section_id: uuid.UUID, payload: RenameSection,
                   db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    course = lock_course(db, course_id, payload.row_version)
    section = db.scalar(select(CourseSection).where(CourseSection.id == section_id, CourseSection.course_id == course_id))
    if section is None:
        raise HTTPException(404)
    section.title = title
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": str(section.id), "title": section.title, "position": section.position, "row_version": course.row_version}


@router.post("/{course_id}/sections/{section_id}/articles", status_code=201)
def create_course_article(course_id: uuid.UUID, section_id: uuid.UUID, payload: NewArticle,
                          db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    course = lock_course(db, course_id, payload.row_version)
    if db.scalar(select(CourseSection.id).where(CourseSection.id == section_id, CourseSection.course_id == course_id)) is None:
        raise HTTPException(404)
    position = db.scalar(select(func.count()).select_from(CourseItem).where(CourseItem.section_id == section_id)) or 0
    article = Article(owner_course_id=course_id, title=title, summary="",
        body={"type": "doc", "content": [{"type": "paragraph"}]}, created_by=actor.id)
    db.add(article)
    db.flush()
    item = CourseItem(course_id=course_id, section_id=section_id, kind="article", article_id=article.id,
        position=position, required=True)
    db.add(item)
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": str(item.id), "article_id": str(article.id), "title": article.title,
            "position": item.position, "required": item.required, "kind": item.kind,
            "row_version": course.row_version}


@router.post("/{course_id}/sections/{section_id}/copy-item", status_code=201)
def copy_item(course_id: uuid.UUID, section_id: uuid.UUID, payload: CopyItem,
              db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    course = lock_course(db, course_id, payload.row_version)
    if db.scalar(select(CourseSection.id).where(CourseSection.id == section_id,
                                                CourseSection.course_id == course_id)) is None:
        raise HTTPException(404)
    source = db.get(CourseItem, payload.source_item_id)
    if source is None:
        raise HTTPException(404)
    article_id, test_id = clone_item_content(db, source, course_id, actor)
    position = db.scalar(select(func.count()).select_from(CourseItem).where(CourseItem.section_id == section_id)) or 0
    item = CourseItem(course_id=course_id, section_id=section_id, kind=source.kind,
        article_id=article_id, test_id=test_id, position=position, required=source.required)
    db.add(item)
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": str(item.id), "article_id": str(article_id) if article_id else None,
            "test_id": str(test_id) if test_id else None, "kind": item.kind,
            "position": item.position, "required": item.required, "row_version": course.row_version}


@router.get("/{course_id}/articles/{article_id}")
def get_course_article(course_id: uuid.UUID, article_id: uuid.UUID, db: Session = Depends(get_db),
                       _actor: Employee = Depends(require_role("teacher"))):
    article = db.scalar(select(Article).where(Article.id == article_id, Article.owner_course_id == course_id))
    if article is None:
        raise HTTPException(404)
    return {"id": str(article.id), "title": article.title, "summary": article.summary,
            "body": article.body, "row_version": article.row_version}


@router.put("/{course_id}/articles/{article_id}")
def edit_course_article(course_id: uuid.UUID, article_id: uuid.UUID, payload: EditArticle,
                        db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title or payload.body.get("type") != "doc":
        raise HTTPException(422, "Invalid article")
    article = db.scalar(select(Article).where(Article.id == article_id, Article.owner_course_id == course_id).with_for_update())
    if article is None:
        raise HTTPException(404)
    if article.row_version != payload.row_version:
        raise HTTPException(409, "Article changed; reload before saving")
    article.title = title
    article.summary = payload.summary
    article.body = deepcopy(payload.body)
    article.row_version += 1
    article.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": str(article.id), "title": article.title, "summary": article.summary,
            "body": article.body, "row_version": article.row_version}


@router.post("/{course_id}/activate")
def activate_course(course_id: uuid.UUID, payload: ActivateCourse, db: Session = Depends(get_db),
                    _actor: Employee = Depends(require_role("editor"))):
    if not payload.confirmed:
        raise HTTPException(422, "Activation needs explicit confirmation")
    course = lock_course(db, course_id, payload.row_version)
    if course.status == "archived":
        raise HTTPException(409, "Archived course cannot be activated")
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course_id)).all()
    if not sections:
        raise HTTPException(422, "Course needs a section")
    items = db.scalars(select(CourseItem).where(CourseItem.course_id == course_id)).all()
    if not items:
        raise HTTPException(422, "Course needs at least one item")
    articles = {row.id: row for row in db.scalars(select(Article).where(Article.owner_course_id == course_id)).all()}
    for item in items:
        if item.kind == "test":
            test = db.get(TestDefinition, item.test_id)
            if test is None or test.owner_course_id != course_id:
                raise HTTPException(422, "Course test is missing")
            questions = db.scalars(select(TestQuestion).where(TestQuestion.test_id == test.id)).all()
            if not questions:
                raise HTTPException(422, "Course test has no questions")
            if test.min_correct > sum(question.kind != "free_text" for question in questions):
                raise HTTPException(422, "Test threshold is invalid")
            for question in questions:
                if not question.prompt.strip():
                    raise HTTPException(422, "Test question is incomplete")
                options = db.scalars(select(TestOption).where(TestOption.question_id == question.id)).all()
                correct_count = sum(option.correct for option in options)
                if question.kind == "single" and (len(options) < 2 or correct_count != 1):
                    raise HTTPException(422, "Single-choice question needs one correct option")
                if question.kind == "multiple" and (len(options) < 2 or correct_count < 1):
                    raise HTTPException(422, "Multiple-choice question needs correct options")
            continue
        article = articles.get(item.article_id)
        if article is None or not article.title.strip() or not article.body.get("content"):
            raise HTTPException(422, "Course article is incomplete")
        if all(not node.get("content") for node in article.body.get("content", []) if isinstance(node, dict)):
            raise HTTPException(422, "Course article is empty")
    if course.status != "active":
        course.status = "active"
        course.row_version += 1
        course.updated_at = datetime.now(timezone.utc)
        db.commit()
    return {"id": str(course.id), "status": course.status, "row_version": course.row_version}
