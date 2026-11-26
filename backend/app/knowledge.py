import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.catalog_import import apply as apply_catalog_import, preview as preview_catalog_import, read_catalog
from app.db import get_db
from app.copying import clone_test_content
from app.google_documents import GoogleReadError, snapshot_google_nodes
from app.models import Article, ArticleRevision, Department, Employee, FolderArticle, KnowledgeFolder, KnowledgeGrant, TestDefinition
from app.permissions import require_role

router = APIRouter(tags=["knowledge"])


class CatalogImportConfirmation(BaseModel):
    confirmed: bool


@router.get("/admin/knowledge/catalog-import/preview")
def catalog_import_preview(db: Session = Depends(get_db), employee: Employee = Depends(require_role("admin"))):
    records, warnings = read_catalog()
    return preview_catalog_import(db, records, warnings)


@router.post("/admin/knowledge/catalog-import")
def catalog_import_confirm(body: CatalogImportConfirmation, db: Session = Depends(get_db),
                           employee: Employee = Depends(require_role("admin"))):
    if not body.confirmed:
        raise HTTPException(400, "Подтвердите однократный импорт")
    records, warnings = read_catalog()
    result = apply_catalog_import(db, records, employee.id)
    return {**result, "warnings": warnings}


class NewFolder(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=20000)
    parent_id: uuid.UUID | None = None


class NewArticle(BaseModel):
    folder_id: uuid.UUID
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=20000)


