"""ACL-checked live Google document reads for article blocks."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.db import get_db
from app.google_documents import GoogleReadError, read_document, read_spreadsheet
from app.knowledge import visible_article_ids
from app.models import Article, Assignment, AssignmentCampaign, Employee, FolderArticle, KnowledgeFolder
from app.permissions import ROLE_RANK, require_role


router = APIRouter(prefix="/google", tags=["google"])


def contains_source(value: object, file_id: str, kind: str) -> bool:
    if isinstance(value, dict):
        attrs = value.get("attrs")
        if value.get("type") == kind and isinstance(attrs, dict) and attrs.get("fileId") == file_id:
            return True
        return any(contains_source(item, file_id, kind) for item in value.values())
    if isinstance(value, list):
        return any(contains_source(item, file_id, kind) for item in value)
    return False


def source_ids(value: object) -> set[tuple[str, str]]:
    if isinstance(value, dict):
        attrs = value.get("attrs")
        found = {(value["type"], attrs["fileId"])} if value.get("type") in ("google_document", "google_spreadsheet") and isinstance(attrs, dict) and isinstance(attrs.get("fileId"), str) else set()
        return found.union(*(source_ids(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(source_ids(item) for item in value))
    return set()


def can_read_article(db: Session, employee: Employee, article: Article) -> bool:
    if ROLE_RANK.get(employee.effective_role, 0) >= ROLE_RANK["editor"]:
        return True
    folders = db.scalars(select(KnowledgeFolder)).all()
    placements = db.scalars(select(FolderArticle)).all()
    if article.id in visible_article_ids(db, employee, folders, placements):
        return True
    targets = [and_(AssignmentCampaign.target_type == "course_article", AssignmentCampaign.target_id == article.id)]
    if article.owner_course_id:
        targets.append(and_(AssignmentCampaign.target_type == "course",
                            AssignmentCampaign.target_id == article.owner_course_id))
    assignment = db.scalar(select(Assignment.id).join(AssignmentCampaign,
        Assignment.campaign_id == AssignmentCampaign.id).where(
        Assignment.employee_id == employee.id, AssignmentCampaign.status == "active",
        Assignment.status.notin_(["cancelled", "exempted"]),
        or_(*targets)).limit(1))
    return assignment is not None


@router.get("/articles/{article_id}/documents/{file_id}")
def live_document(article_id: uuid.UUID, file_id: str, db: Session = Depends(get_db),
                  employee: Employee = Depends(current_employee)):
    article = db.get(Article, article_id)
    if article is None or not contains_source(article.body, file_id, "google_document") or not can_read_article(db, employee, article):
        raise HTTPException(404)
    try:
        data = read_document(file_id)
    except GoogleReadError as exc:
        raise HTTPException(503, "Google document is unavailable") from exc
    return {key: data[key] for key in ("title", "revision_id", "blocks", "fetched_at")}


@router.get("/articles/{article_id}/spreadsheets/{file_id}")
def live_spreadsheet(article_id: uuid.UUID, file_id: str, db: Session = Depends(get_db),
                     employee: Employee = Depends(current_employee)):
    article = db.get(Article, article_id)
    if article is None or not contains_source(article.body, file_id, "google_spreadsheet") or not can_read_article(db, employee, article):
        raise HTTPException(404)
    try:
        data = read_spreadsheet(file_id)
    except GoogleReadError as exc:
        raise HTTPException(503, "Google spreadsheet is unavailable") from exc
    return {key: data[key] for key in ("title", "revision_id", "blocks", "fetched_at")}


@router.get("/admin/documents/{file_id}/verify")
def verify_document(file_id: str, _actor: Employee = Depends(require_role("editor"))):
    try:
        data = read_document(file_id)
    except GoogleReadError as exc:
        raise HTTPException(503, "Google document is unavailable") from exc
    return {key: data[key] for key in ("file_id", "title", "revision_id", "fetched_at")}


@router.get("/admin/sources")
def knowledge_sources(db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    articles = db.scalars(select(Article).where(Article.owner_course_id.is_(None)).order_by(Article.title)).all()
    return [{"article_id": str(article.id), "article_title": article.title, "file_id": file_id,
             "source_kind": kind, "source_url": f"https://docs.google.com/{'document' if kind == 'google_document' else 'spreadsheets'}/d/{file_id}/edit"}
            for article in articles for kind, file_id in sorted(source_ids(article.body))]
