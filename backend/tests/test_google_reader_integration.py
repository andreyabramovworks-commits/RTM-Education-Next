import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import Article, BrowserSession, Employee, FolderArticle, KnowledgeFolder, KnowledgeGrant


def test_google_reader_checks_article_acl_before_fetch(monkeypatch):
    assert SessionLocal is not None
    marker = uuid.uuid4().hex
    token = f"google-reader-{marker}"
    called = []
    monkeypatch.setattr("app.google_reader.read_document", lambda file_id: called.append(file_id) or {
        "title": "Private document", "revision_id": "rev-1", "blocks": [{"type": "paragraph", "text": "Content"}],
        "fetched_at": "2026-11-26T00:00:00Z"})
    with SessionLocal() as db:
        admin = Employee(bitrix_id=1_500_000_000 + int(marker[:6], 16), first_name="Test", last_name="Admin", bitrix_admin=True)
        reader = Employee(bitrix_id=1_600_000_000 + int(marker[:6], 16), first_name="Test", last_name="Reader")
        db.add_all([admin, reader]); db.flush()
        folder = KnowledgeFolder(title="Private")
        db.add(folder); db.flush()
        article = Article(title="A", body={"type": "doc", "content": [{"type": "google_document", "attrs": {
            "fileId": "source12345", "sourceUrl": "https://docs.google.com/document/d/source12345/edit"}}]},
            created_by=admin.id)
        db.add(article); db.flush()
        db.add(FolderArticle(article_id=article.id, folder_id=folder.id))
        db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=reader.id,
                              expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
        ids = (admin.id, reader.id, folder.id, article.id)
        reader_bitrix_id = reader.bitrix_id
    try:
        client = TestClient(app)
        headers = {"Cookie": f"rtm_next_session={token}"}
        endpoint = f"/google/articles/{ids[3]}/documents/source12345"
        assert client.get(endpoint, headers=headers).status_code == 404
        assert client.get(f"/google/articles/{ids[3]}/documents/other12345", headers=headers).status_code == 404
        assert called == []
        assert client.get("/google/admin/sources", headers=headers).status_code == 403
        with SessionLocal() as db:
            db.add(KnowledgeGrant(target_type="article", target_id=ids[3], subject_type="employee",
                                  subject_id=str(reader_bitrix_id), granted_by=ids[0]))
            db.commit()
        response = client.get(endpoint, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["blocks"][0]["text"] == "Content"
        assert called == ["source12345"]
    finally:
        with SessionLocal() as db:
            db.execute(delete(KnowledgeGrant).where(KnowledgeGrant.target_id == ids[3]))
            db.execute(delete(FolderArticle).where(FolderArticle.article_id == ids[3]))
            db.execute(delete(Article).where(Article.id == ids[3]))
            db.execute(delete(KnowledgeFolder).where(KnowledgeFolder.id == ids[2]))
            db.execute(delete(BrowserSession).where(BrowserSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
            db.execute(delete(Employee).where(Employee.id.in_(ids[:2])))
            db.commit()