class EditArticle(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(max_length=20000)
    body: dict
    row_version: int = Field(ge=1)


class AccessGrant(BaseModel):
    target_type: str = Field(pattern="^(folder|article)$")
    target_id: uuid.UUID
    subject_type: str = Field(pattern="^(employee|department|subdepartment)$")
    subject_id: str = Field(min_length=1, max_length=64)


class PublishRevision(BaseModel):
    revision_date: date
    description: str = Field(min_length=1, max_length=20000)
    row_version: int = Field(ge=1)
    completion_mode: str = Field(default="acknowledge", pattern="^(acknowledge|full_test)$")
    copy_test_id: uuid.UUID | None = None


class WithdrawRevision(BaseModel):
    reason: str = Field(min_length=1, max_length=20000)
    confirmed: bool


class MoveArticle(BaseModel):
    folder_id: uuid.UUID
    confirmed: bool


class MoveFolder(BaseModel):
    parent_id: uuid.UUID | None
    confirmed: bool


class PreviewMove(BaseModel):
    target_type: str = Field(pattern="^(article|folder)$")
    target_id: uuid.UUID
    destination_id: uuid.UUID | None = None


def folder_data(folder: KnowledgeFolder) -> dict:
    return {"id": str(folder.id), "parent_id": str(folder.parent_id) if folder.parent_id else None,
            "title": folder.title, "description": folder.description}


def article_data(article: Article, folder_id: uuid.UUID | None = None) -> dict:
    return {"id": str(article.id), "folder_id": str(folder_id) if folder_id else None,
            "title": article.title, "summary": article.summary, "body": article.body,
            "row_version": article.row_version, "updated_at": article.updated_at.isoformat()}


def visible_article_ids(db: Session, employee: Employee, folders: list[KnowledgeFolder], placements: list[FolderArticle]) -> set[uuid.UUID]:
    departments = {row.bitrix_id: row for row in db.scalars(select(Department)).all()}
    grants = db.scalars(select(KnowledgeGrant)).all()
    return visible_article_ids_with_data(employee, folders, placements, departments, grants)


def visible_article_ids_with_data(employee: Employee, folders: list[KnowledgeFolder], placements: list[FolderArticle],
                                  departments: dict[int, Department], all_grants: list[KnowledgeGrant]) -> set[uuid.UUID]:
    if employee.effective_role in ("admin", "developer"):
        return {placement.article_id for placement in placements}
    ancestors: set[int] = set()
    for department_id in employee.department_ids:
        cursor = department_id
        visited: set[int] = set()
        while cursor and cursor not in visited:
            ancestors.add(cursor)
            visited.add(cursor)
            node = departments.get(cursor)
            cursor = node.parent_id if node else None
    direct_department_ids = {str(value) for value in employee.department_ids}
    ancestor_ids = {str(value) for value in ancestors}
    grants = [grant for grant in all_grants
              if (grant.subject_type == "employee" and grant.subject_id == str(employee.bitrix_id))
              or (grant.subject_type == "department" and grant.subject_id in direct_department_ids)
              or (grant.subject_type == "subdepartment" and grant.subject_id in ancestor_ids)]
    folder_map = {folder.id: folder for folder in folders}
    granted_folders = {grant.target_id for grant in grants if grant.target_type == "folder"}
    direct_articles = {grant.target_id for grant in grants if grant.target_type == "article"}
    result = set(direct_articles)
    for placement in placements:
        cursor = placement.folder_id
        visited: set[uuid.UUID] = set()
        while cursor and cursor not in visited:
            if cursor in granted_folders:
                result.add(placement.article_id)
                break
            visited.add(cursor)
            folder = folder_map.get(cursor)
            cursor = folder.parent_id if folder else None
    return result


def validate_folder_destination(folder_id: uuid.UUID, parent_id: uuid.UUID | None,
                                folders: list[KnowledgeFolder]) -> None:
    if parent_id == folder_id:
        raise HTTPException(422, "Folder cannot contain itself")
    parents = {row.id: row.parent_id for row in folders}
    if parent_id is not None and parent_id not in parents:
        raise HTTPException(404)
    cursor = parent_id
    visited: set[uuid.UUID] = set()
    while cursor is not None:
        if cursor == folder_id or cursor in visited:
            raise HTTPException(422, "Folder cycle")
        visited.add(cursor)
        cursor = parents.get(cursor)


@router.post("/admin/knowledge/move-preview")
def preview_move(payload: PreviewMove, db: Session = Depends(get_db),
                 _actor: Employee = Depends(require_role("admin"))):
    folders = db.scalars(select(KnowledgeFolder)).all()
    placements = db.scalars(select(FolderArticle)).all()
    next_folders = list(folders)
    next_placements = list(placements)
    if payload.target_type == "folder":
        folder = next((row for row in folders if row.id == payload.target_id), None)
        if folder is None:
            raise HTTPException(404)
        validate_folder_destination(folder.id, payload.destination_id, folders)
        changed = SimpleNamespace(id=folder.id, parent_id=payload.destination_id)
        next_folders = [changed if row.id == folder.id else row for row in folders]
    else:
        if payload.destination_id is None or not any(row.id == payload.destination_id for row in folders):
            raise HTTPException(404)
        article = db.get(Article, payload.target_id)
        placement = next((row for row in placements if row.article_id == payload.target_id), None)
        if article is None or article.owner_course_id is not None or placement is None:
            raise HTTPException(404)
        changed = SimpleNamespace(article_id=placement.article_id, folder_id=payload.destination_id)
        next_placements = [changed if row.article_id == placement.article_id else row for row in placements]
    departments = {row.bitrix_id: row for row in db.scalars(select(Department)).all()}
    grants = db.scalars(select(KnowledgeGrant)).all()
    employees = db.scalars(select(Employee).where(Employee.active.is_(True)).order_by(
        Employee.last_name, Employee.first_name)).all()
    gained, lost = [], []
    changed_articles: set[uuid.UUID] = set()
    for employee in employees:
        before = visible_article_ids_with_data(employee, folders, placements, departments, grants)
        after = visible_article_ids_with_data(employee, next_folders, next_placements, departments, grants)
        newly_visible = after - before
        no_longer_visible = before - after
        changed_articles.update(newly_visible | no_longer_visible)
        person = {"bitrix_id": employee.bitrix_id,
                  "name": f"{employee.first_name} {employee.last_name}".strip()}
        if newly_visible:
            gained.append({**person, "article_count": len(newly_visible)})
        if no_longer_visible:
            lost.append({**person, "article_count": len(no_longer_visible)})
    return {"gained": gained, "lost": lost, "affected_article_count": len(changed_articles)}


@router.get("/knowledge")
def list_knowledge(db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    folders = db.scalars(select(KnowledgeFolder).order_by(KnowledgeFolder.title)).all()
    placements = db.scalars(select(FolderArticle)).all()
    allowed = visible_article_ids(db, employee, folders, placements)
    placement_map = {placement.article_id: placement.folder_id for placement in placements}
    folder_map = {folder.id: folder for folder in folders}
    visible_folders: set[uuid.UUID] = set()
    for article_id in allowed:
        cursor = placement_map.get(article_id)
        while cursor and cursor not in visible_folders:
            visible_folders.add(cursor)
            folder = folder_map.get(cursor)
            cursor = folder.parent_id if folder else None
    articles = db.scalars(select(Article).where(Article.id.in_(allowed)).order_by(Article.title)).all() if allowed else []
    return {"folders": [folder_data(folder) for folder in folders if folder.id in visible_folders],
            "articles": [article_data(article, placement_map.get(article.id)) for article in articles]}


@router.get("/admin/knowledge")
def list_knowledge_admin(db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    folders = db.scalars(select(KnowledgeFolder).order_by(KnowledgeFolder.title)).all()
    placements = db.scalars(select(FolderArticle)).all()
    placement_map = {row.article_id: row.folder_id for row in placements}
    articles = db.scalars(select(Article).where(Article.owner_course_id.is_(None)).order_by(Article.title)).all()
    return {"folders": [folder_data(folder) for folder in folders],
            "articles": [article_data(article, placement_map.get(article.id)) for article in articles]}


@router.get("/knowledge/articles/{article_id}")
def read_article(article_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    folders = db.scalars(select(KnowledgeFolder)).all()
    placements = db.scalars(select(FolderArticle)).all()
    if article_id not in visible_article_ids(db, employee, folders, placements):
        raise HTTPException(404)
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404)
    placement = next((row for row in placements if row.article_id == article_id), None)
    revisions = db.scalars(select(ArticleRevision).where(ArticleRevision.article_id == article_id,
        ArticleRevision.deleted_at.is_(None)).order_by(ArticleRevision.revision_no.desc())).all()
    return {**article_data(article, placement.folder_id if placement else None),
            "revisions": [{"id": str(row.id), "number": row.revision_no, "date": row.revision_date.isoformat(),
                           "description": row.description} for row in revisions]}


@router.get("/knowledge/revisions/{revision_id}")
def read_revision(revision_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    revision = db.get(ArticleRevision, revision_id)
    if revision is None:
        raise HTTPException(404)
    folders = db.scalars(select(KnowledgeFolder)).all()
    placements = db.scalars(select(FolderArticle)).all()
    if revision.article_id not in visible_article_ids(db, employee, folders, placements):
        raise HTTPException(404)
    return {"id": str(revision.id), "article_id": str(revision.article_id),
            "number": revision.revision_no, "date": revision.revision_date.isoformat(),
            "description": revision.description, "body": revision.body_snapshot}


@router.post("/admin/knowledge/folders", status_code=201)
def create_folder(payload: NewFolder, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("admin"))):
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    if payload.parent_id and db.get(KnowledgeFolder, payload.parent_id) is None:
        raise HTTPException(404)
    folder = KnowledgeFolder(parent_id=payload.parent_id, title=title, description=payload.description)
    db.add(folder)
    db.commit()
    return folder_data(folder)


@router.post("/admin/knowledge/articles", status_code=201)
def create_article(payload: NewArticle, db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    if db.get(KnowledgeFolder, payload.folder_id) is None:
        raise HTTPException(404)
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, "Title is required")
    article = Article(title=title, summary=payload.summary, body={"type": "doc", "content": [{"type": "paragraph"}]}, created_by=actor.id)
    db.add(article)
    db.flush()
    db.add(FolderArticle(article_id=article.id, folder_id=payload.folder_id))
    db.commit()
    return article_data(article, payload.folder_id)


@router.put("/admin/knowledge/articles/{article_id}/folder")
def move_article(article_id: uuid.UUID, payload: MoveArticle, db: Session = Depends(get_db),
                 _actor: Employee = Depends(require_role("admin"))):
    if not payload.confirmed:
        raise HTTPException(422, "Confirm access change")
    article = db.get(Article, article_id)
    if article is None or article.owner_course_id is not None:
        raise HTTPException(404)
    if db.get(KnowledgeFolder, payload.folder_id) is None:
        raise HTTPException(404)
    placement = db.scalar(select(FolderArticle).where(FolderArticle.article_id == article_id).with_for_update())
    if placement is None:
        raise HTTPException(404)
    placement.folder_id = payload.folder_id
    db.commit()
    return article_data(article, payload.folder_id)


@router.put("/admin/knowledge/folders/{folder_id}/parent")
def move_folder(folder_id: uuid.UUID, payload: MoveFolder, db: Session = Depends(get_db),
                _actor: Employee = Depends(require_role("admin"))):
    if not payload.confirmed:
        raise HTTPException(422, "Confirm access change")
    folder = db.scalar(select(KnowledgeFolder).where(KnowledgeFolder.id == folder_id).with_for_update())
    if folder is None:
        raise HTTPException(404)
    validate_folder_destination(folder_id, payload.parent_id, db.scalars(select(KnowledgeFolder)).all())
    folder.parent_id = payload.parent_id
    db.commit()
    return folder_data(folder)


@router.put("/admin/knowledge/articles/{article_id}")
def update_article(article_id: uuid.UUID, payload: EditArticle, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    title = payload.title.strip()
    if not title or payload.body.get("type") != "doc":
        raise HTTPException(422, "Invalid article")
    article = db.scalar(select(Article).where(Article.id == article_id, Article.owner_course_id.is_(None)).with_for_update())
    if article is None:
        raise HTTPException(404)
    if article.row_version != payload.row_version:
        raise HTTPException(409, "Article changed; reload before saving")
    article.title = title
    article.summary = payload.summary
    article.body = payload.body
    article.row_version += 1
    article.updated_at = datetime.now(timezone.utc)
    db.commit()
    placement = db.get(FolderArticle, article_id)
    return article_data(article, placement.folder_id if placement else None)


@router.get("/admin/knowledge/articles/{article_id}/revisions")
def list_revisions(article_id: uuid.UUID, db: Session = Depends(get_db), _actor: Employee = Depends(require_role("editor"))):
    article = db.get(Article, article_id)
    if article is None or article.owner_course_id is not None:
        raise HTTPException(404)
    rows = db.scalars(select(ArticleRevision).where(ArticleRevision.article_id == article_id)
        .order_by(ArticleRevision.revision_no.desc())).all()
    tests = {row.article_revision_id: row.id for row in db.scalars(select(TestDefinition).where(
        TestDefinition.article_revision_id.in_([revision.id for revision in rows]))).all()} if rows else {}
    return [{"id": str(row.id), "number": row.revision_no, "date": row.revision_date.isoformat(),
             "description": row.description, "published_at": row.published_at.isoformat(),
             "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
             "delete_reason": row.delete_reason,
             "completion_mode": "full_test" if row.id in tests else "acknowledge",
             "test_id": str(tests[row.id]) if row.id in tests else None} for row in rows]


@router.get("/admin/revisions/assignable")
def assignable_revisions(db: Session = Depends(get_db), _actor: Employee = Depends(require_role("teacher"))):
    rows = db.execute(select(ArticleRevision, Article).join(Article, Article.id == ArticleRevision.article_id)
        .where(Article.owner_course_id.is_(None), ArticleRevision.deleted_at.is_(None))
        .order_by(ArticleRevision.published_at.desc())).all()
    return [{"id": str(revision.id), "article_title": article.title,
             "number": revision.revision_no, "date": revision.revision_date.isoformat()}
            for revision, article in rows]


@router.post("/admin/knowledge/articles/{article_id}/revisions", status_code=201)
def publish_revision(article_id: uuid.UUID, payload: PublishRevision, db: Session = Depends(get_db), actor: Employee = Depends(require_role("editor"))):
    article = db.scalar(select(Article).where(Article.id == article_id, Article.owner_course_id.is_(None)).with_for_update())
    if article is None:
        raise HTTPException(404)
    if article.row_version != payload.row_version:
        raise HTTPException(409, "Article changed; reload before publishing")
    description = payload.description.strip()
    if not description:
        raise HTTPException(422, "Description is required")
    if db.scalar(select(ArticleRevision.id).where(ArticleRevision.article_id == article_id,
                                                   ArticleRevision.revision_date == payload.revision_date)):
        raise HTTPException(409, "Revision date already exists")
    try:
        snapshot = snapshot_google_nodes(article.body)
    except GoogleReadError as exc:
        raise HTTPException(409, "Google document snapshot is unavailable") from exc
    source_test = db.get(TestDefinition, payload.copy_test_id) if payload.copy_test_id else None
    if payload.copy_test_id and (payload.completion_mode != "full_test" or source_test is None
            or source_test.article_revision_id is None):
        raise HTTPException(422, "Choose a revision test to copy")
    if source_test:
        source_revision = db.get(ArticleRevision, source_test.article_revision_id)
        if source_revision is None or source_revision.article_id != article_id:
            raise HTTPException(422, "Test belongs to another article")
    last = db.scalar(select(ArticleRevision.revision_no).where(ArticleRevision.article_id == article_id)
        .order_by(ArticleRevision.revision_no.desc()).limit(1)) or 0
    revision = ArticleRevision(article_id=article_id, revision_no=last + 1,
        revision_date=payload.revision_date, description=description,
        body_snapshot=snapshot, published_at=datetime.now(timezone.utc))
    db.add(revision)
    db.flush()
    test = None
    if payload.completion_mode == "full_test":
        test = clone_test_content(db, source_test, actor, article_revision_id=revision.id) if source_test else TestDefinition(
            article_revision_id=revision.id, title=f"Тест редакции № {revision.revision_no}: {article.title}",
            created_by=actor.id)
        db.add(test)
    db.commit()
    return {"id": str(revision.id), "number": revision.revision_no,
            "date": revision.revision_date.isoformat(), "description": revision.description,
            "completion_mode": payload.completion_mode, "test_id": str(test.id) if test else None}


@router.post("/admin/knowledge/articles/{article_id}/revisions/{revision_id}/withdraw")
def withdraw_revision(article_id: uuid.UUID, revision_id: uuid.UUID, payload: WithdrawRevision,
                      db: Session = Depends(get_db), actor: Employee = Depends(require_role("admin"))):
    if not payload.confirmed:
        raise HTTPException(422, "Confirm revision withdrawal")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(422, "Reason is required")
    revision = db.scalar(select(ArticleRevision).where(ArticleRevision.id == revision_id,
        ArticleRevision.article_id == article_id).with_for_update())
    if revision is None:
        raise HTTPException(404)
    if revision.deleted_at is not None:
        raise HTTPException(409, "Revision already withdrawn")
    revision.deleted_at = datetime.now(timezone.utc)
    revision.deleted_by = actor.id
    revision.delete_reason = reason
    db.commit()
    return {"id": str(revision.id), "deleted_at": revision.deleted_at.isoformat(),
            "delete_reason": revision.delete_reason}


@router.post("/admin/knowledge/grants", status_code=201)
def add_grant(payload: AccessGrant, db: Session = Depends(get_db), actor: Employee = Depends(require_role("admin"))):
    if payload.target_type == "folder":
        if db.get(KnowledgeFolder, payload.target_id) is None:
            raise HTTPException(404)
    elif db.get(FolderArticle, payload.target_id) is None:
        raise HTTPException(404)
    try:
        bitrix_id = int(payload.subject_id)
    except ValueError as exc:
        raise HTTPException(422, "Invalid Bitrix ID") from exc
    if bitrix_id <= 0:
        raise HTTPException(422, "Invalid Bitrix ID")
    if payload.subject_type == "employee":
        if db.scalar(select(Employee.id).where(Employee.bitrix_id == bitrix_id)) is None:
            raise HTTPException(404)
    elif db.get(Department, bitrix_id) is None:
        raise HTTPException(404, "Department is not synchronized")
    existing = db.scalar(select(KnowledgeGrant).where(KnowledgeGrant.target_type == payload.target_type,
        KnowledgeGrant.target_id == payload.target_id, KnowledgeGrant.subject_type == payload.subject_type,
        KnowledgeGrant.subject_id == payload.subject_id))
    if existing:
        return {"id": str(existing.id)}
    grant = KnowledgeGrant(target_type=payload.target_type, target_id=payload.target_id,
        subject_type=payload.subject_type, subject_id=payload.subject_id, granted_by=actor.id)
    db.add(grant)
    db.commit()
    return {"id": str(grant.id)}
