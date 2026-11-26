import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import Article, ArticleRevision, BrowserSession, Employee, FolderArticle, KnowledgeFolder, KnowledgeGrant


def test_revision_withdrawal_retains_snapshot_and_requires_admin_reason():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    tokens = {role: f"withdraw-{marker}-{role}" for role in ("admin", "editor", "learner")}
    ids = []
    with SessionLocal() as db:
        for index, role in enumerate(tokens):
            person = Employee(bitrix_id=1_380_000_000 + marker * 3 + index,
                first_name="Revision", last_name=role,
                local_role=role if role != "learner" else "employee")
            db.add(person)
            db.flush()
            ids.append(person.id)
            db.add(BrowserSession(token_hash=hashlib.sha256(tokens[role].encode()).hexdigest(),
                employee_id=person.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    client = TestClient(app)
    headers = {role: {"Cookie": f"rtm_next_session={token}"} for role, token in tokens.items()}
    folder_id = article_id = revision_id = None
    try:
        folder = client.post("/admin/knowledge/folders", headers=headers["admin"], json={"title": "Withdrawal"})
        assert folder.status_code == 201, folder.text
        folder_id = uuid.UUID(folder.json()["id"])
        article = client.post("/admin/knowledge/articles", headers=headers["editor"], json={
            "title": "Historical article", "folder_id": str(folder_id)})
        assert article.status_code == 201, article.text
        article_id = uuid.UUID(article.json()["id"])
        body = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "Evidence retained"}]}]}
        assert client.put(f"/admin/knowledge/articles/{article_id}", headers=headers["editor"], json={
            "title": "Historical article", "summary": "", "body": body, "row_version": 1}).status_code == 200
        published = client.post(f"/admin/knowledge/articles/{article_id}/revisions",
            headers=headers["editor"], json={"revision_date": date.today().isoformat(),
                "description": "Baseline", "row_version": 2})
        assert published.status_code == 201, published.text
        revision_id = uuid.UUID(published.json()["id"])
        path = f"/admin/knowledge/articles/{article_id}/revisions/{revision_id}/withdraw"
        assert client.post(path, headers=headers["editor"], json={
            "reason": "Incorrect publication", "confirmed": True}).status_code == 403
        assert client.post(path, headers=headers["admin"], json={
            "reason": "Incorrect publication", "confirmed": False}).status_code == 422
        assert client.post(path, headers=headers["admin"], json={
            "reason": " ", "confirmed": True}).status_code == 422
        result = client.post(path, headers=headers["admin"], json={
            "reason": "Incorrect publication", "confirmed": True})
        assert result.status_code == 200, result.text
        assert result.json()["delete_reason"] == "Incorrect publication"
        assert client.post(path, headers=headers["admin"], json={
            "reason": "Again", "confirmed": True}).status_code == 409
        listing = client.get(f"/admin/knowledge/articles/{article_id}/revisions", headers=headers["editor"])
        assert listing.json()[0]["deleted_at"] is not None
        assert revision_id not in {uuid.UUID(row["id"]) for row in
            client.get("/admin/revisions/assignable", headers=headers["admin"]).json()}
        with SessionLocal() as db:
            retained = db.get(ArticleRevision, revision_id)
            assert retained.body_snapshot == body
            assert retained.deleted_by == ids[0]
    finally:
        with SessionLocal() as db:
            if revision_id:
                db.execute(delete(ArticleRevision).where(ArticleRevision.id == revision_id))
            if article_id:
                db.execute(delete(KnowledgeGrant).where(KnowledgeGrant.target_id == article_id))
                db.execute(delete(FolderArticle).where(FolderArticle.article_id == article_id))
                db.execute(delete(Article).where(Article.id == article_id))
            if folder_id:
                db.execute(delete(KnowledgeFolder).where(KnowledgeFolder.id == folder_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids)))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.commit()
