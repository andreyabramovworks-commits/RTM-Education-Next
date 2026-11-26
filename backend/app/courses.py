import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.copying import clone_item_content
from app.models import Article, Course, CourseItem, CourseSection, Employee, TestDefinition
from app.permissions import require_role

router = APIRouter(prefix="/admin/courses", tags=["courses"])


class NewCourse(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=20000)
    mode: str = Field(default="free", pattern="^(free|sequential)$")


class EditCourse(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(max_length=20000)
    mode: str = Field(pattern="^(free|sequential)$")
    row_version: int = Field(ge=1)


class NewSection(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    row_version: int = Field(ge=1)


def course_data(course: Course) -> dict:
    return {
        "id": str(course.id),
        "title": course.title,
        "description": course.description,
        "mode": course.mode,
        "status": course.status,
        "row_version": course.row_version,
        "updated_at": course.updated_at.isoformat(),
    }


@router.get("")
def list_courses(
    search: str = Query(default="", max_length=240),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _actor: Employee = Depends(require_role("teacher")),
):
    query = select(Course)
    if search:
        query = query.where(Course.title.ilike(f"%{search.replace('%', r'\%').replace('_', r'\_')}%", escape="\\"))
    rows = db.scalars(query.order_by(Course.updated_at.desc(), Course.id).offset(offset).limit(limit)).all()
    return [course_data(row) for row in rows]


@router.post("", status_code=201)
def create_course(payload: NewCourse, db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    course = Course(title=title, description=payload.description, mode=payload.mode, created_by=actor.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course_data(course)


@router.post("/{course_id}/copy", status_code=201)
def copy_course(course_id: uuid.UUID, db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    source = db.get(Course, course_id)
    if source is None:
        raise HTTPException(404)
    title = f"{source.title} — копия"[:240]
    copied = Course(title=title, description=source.description, mode=source.mode,
                    status="draft", created_by=actor.id)
    db.add(copied)
    db.flush()
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course_id)
        .order_by(CourseSection.position)).all()
    for section in sections:
        new_section = CourseSection(course_id=copied.id, title=section.title, position=section.position)
        db.add(new_section)
        db.flush()
        items = db.scalars(select(CourseItem).where(CourseItem.section_id == section.id)
            .order_by(CourseItem.position)).all()
        for item in items:
            article_id, test_id = clone_item_content(db, item, copied.id, actor)
            db.add(CourseItem(course_id=copied.id, section_id=new_section.id, kind=item.kind,
                article_id=article_id, test_id=test_id, position=item.position, required=item.required))
    db.commit()
    return get_course(copied.id, db, actor)


@router.get("/{course_id}")
def get_course(course_id: uuid.UUID, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("teacher"))):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course_id).order_by(CourseSection.position)).all()
    items = db.scalars(select(CourseItem).where(CourseItem.course_id == course_id).order_by(CourseItem.section_id, CourseItem.position)).all()
    article_ids = [item.article_id for item in items if item.article_id]
    article_titles = dict(db.execute(select(Article.id, Article.title).where(Article.id.in_(article_ids))).all()) if article_ids else {}
    test_ids = [item.test_id for item in items if item.test_id]
    test_titles = dict(db.execute(select(TestDefinition.id, TestDefinition.title).where(TestDefinition.id.in_(test_ids))).all()) if test_ids else {}
    return {**course_data(course), "sections": [{"id": str(s.id), "title": s.title, "position": s.position,
        "items": [{"id": str(item.id), "kind": item.kind, "article_id": str(item.article_id) if item.article_id else None,
                   "test_id": str(item.test_id) if item.test_id else None, "title": article_titles.get(item.article_id) or test_titles.get(item.test_id, "Тест"),
                   "position": item.position, "required": item.required}
                  for item in items if item.section_id == s.id]} for s in sections]}


@router.put("/{course_id}")
def edit_course(course_id: uuid.UUID, payload: EditCourse, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    result = db.execute(
        update(Course)
        .where(Course.id == course_id, Course.row_version == payload.row_version)
        .values(title=title, description=payload.description, mode=payload.mode,
                row_version=Course.row_version + 1, updated_at=datetime.now(timezone.utc))
        .returning(Course.id)
    ).first()
    if result is None:
        db.rollback()
        if db.get(Course, course_id) is None:
            raise HTTPException(404)
        raise HTTPException(409, "Course changed; reload before saving")
    db.commit()
    return course_data(db.get(Course, course_id))


@router.post("/{course_id}/sections", status_code=201)
def add_section(course_id: uuid.UUID, payload: NewSection, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    course = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if course is None:
        raise HTTPException(404)
    if course.row_version != payload.row_version:
        raise HTTPException(409, "Course changed; reload before saving")
    position = db.scalar(select(func.count()).select_from(CourseSection).where(CourseSection.course_id == course_id)) or 0
    section = CourseSection(course_id=course_id, title=title, position=position)
    db.add(section)
    course.row_version += 1
    course.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": str(section.id), "title": section.title, "position": section.position, "row_version": course.row_version}
