"""Plan and apply the one-time RTM Google Sheets catalogue import.

The source snapshot is private and supplied separately from the release. Imported
articles start without ACL grants, so only administrators can see them until the
knowledge-base owner explicitly grants access.
"""

import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Article, Employee, FolderArticle, KnowledgeFolder

SOURCE_SHEET = "1NyZ3tC82_iWDsh3Y8UMtcpM5HXa6Ge13bBjI7UJ_7Xw"
SOURCE_TAB = 230795919
IMPORT_NAMESPACE = uuid.UUID("23c78a6e-7e61-4b3c-b3a5-5f840a6ebac1")
GOOGLE_ID = re.compile(r"^/(document|spreadsheets)/d/([A-Za-z0-9_-]+)(?:/|$)")


@dataclass(frozen=True)
class PlannedFolder:
    id: uuid.UUID
    row: int
    title: str
    parent_id: uuid.UUID | None


@dataclass(frozen=True)
class PlannedArticle:
    id: uuid.UUID
    row: int
    title: str
    description: str
    folder_id: uuid.UUID
    source_kind: str
    google_file_id: str
    source_url: str


@dataclass(frozen=True)
class ImportPlan:
    folders: list[PlannedFolder]
    articles: list[PlannedArticle]
    skipped: list[dict]


def stable_id(kind: str, sheet_id: str, tab_id: int, row: int) -> uuid.UUID:
    return uuid.uuid5(IMPORT_NAMESPACE, f"{kind}:{sheet_id}:{tab_id}:{row}")


def google_source(value: str) -> tuple[str, str, str] | None:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname != "docs.google.com":
        return None
    match = GOOGLE_ID.match(parsed.path)
    if not match:
        return None
    kind, file_id = match.groups()
    return kind, file_id, f"https://docs.google.com/{kind}/d/{file_id}/edit"


def plan_catalog(snapshot: dict) -> ImportPlan:
    if snapshot.get("source_spreadsheet_id") != SOURCE_SHEET or snapshot.get("sheet_id") != SOURCE_TAB:
        raise ValueError("Unexpected source spreadsheet or tab")
    folders: list[PlannedFolder] = []
    articles: list[PlannedArticle] = []
    skipped: list[dict] = []
    stack: dict[int, PlannedFolder] = {}
    obsolete = False
    seen_rows: set[int] = set()
    for source in sorted(snapshot.get("rows", []), key=lambda item: item["row"]):
        row = source["row"]
        if not isinstance(row, int) or row < 2 or row in seen_rows:
            raise ValueError("Invalid or duplicated source row")
        seen_rows.add(row)
        title = str(source.get("title", "")).strip()
        if not title:
            continue
        description = str(source.get("description", "")).strip()
        link_values = [str(source.get("google_url", "")).strip(), str(source.get("primary_url", "")).strip()]
        links = [google_source(value) for value in link_values if value]
        source_link = next((link for link in links if link is not None), None)
        is_heading = bool(source.get("bold")) and not description and not any(link_values)
        color = source.get("color")
        if is_heading:
            if title.upper() == "НЕАКТУАЛЬНЫЕ":
                obsolete = True
                skipped.append({"row": row, "reason": "obsolete_section"})
                continue
            if color == "217,217,217":
                level = 0
            elif color == "201,218,248":
                level = 1
            else:
                level = 2
            if obsolete and level <= 1:
                obsolete = False
            if obsolete:
                skipped.append({"row": row, "reason": "obsolete_section"})
                continue
            parent = stack.get(level - 1) if level else None
            if level and parent is None:
                skipped.append({"row": row, "reason": "missing_parent_folder"})
                continue
            folder = PlannedFolder(stable_id("folder", SOURCE_SHEET, SOURCE_TAB, row), row, title,
                                   parent.id if parent else None)
            folders.append(folder)
            stack[level] = folder
            for key in list(stack):
                if key > level:
                    del stack[key]
            continue
        if obsolete:
            skipped.append({"row": row, "reason": "obsolete_section"})
        elif source_link is None:
            skipped.append({"row": row, "reason": "no_google_document_link"})
        elif not stack:
            skipped.append({"row": row, "reason": "missing_parent_folder"})
        else:
            kind, file_id, canonical = source_link
            folder = stack[max(stack)]
            articles.append(PlannedArticle(stable_id("article", SOURCE_SHEET, SOURCE_TAB, row),
                row, title, description, folder.id, kind, file_id, canonical))
    return ImportPlan(folders, articles, skipped)


def apply_catalog(db: Session, plan: ImportPlan, actor: Employee) -> dict[str, int]:
    """Insert only missing records; never overwrite subsequent RTM edits or ACLs."""
    created_folders = created_articles = 0
    for folder in plan.folders:
        if db.get(KnowledgeFolder, folder.id) is None:
            db.add(KnowledgeFolder(id=folder.id, parent_id=folder.parent_id, title=folder.title))
            db.flush()
            created_folders += 1
    for entry in plan.articles:
        if db.get(Article, entry.id) is not None:
            continue
        node_type = "google_document" if entry.source_kind == "document" else "google_spreadsheet"
        body = {"type": "doc", "content": [{"type": node_type, "attrs": {
            "fileId": entry.google_file_id, "sourceUrl": entry.source_url}}]}
        db.add(Article(id=entry.id, title=entry.title, summary=entry.description,
                       body=body, created_by=actor.id))
        db.add(FolderArticle(article_id=entry.id, folder_id=entry.folder_id))
        created_articles += 1
    db.commit()
    return {"folders_created": created_folders, "articles_created": created_articles,
            "skipped": len(plan.skipped)}
