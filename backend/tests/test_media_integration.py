import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import Article, BrowserSession, Employee, FolderArticle, KnowledgeFolder, KnowledgeGrant, MediaAsset


def test_private_uploaded_audio_requires_article_access():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    tokens = {name: f"media-{marker}-{name}" for name in ("admin", "learner", "other")}
    ids = []
    bitrix_ids = {}
    with SessionLocal() as db:
        for index, name in enumerate(tokens):
            person = Employee(bitrix_id=1_350_000_000 + marker * 3 + index,
                first_name="Test", last_name=name, local_role="admin" if name == "admin" else "employee")
            db.add(person)
            db.flush()
            ids.append(person.id)
            bitrix_ids[name] = person.bitrix_id
            db.add(BrowserSession(token_hash=hashlib.sha256(tokens[name].encode()).hexdigest(),
                employee_id=person.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    client = TestClient(app)
    headers = {name: {"Cookie": f"rtm_next_session={token}"} for name, token in tokens.items()}
    folder_id = article_id = asset_id = rutube_id = None
    try:
        folder = client.post("/admin/knowledge/folders", headers=headers["admin"], json={"title": "Media"})
        folder_id = uuid.UUID(folder.json()["id"])
        article = client.post("/admin/knowledge/articles", headers=headers["admin"], json={
            "title": "Audio article", "folder_id": str(folder_id)})
        article_id = uuid.UUID(article.json()["id"])
        fake_mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"audio test data"
        upload = client.post("/admin/media/upload", headers=headers["admin"], data={"kind": "audio"},
            files={"file": ("lesson.mp3", fake_mp3, "audio/mpeg")})
        assert upload.status_code == 201, upload.text
        asset_id = uuid.UUID(upload.json()["id"])
        body = {"type": "doc", "content": [{"type": "mediaEmbed", "attrs": {"assetId": str(asset_id)}}]}
        assert client.put(f"/admin/knowledge/articles/{article_id}", headers=headers["admin"], json={
            "title": "Audio article", "summary": "", "body": body, "row_version": 1}).status_code == 200
        assert client.get(f"/media/{asset_id}", headers=headers["learner"]).status_code == 404
        assert client.post("/admin/knowledge/grants", headers=headers["admin"], json={
            "target_type": "article", "target_id": str(article_id),
            "subject_type": "employee", "subject_id": str(bitrix_ids["learner"])}).status_code == 201
        assert client.get(f"/media/{asset_id}", headers=headers["other"]).status_code == 404
        info = client.get(f"/media/{asset_id}/info", headers=headers["learner"])
        assert info.status_code == 200 and info.json()["kind"] == "audio"
        stream = client.get(f"/media/{asset_id}", headers=headers["learner"])
        assert stream.status_code == 200 and stream.content == fake_mp3
        assert client.post("/admin/media/rutube", headers=headers["admin"], json={
            "url": "https://evil.example/video/123", "title": "Bad"}).status_code == 422
        private = client.post("/admin/media/rutube", headers=headers["admin"], json={
            "url": "https://rutube.ru/video/private/aabbccddeeff00112233445566778899/?p=sampleKey123456789",
            "title": "Private demo"})
        assert private.status_code == 201, private.text
        rutube_id = uuid.UUID(private.json()["id"])
        body["content"].append({"type": "mediaEmbed", "attrs": {"assetId": str(rutube_id)}})
        assert client.put(f"/admin/knowledge/articles/{article_id}", headers=headers["admin"], json={
            "title": "Audio article", "summary": "", "body": body, "row_version": 2}).status_code == 200
        assert client.get(f"/media/{rutube_id}/info", headers=headers["other"]).status_code == 404
        private_info = client.get(f"/media/{rutube_id}/info", headers=headers["learner"])
        assert private_info.status_code == 200
        assert private_info.json()["embed_url"] == (
            "https://rutube.ru/play/embed/aabbccddeeff00112233445566778899/?p=sampleKey123456789")
    finally:
        with SessionLocal() as db:
            if article_id:
                db.execute(delete(KnowledgeGrant).where(KnowledgeGrant.target_id == article_id))
                db.execute(delete(FolderArticle).where(FolderArticle.article_id == article_id))
                db.execute(delete(Article).where(Article.id == article_id))
            if folder_id:
                db.execute(delete(KnowledgeFolder).where(KnowledgeFolder.id == folder_id))
            if asset_id:
                db.execute(delete(MediaAsset).where(MediaAsset.id == asset_id))
            if rutube_id:
                db.execute(delete(MediaAsset).where(MediaAsset.id == rutube_id))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids)))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.commit()
        if asset_id:
            (Path("/media") / str(asset_id)).unlink(missing_ok=True)
