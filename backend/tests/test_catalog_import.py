import uuid
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.catalog_import import SHEET_GID, classify_rows
from app.db import SessionLocal
from app.main import app
from app.models import Article, BrowserSession, Employee, FolderArticle, KnowledgeFolder


def cell(value="", *, bold=False, color=None):
    result = {"formattedValue": value, "effectiveFormat": {"textFormat": {"bold": bold}}}
    if color:
        result["effectiveFormat"]["backgroundColor"] = dict(zip(("red", "green", "blue"), color))
    return result


def row(title, url="", *, bold=False, color=None, description=""):
    cells = [cell() for _ in range(11)]
    cells[1] = cell(title, bold=bold, color=color)
    cells[2] = cell(description)
    cells[6] = cell(url)
    return {"values": cells}


def test_catalog_hierarchy_google_links_and_skipped_rows():
    grid = {"sheets": [{"properties": {"sheetId": SHEET_GID}, "data": [{"startRow": 0, "rowData": [
        row("Заголовок"),
        row("Корневая", bold=True, color=(.85, .85, .85)),
        row("Вложенная", bold=True, color=(201 / 255, 218 / 255, 248 / 255)),
        row("Третий уровень", bold=True),
        row("Без ссылки"),
        row("Документ", "https://docs.google.com/document/d/abcdefgh123/edit", description="Описание"),
        row("Внешний", "https://example.org/read"),
    ]}]}]}
    records, warnings = classify_rows(grid)
    assert not warnings
    assert [item["kind"] for item in records] == ["folder"] * 3 + ["article"] * 2
    assert records[1]["parent_id"] == records[0]["id"]
    assert records[2]["parent_id"] == records[1]["id"]
    assert records[3]["folder_id"] == records[2]["id"]
    assert records[3]["summary"] == "Описание"
    assert records[3]["body"]["content"][0]["attrs"]["fileId"] == "abcdefgh123"
    assert records[4]["source_type"] == "paragraph"
    assert records[4]["id"] == uuid.uuid5(uuid.UUID("13bdde43-076b-48d8-b2e5-c7d188462a80"),
                                            "1NyZ3tC82_iWDsh3Y8UMtcpM5HXa6Ge13bBjI7UJ_7Xw:article:7")


def test_catalog_rejects_non_https_values_and_orphans():
    grid = {"sheets": [{"properties": {"sheetId": SHEET_GID}, "data": [{"startRow": 0, "rowData": [
        row("Заголовок"), row("Без папки", "https://example.org"),
        row("Синяя папка", bold=True, color=(201 / 255, 218 / 255, 248 / 255)),
        row("Корневая", bold=True, color=(.85, .85, .85)),
        row("Не ссылка", "см. комментарий"),
    ]}]}]}
    records, warnings = classify_rows(grid)
    assert [item["kind"] for item in records] == ["folder"]
    assert [item["row"] for item in warnings] == [2, 3, 5]


def test_import_preview_permission_confirmation_and_idempotency(monkeypatch):
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    admin_token, learner_token = f"catalog-admin-{marker}", f"catalog-learner-{marker}"
    with SessionLocal() as db:
        admin = Employee(bitrix_id=1_700_000_000 + marker, first_name="Catalog", last_name="Admin", local_role="admin")
        learner = Employee(bitrix_id=1_800_000_000 + marker, first_name="Catalog", last_name="Learner")
        db.add_all([admin, learner]); db.flush()
        employee_ids = [admin.id, learner.id]
        for token, employee in ((admin_token, admin), (learner_token, learner)):
            db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=employee.id,
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    row_key = f"test-{uuid.uuid4()}"
    folder_id, article_id = uuid.uuid5(uuid.NAMESPACE_URL, row_key + "-folder"), uuid.uuid5(uuid.NAMESPACE_URL, row_key + "-article")
    records = [
        {"kind": "folder", "row": 2, "id": folder_id, "parent_id": None, "title": "Imported", "description": ""},
        {"kind": "article", "row": 3, "id": article_id, "folder_id": folder_id, "title": "Imported document",
         "summary": "Description", "body": {"type": "doc", "content": [{"type": "paragraph"}]},
         "source_type": "google_document"},
    ]
    monkeypatch.setattr("app.knowledge.read_catalog", lambda: (records, []))
    client = TestClient(app)
    admin_headers = {"Cookie": f"rtm_next_session={admin_token}"}
    learner_headers = {"Cookie": f"rtm_next_session={learner_token}"}
    try:
        assert client.get("/admin/knowledge/catalog-import/preview", headers=learner_headers).status_code == 403
        assert client.post("/admin/knowledge/catalog-import", headers=learner_headers,
                           json={"confirmed": True}).status_code == 403
        preview = client.get("/admin/knowledge/catalog-import/preview", headers=admin_headers)
        assert preview.status_code == 200, preview.text
        assert (preview.json()["new_folders"], preview.json()["new_articles"]) == (1, 1)
        assert client.post("/admin/knowledge/catalog-import", headers=admin_headers,
                           json={"confirmed": False}).status_code == 400
        created = client.post("/admin/knowledge/catalog-import", headers=admin_headers,
                              json={"confirmed": True})
        assert created.status_code == 200, created.text
        assert created.json()["folders"] == created.json()["articles"] == 1
        with SessionLocal() as db:
            db.get(Article, article_id).summary = "Edited after import"
            db.commit()
        repeated = client.post("/admin/knowledge/catalog-import", headers=admin_headers,
                               json={"confirmed": True})
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["folders"] == repeated.json()["articles"] == 0
        with SessionLocal() as db:
            assert db.get(Article, article_id).summary == "Edited after import"
        assert client.get("/knowledge/articles/" + str(article_id), headers=learner_headers).status_code == 404
    finally:
        with SessionLocal() as db:
            db.execute(delete(FolderArticle).where(FolderArticle.article_id == article_id))
            db.execute(delete(Article).where(Article.id == article_id))
            db.execute(delete(KnowledgeFolder).where(KnowledgeFolder.id == folder_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(employee_ids)))
            db.execute(delete(Employee).where(Employee.id.in_(employee_ids)))
            db.commit()
