import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.db import get_db
from app.models import (Article, ArticleRevision, Assignment, AssignmentCampaign, Course,
                        CourseItem, CourseSection, Employee, ItemCompletion, RevisionAcknowledgement, TestDefinition)

router = APIRouter(prefix="/my/assignments", tags=["learning"])


def own_assignment(db: Session, assignment_id: uuid.UUID, employee: Employee, lock: bool = False) -> Assignment:
    query = select(Assignment).where(Assignment.id == assignment_id, Assignment.employee_id == employee.id)
    if lock:
        query = query.with_for_update()
    assignment = db.scalar(query)
    if assignment is None:
        raise HTTPException(404)
    return assignment


def mark_item_complete(db: Session, assignment: Assignment, item: CourseItem, method: str, now: datetime) -> None:
    existing = db.scalar(select(ItemCompletion.id).where(ItemCompletion.assignment_id == assignment.id,
        ItemCompletion.course_item_id == item.id))
    if existing is None:
        db.add(ItemCompletion(assignment_id=assignment.id, course_item_id=item.id, completed_at=now, method=method))
        db.flush()
    required_ids = set(db.scalars(select(CourseItem.id).where(CourseItem.course_id == item.course_id,
        CourseItem.required.is_(True))).all())
    done_ids = set(db.scalars(select(ItemCompletion.course_item_id).where(ItemCompletion.assignment_id == assignment.id,
        ItemCompletion.course_item_id.in_(required_ids))).all())
    if required_ids and required_ids <= done_ids:
        assignment.status = "completed"
        assignment.completed_at = now


def course_detail(db: Session, assignment: Assignment, campaign: AssignmentCampaign) -> dict:
    course = db.get(Course, campaign.target_id)
    if course is None:
        raise HTTPException(404)
    sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all()
    items = db.scalars(select(CourseItem).where(CourseItem.course_id == course.id).order_by(CourseItem.position)).all()
    article_ids = [item.article_id for item in items if item.article_id]
    articles = {article.id: article for article in db.scalars(select(Article).where(Article.id.in_(article_ids))).all()} if article_ids else {}
    test_ids = [item.test_id for item in items if item.test_id]
    tests = {test.id: test for test in db.scalars(select(TestDefinition).where(TestDefinition.id.in_(test_ids))).all()} if test_ids else {}
    done = {row.course_item_id for row in db.scalars(select(ItemCompletion).where(ItemCompletion.assignment_id == assignment.id)).all()}
    seen_required_incomplete = False
    section_data = []
    required_total = sum(1 for item in items if item.required)
    required_done = sum(1 for item in items if item.required and item.id in done)
    for section in sections:
        section_items = []
        for item in [row for row in items if row.section_id == section.id]:
            article = articles.get(item.article_id)
            test = tests.get(item.test_id)
            locked = course.mode == "sequential" and seen_required_incomplete and item.id not in done
            section_items.append({"id": str(item.id), "kind": item.kind, "title": article.title if article else test.title if test else "Тест",
                                  "required": item.required, "completed": item.id in done, "locked": locked,
                                  "test_id": str(test.id) if test else None,
                                  "article": {"id": str(article.id), "summary": article.summary, "body": article.body}
                                  if article and not locked else None})
            if item.required and item.id not in done:
                seen_required_incomplete = True
        section_data.append({"id": str(section.id), "title": section.title, "items": section_items})
    return {"id": str(assignment.id), "title": campaign.title, "status": assignment.status,
            "target_type": "course", "course": {"id": str(course.id), "title": course.title,
            "description": course.description, "mode": course.mode, "sections": section_data},
            "required_total": required_total, "required_done": required_done,
            "due_at": assignment.due_at.isoformat() if assignment.due_at else None}


