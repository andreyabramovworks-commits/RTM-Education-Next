"""Server-side Google Docs reading and compact historical snapshots."""

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from google.auth import load_credentials_from_file
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest


GOOGLE_CREDENTIALS_FILE = Path(os.environ.get("GOOGLE_CREDENTIALS_FILE", "/data/google-credentials.json"))
DOC_SCOPE = "https://www.googleapis.com/auth/documents.readonly"
SHEET_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
FILE_ID = re.compile(r"^[A-Za-z0-9_-]{8,200}$")
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_SHEET_CELLS = 100_000


class GoogleReadError(Exception):
    pass


def credentials_ready() -> bool:
    return GOOGLE_CREDENTIALS_FILE.is_file()


def request_google_json(file_id: str, url: str) -> dict:
    if not FILE_ID.fullmatch(file_id):
        raise GoogleReadError("INVALID_DOCUMENT_ID")
    if not credentials_ready():
        raise GoogleReadError("GOOGLE_CREDENTIALS_UNAVAILABLE")
    try:
        credentials, _ = load_credentials_from_file(str(GOOGLE_CREDENTIALS_FILE), scopes=[DOC_SCOPE, SHEET_SCOPE])
        credentials.refresh(GoogleRequest())
        request = Request(url,
                          headers={"Authorization": f"Bearer {credentials.token}", "Accept": "application/json"})
        with urlopen(request, timeout=15) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GoogleReadError("GOOGLE_DOCUMENT_TOO_LARGE")
        return json.loads(raw)
    except (GoogleAuthError, OSError, ValueError, HTTPError, URLError, TimeoutError) as exc:
        raise GoogleReadError("GOOGLE_DOCUMENT_UNAVAILABLE") from exc


def read_document(file_id: str) -> dict:
    document = request_google_json(file_id, f"https://docs.googleapis.com/v1/documents/{file_id}?includeTabsContent=true")
    blocks = document_blocks(document)
    text = "\n".join(block_text(block) for block in blocks).strip()
    if not blocks or not text:
        raise GoogleReadError("GOOGLE_DOCUMENT_EMPTY")
    return {"file_id": file_id, "title": str(document.get("title", ""))[:240],
            "revision_id": str(document.get("revisionId", ""))[:240],
            "blocks": blocks, "text": text,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(text.encode()).hexdigest()}


def read_spreadsheet(file_id: str) -> dict:
    metadata = request_google_json(file_id, f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}?" +
        urlencode({"fields": "properties(title),sheets(properties(title,gridProperties(rowCount,columnCount)))"}))
    sheets = metadata.get("sheets", [])
    if not sheets:
        raise GoogleReadError("GOOGLE_SHEET_EMPTY")
    estimated_cells = sum(int(sheet.get("properties", {}).get("gridProperties", {}).get("rowCount", 0)) *
                          int(sheet.get("properties", {}).get("gridProperties", {}).get("columnCount", 0))
                          for sheet in sheets)
    if estimated_cells > MAX_SHEET_CELLS:
        raise GoogleReadError("GOOGLE_SHEET_TOO_LARGE")
    blocks = []
    for sheet in sheets:
        title = str(sheet.get("properties", {}).get("title", ""))
        if not title:
            continue
        a1 = "'" + title.replace("'", "''") + "'"
        values = request_google_json(file_id, f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}/values/{quote(a1, safe='')}?" +
            urlencode({"valueRenderOption": "FORMATTED_VALUE"})).get("values", [])
        rows = [[str(cell) for cell in row] for row in values]
        blocks.append({"type": "sheet", "title": title, "rows": rows})
    text = "\n".join(block["title"] + "\n" + "\n".join("\t".join(row) for row in block["rows"])
                     for block in blocks).strip()
    if not text:
        raise GoogleReadError("GOOGLE_SHEET_EMPTY")
    return {"file_id": file_id, "title": str(metadata.get("properties", {}).get("title", ""))[:240],
            "revision_id": "", "blocks": blocks, "text": text,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(text.encode()).hexdigest()}


def block_text(block: dict) -> str:
    if block["type"] == "table":
        return "\n".join("\t".join(cell for cell in row) for row in block["rows"])
    return block["text"]


def content_text(elements: list[dict]) -> str:
    return "\n".join(block_text(block) for block in structural_blocks(elements)).strip()


def structural_blocks(elements: list[dict]) -> list[dict]:
    result = []
    for element in elements:
        paragraph = element.get("paragraph")
        if paragraph is not None:
            text = "".join(item.get("textRun", {}).get("content", "") for item in paragraph.get("elements", [])).strip()
            if text:
                result.append({"type": "paragraph", "style": paragraph.get("paragraphStyle", {}).get(
                    "namedStyleType", "NORMAL_TEXT"), "text": text})
        table = element.get("table")
        if table is not None:
            rows = [[content_text(cell.get("content", [])) for cell in row.get("tableCells", [])]
                    for row in table.get("tableRows", [])]
            if rows:
                result.append({"type": "table", "rows": rows})
        toc = element.get("tableOfContents")
        if toc is not None:
            result.extend(structural_blocks(toc.get("content", [])))
    return result


def document_blocks(document: dict) -> list[dict]:
    result = []

    def tabs(items: list[dict]) -> None:
        for tab in items:
            result.extend(structural_blocks(tab.get("documentTab", {}).get("body", {}).get("content", [])))
            tabs(tab.get("childTabs", []))

    if document.get("tabs"):
        tabs(document["tabs"])
    else:
        result.extend(structural_blocks(document.get("body", {}).get("content", [])))
    return result


def snapshot_google_nodes(body: dict) -> dict:
    snapshot = deepcopy(body)

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "google_document":
                attrs = value.get("attrs")
                if not isinstance(attrs, dict) or not isinstance(attrs.get("fileId"), str):
                    raise GoogleReadError("INVALID_DOCUMENT_ID")
                data = read_document(attrs["fileId"])
                attrs["snapshot"] = {key: data[key] for key in ("file_id", "revision_id", "text", "fetched_at", "sha256")}
            elif value.get("type") == "google_spreadsheet":
                attrs = value.get("attrs")
                if not isinstance(attrs, dict) or not isinstance(attrs.get("fileId"), str):
                    raise GoogleReadError("INVALID_DOCUMENT_ID")
                data = read_spreadsheet(attrs["fileId"])
                attrs["snapshot"] = {key: data[key] for key in ("file_id", "revision_id", "text", "fetched_at", "sha256")}
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(snapshot)
    return snapshot
