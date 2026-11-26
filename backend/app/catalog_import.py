"""One-time, idempotent import of the approved document catalog."""

import re
import uuid
from urllib.parse import quote, urlparse

from sqlalchemy.orm import Session

from app.google_documents import request_google_json
from app.models import Article, FolderArticle, KnowledgeFolder

SHEET_ID = "1NyZ3tC82_iWDsh3Y8UMtcpM5HXa6Ge13bBjI7UJ_7Xw"
SHEET_NAME = "Каталог документов"
SHEET_GID = 230795919
NAMESPACE = uuid.UUID("13bdde43-076b-48d8-b2e5-c7d188462a80")
GOOGLE_LINK = re.compile(r"^https://docs\.google\.com/(document|spreadsheets)/d/([A-Za-z0-9_-]+)")
URL = re.compile(r"https://[^\s]+")


def _value(cells: list[dict], column: int) -> str:
    return str(cells[column].get("formattedValue", "")).strip() if len(cells) > column else ""


def _link(cells: list[dict], column: int) -> str:
    if len(cells) <= column:
        return ""
    cell = cells[column]
    return str(cell.get("hyperlink") or cell.get("formattedValue") or "").strip()


def _color(cell: dict) -> tuple[int, int, int] | None:
    color = cell.get("effectiveFormat", {}).get("backgroundColor")
    if not isinstance(color, dict):
        return None
    return tuple(round(float(color.get(key, 0)) * 255) for key in ("red", "green", "blue"))


def classify_rows(grid: dict) -> tuple[list[dict], list[dict]]:
    """Return folder/article records and exceptions, preserving sheet row numbers."""
    sheet = next((item for item in grid.get("sheets", [])
                  if item.get("properties", {}).get("sheetId") == SHEET_GID), None)
    if sheet is None:
        raise ValueError("Каталог документов: нужный лист не найден")
    records: list[dict] = []
    warnings: list[dict] = []
    ancestors: dict[int, uuid.UUID] = {}
    data = sheet.get("data", [{}])[0]
    for index, row in enumerate(data.get("rowData", []), start=int(data.get("startRow", 0)) + 1):
        if index == 1:
            continue
        cells = row.get("values", [])
        title = _value(cells, 1)[:240]
        if not title:
            continue
        primary, google = _link(cells, 6), _link(cells, 7)
        raw_link = google or primary
        # A cell may contain two pasted URLs; the Google document takes precedence.
        matches = URL.findall(f"{google}\n{primary}")
        selected = next((link for link in matches if GOOGLE_LINK.match(link)), None)
        selected = selected or (matches[0] if matches else "")
        bold = bool(cells[1].get("effectiveFormat", {}).get("textFormat", {}).get("bold")) if len(cells) > 1 else False
        if not raw_link and bold:
            color = _color(cells[1])
            depth = 1 if color == (217, 217, 217) else 2 if color == (201, 218, 248) else 3
            parent = ancestors.get(depth - 1) if depth > 1 else None
            if depth > 1 and parent is None:
                warnings.append({"row": index, "reason": "Папка без родительской папки"})
                continue
            folder_id = uuid.uuid5(NAMESPACE, f"{SHEET_ID}:folder:{index}")
            records.append({"kind": "folder", "row": index, "id": folder_id, "parent_id": parent,
                            "title": title, "description": _value(cells, 2)})
            ancestors[depth] = folder_id
            for level in range(depth + 1, 4):
                ancestors.pop(level, None)
            continue
        if not raw_link:
            continue
        parsed = urlparse(selected)
        if parsed.scheme != "https" or not parsed.hostname or not selected:
            warnings.append({"row": index, "reason": "Ссылка не является HTTPS URL"})
            continue
        parent = ancestors.get(3) or ancestors.get(2) or ancestors.get(1)
        if parent is None:
            warnings.append({"row": index, "reason": "Статья без папки"})
            continue
        match = GOOGLE_LINK.match(selected)
        if match:
            node = {"type": "google_document" if match.group(1) == "document" else "google_spreadsheet",
                    "attrs": {"fileId": match.group(2), "sourceUrl": selected, "snapshot": None}}
        else:
            node = {"type": "paragraph", "content": [{"type": "text", "text": "Открыть источник",
                    "marks": [{"type": "link", "attrs": {"href": selected, "target": "_blank", "rel": "noopener noreferrer"}}]}]}
        records.append({"kind": "article", "row": index,
                        "id": uuid.uuid5(NAMESPACE, f"{SHEET_ID}:article:{index}"),
                        "folder_id": parent, "title": title, "summary": _value(cells, 2)[:20000],
                        "body": {"type": "doc", "content": [node]}, "source_type": node["type"]})
    return records, warnings


def read_catalog() -> tuple[list[dict], list[dict]]:
    fields = "sheets(properties(sheetId,title),data(startRow,rowData(values(formattedValue,hyperlink,effectiveFormat(textFormat(bold),backgroundColor)))))"
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?includeGridData=true&ranges="
    url += quote(f"'{SHEET_NAME}'!A1:K600", safe="") + "&fields=" + quote(fields, safe="(),")
    return classify_rows(request_google_json(SHEET_ID, url))


def preview(db: Session, records: list[dict], warnings: list[dict]) -> dict:
    existing_folders = {row.id for row in db.query(KnowledgeFolder.id).all()}
    existing_articles = {row.id for row in db.query(Article.id).all()}
    return {"folders": sum(row["kind"] == "folder" for row in records),
            "articles": sum(row["kind"] == "article" for row in records),
            "new_folders": sum(row["kind"] == "folder" and row["id"] not in existing_folders for row in records),
            "new_articles": sum(row["kind"] == "article" and row["id"] not in existing_articles for row in records),
            "external_links": [row["row"] for row in records if row.get("source_type") == "paragraph"],
            "warnings": warnings}


def apply(db: Session, records: list[dict], actor_id: uuid.UUID) -> dict:
    # All rows are inserted in one transaction. Existing IDs are left untouched so
    # a rerun cannot overwrite editorial changes made after the first import.
    existing_folders = {row.id for row in db.query(KnowledgeFolder.id).all()}
    existing_articles = {row.id for row in db.query(Article.id).all()}
    created = {"folders": 0, "articles": 0}
    for row in records:
        if row["kind"] == "folder" and row["id"] not in existing_folders:
            db.add(KnowledgeFolder(id=row["id"], parent_id=row["parent_id"], title=row["title"],
                                   description=row["description"]))
            created["folders"] += 1
    db.flush()
    for row in records:
        if row["kind"] == "article" and row["id"] not in existing_articles:
            db.add(Article(id=row["id"], title=row["title"], summary=row["summary"],
                           body=row["body"], created_by=actor_id))
            db.add(FolderArticle(article_id=row["id"], folder_id=row["folder_id"]))
            created["articles"] += 1
    db.commit()
    return created