@router.get("/{assignment_id}")
def detail(assignment_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.status != "active":
        raise HTTPException(404)
    if campaign.target_type == "course":
        return course_detail(db, assignment, campaign)
    if campaign.target_type == "article_revision":
        revision = db.get(ArticleRevision, campaign.target_id)
        if revision is None:
            raise HTTPException(404)
        article = db.get(Article, revision.article_id)
        acknowledged = db.scalar(select(RevisionAcknowledgement.id).where(RevisionAcknowledgement.assignment_id == assignment.id)) is not None
        test = db.scalar(select(TestDefinition).where(TestDefinition.article_revision_id == revision.id))
        return {"id": str(assignment.id), "title": campaign.title, "status": assignment.status,
                "target_type": "article_revision", "revision": {"id": str(revision.id),
                "article_title": article.title if article else campaign.title, "number": revision.revision_no,
                "date": revision.revision_date.isoformat(), "description": revision.description,
                "body": revision.body_snapshot, "acknowledged": acknowledged,
                "test_id": str(test.id) if test else None},
                "due_at": assignment.due_at.isoformat() if assignment.due_at else None}
    if campaign.target_type == "course_article":
        article = db.get(Article, campaign.target_id)
        if article is None or article.owner_course_id is None:
            raise HTTPException(404)
        return {"id": str(assignment.id), "title": campaign.title, "status": assignment.status,
                "target_type": "course_article", "article": {"id": str(article.id),
                    "title": article.title, "summary": article.summary, "body": article.body},
                "due_at": assignment.due_at.isoformat() if assignment.due_at else None}
    if campaign.target_type == "course_test":
        test = db.get(TestDefinition, campaign.target_id)
        if test is None or test.owner_course_id is None:
            raise HTTPException(404)
        return {"id": str(assignment.id), "title": campaign.title, "status": assignment.status,
                "target_type": "course_test", "test": {"id": str(test.id), "title": test.title},
                "due_at": assignment.due_at.isoformat() if assignment.due_at else None}
    raise HTTPException(404)


@router.post("/{assignment_id}/start")
def start(assignment_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    if assignment.status == "not_started":
        assignment.status = "in_progress"
        assignment.started_at = datetime.now(timezone.utc)
        db.commit()
    elif assignment.status not in ("in_progress", "pending_review", "returned", "completed"):
        raise HTTPException(409, "Assignment cannot be started")
    return {"status": assignment.status}


@router.post("/{assignment_id}/items/{item_id}/acknowledge")
def acknowledge_item(assignment_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db),
                     employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "course":
        raise HTTPException(404)
    if assignment.status not in ("in_progress", "completed"):
        raise HTTPException(409, "Start assignment first")
    item = db.scalar(select(CourseItem).where(CourseItem.id == item_id, CourseItem.course_id == campaign.target_id))
    if item is None:
        raise HTTPException(404)
    if item.kind != "article":
        raise HTTPException(409, "Test requires an attempt")
    completed = db.scalar(select(ItemCompletion).where(ItemCompletion.assignment_id == assignment_id,
                                                        ItemCompletion.course_item_id == item_id))
    if completed is not None:
        return {"completed": True, "assignment_status": assignment.status}
    course = db.get(Course, campaign.target_id)
    if course is None:
        raise HTTPException(404)
    if course.mode == "sequential":
        sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all()
        positions = {section.id: section.position for section in sections}
        earlier_required = db.scalars(select(CourseItem).where(CourseItem.course_id == course.id,
            CourseItem.required.is_(True))).all()
        current_key = (positions[item.section_id], item.position)
        earlier_ids = [row.id for row in earlier_required if (positions[row.section_id], row.position) < current_key]
        done_ids = set(db.scalars(select(ItemCompletion.course_item_id).where(ItemCompletion.assignment_id == assignment_id,
            ItemCompletion.course_item_id.in_(earlier_ids))).all())
        if len(done_ids) != len(earlier_ids):
            raise HTTPException(409, "Previous required items are incomplete")
    mark_item_complete(db, assignment, item, "button", datetime.now(timezone.utc))
    db.commit()
    return {"completed": True, "assignment_status": assignment.status}


@router.post("/{assignment_id}/revision/acknowledge")
def acknowledge_revision(assignment_id: uuid.UUID, db: Session = Depends(get_db),
                         employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "article_revision":
        raise HTTPException(404)
    if assignment.status not in ("in_progress", "completed"):
        raise HTTPException(409, "Start assignment first")
    if db.scalar(select(RevisionAcknowledgement.id).where(RevisionAcknowledgement.assignment_id == assignment_id)):
        return {"completed": True, "assignment_status": assignment.status}
    db.add(RevisionAcknowledgement(assignment_id=assignment.id, article_revision_id=campaign.target_id,
        completed_at=datetime.now(timezone.utc), method="button"))
    has_test = db.scalar(select(TestDefinition.id).where(TestDefinition.article_revision_id == campaign.target_id))
    if not has_test:
        assignment.status = "completed"
        assignment.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"completed": True, "assignment_status": assignment.status}


@router.post("/{assignment_id}/article/acknowledge")
def acknowledge_standalone_article(assignment_id: uuid.UUID, db: Session = Depends(get_db),
                                   employee: Employee = Depends(current_employee)):
    assignment = own_assignment(db, assignment_id, employee, lock=True)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.target_type != "course_article":
        raise HTTPException(404)
    if assignment.status == "completed":
        return {"completed": True, "assignment_status": assignment.status}
    if assignment.status != "in_progress":
        raise HTTPException(409, "Start assignment first")
    assignment.status = "completed"
    assignment.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"completed": True, "assignment_status": assignment.status}
