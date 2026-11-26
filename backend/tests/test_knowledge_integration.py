import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import Article, ArticleRevision, BrowserSession, Department, Employee, FolderArticle, KnowledgeFolder, KnowledgeGrant


def test_direct_article_grant_hides_sibling_and_folder_grant_inherits():
    assert SessionLocal is not None
    marker = int(uuid.uuid4().hex[:6], 16)
    admin_token, learner_token, child_token = f"admin-{marker}", f"learner-{marker}", f"child-{marker}"
    with SessionLocal() as db:
        admin = Employee(bitrix_id=1_700_000_000 + marker, first_name="Test", last_name="Admin", local_role="admin")
        learner = Employee(bitrix_id=1_800_000_000 + marker, first_name="Test", last_name="Learner")
        child_reader = Employee(bitrix_id=1_600_000_000 + marker, first_name="Test", last_name="ChildReader")
        db.add_all([admin, learner, child_reader])
        db.flush()
        ids = [admin.id, learner.id, child_reader.id]
        learner_bitrix_id = learner.bitrix_id
        child_bitrix_id = child_reader.bitrix_id
        for token, employee in ((admin_token, admin), (learner_token, learner), (child_token, child_reader)):
            db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=employee.id,
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    folders: list[uuid.UUID] = []
    articles: list[uuid.UUID] = []
    department_ids = [1_500_000_000 + marker * 2, 1_500_000_001 + marker * 2]
    client = TestClient(app)
    admin_headers = {"Cookie": f"rtm_next_session={admin_token}"}
    learner_headers = {"Cookie": f"rtm_next_session={learner_token}"}
    child_headers = {"Cookie": f"rtm_next_session={child_token}"}
    try:
        root = client.post("/admin/knowledge/folders", headers=admin_headers, json={"title": "Root"})
        assert root.status_code == 201, root.text
        root_id = root.json()["id"]
        folders.append(uuid.UUID(root_id))
        child = client.post("/admin/knowledge/folders", headers=admin_headers, json={"title": "Child", "parent_id": root_id})
        assert child.status_code == 201, child.text
        child_id = child.json()["id"]
        folders.append(uuid.UUID(child_id))
        for title in ("Allowed", "Hidden"):
            response = client.post("/admin/knowledge/articles", headers=admin_headers, json={"title": title, "folder_id": child_id})
            assert response.status_code == 201, response.text
            articles.append(uuid.UUID(response.json()["id"]))
        first_body = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "First text"}]}]}
        updated = client.put(f"/admin/knowledge/articles/{articles[0]}", headers=admin_headers,
            json={"title": "Allowed", "summary": "", "body": first_body, "row_version": 1})
        assert updated.status_code == 200, updated.text
        published = client.post(f"/admin/knowledge/articles/{articles[0]}/revisions", headers=admin_headers,
            json={"revision_date": "2026-11-25", "description": "Initial article", "row_version": 2})
        assert published.status_code == 201, published.text
        revision_id = published.json()["id"]
        second_body = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "New text"}]}]}
        assert client.put(f"/admin/knowledge/articles/{articles[0]}", headers=admin_headers,
            json={"title": "Allowed", "summary": "", "body": second_body, "row_version": 2}).status_code == 200
        assert client.post("/admin/knowledge/grants", headers=learner_headers,
            json={"target_type": "article", "target_id": str(articles[0]), "subject_type": "employee", "subject_id": str(learner_bitrix_id)}).status_code == 403
        grant = client.post("/admin/knowledge/grants", headers=admin_headers,
            json={"target_type": "article", "target_id": str(articles[0]), "subject_type": "employee", "subject_id": str(learner_bitrix_id)})
        assert grant.status_code == 201, grant.text
        listing = client.get("/knowledge", headers=learner_headers)
        assert [article["title"] for article in listing.json()["articles"]] == ["Allowed"]
        assert client.get(f"/knowledge/articles/{articles[0]}", headers=learner_headers).json()["body"] == second_body
        assert client.get(f"/knowledge/revisions/{revision_id}", headers=learner_headers).json()["body"] == first_body
        assert {folder["title"] for folder in listing.json()["folders"]} == {"Root", "Child"}
        assert client.get(f"/knowledge/articles/{articles[1]}", headers=learner_headers).status_code == 404
        with SessionLocal() as db:
            db.add_all([Department(bitrix_id=department_ids[0], title="Main", parent_id=None,
                                   updated_at=datetime.now(timezone.utc)),
                        Department(bitrix_id=department_ids[1], title="Child", parent_id=department_ids[0],
                                   updated_at=datetime.now(timezone.utc))])
            person = db.get(Employee, ids[1])
            person.department_ids = [department_ids[1]]
            db.commit()
        assert client.post("/admin/knowledge/grants", headers=admin_headers,
            json={"target_type": "folder", "target_id": root_id, "subject_type": "department",
                  "subject_id": str(department_ids[0])}).status_code == 201
        assert client.get(f"/knowledge/articles/{articles[1]}", headers=learner_headers).status_code == 404
        assert client.post("/admin/knowledge/grants", headers=admin_headers,
            json={"target_type": "folder", "target_id": root_id, "subject_type": "subdepartment",
                  "subject_id": str(department_ids[0])}).status_code == 201
        assert client.get(f"/knowledge/articles/{articles[1]}", headers=learner_headers).status_code == 200
        grant = client.post("/admin/knowledge/grants", headers=admin_headers,
            json={"target_type": "folder", "target_id": root_id, "subject_type": "employee", "subject_id": str(learner_bitrix_id)})
        assert grant.status_code == 201, grant.text
        assert {article["title"] for article in client.get("/knowledge", headers=learner_headers).json()["articles"]} == {"Allowed", "Hidden"}
        assert client.post("/admin/knowledge/grants", headers=admin_headers,
            json={"target_type": "folder", "target_id": child_id, "subject_type": "employee",
                  "subject_id": str(child_bitrix_id)}).status_code == 201
        assert client.get(f"/knowledge/articles/{articles[0]}", headers=child_headers).status_code == 200
        preview = client.post("/admin/knowledge/move-preview", headers=admin_headers,
            json={"target_type": "article", "target_id": str(articles[0]), "destination_id": root_id})
        assert preview.status_code == 200, preview.text
        assert any(row["bitrix_id"] == child_bitrix_id for row in preview.json()["lost"])
        assert client.put(f"/admin/knowledge/folders/{root_id}/parent", headers=admin_headers,
            json={"parent_id": child_id, "confirmed": True}).status_code == 422
        moved = client.put(f"/admin/knowledge/articles/{articles[0]}/folder", headers=admin_headers,
            json={"folder_id": root_id, "confirmed": True})
        assert moved.status_code == 200 and moved.json()["folder_id"] == root_id
        assert client.get(f"/knowledge/articles/{articles[0]}", headers=child_headers).status_code == 404
        assert client.put(f"/admin/knowledge/folders/{child_id}/parent", headers=admin_headers,
            json={"parent_id": None, "confirmed": True}).status_code == 200
        assert client.get(f"/knowledge/articles/{articles[0]}", headers=learner_headers).status_code == 200
    finally:
        with SessionLocal() as db:
            db.execute(delete(KnowledgeGrant).where(KnowledgeGrant.target_id.in_(folders + articles)))
            db.execute(delete(ArticleRevision).where(ArticleRevision.article_id.in_(articles)))
            db.execute(delete(FolderArticle).where(FolderArticle.article_id.in_(articles)))
            db.execute(delete(Article).where(Article.id.in_(articles)))
            db.execute(delete(KnowledgeFolder).where(KnowledgeFolder.id.in_(folders)))
            db.execute(delete(BrowserSession).where(BrowserSession.employee_id.in_(ids)))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.execute(delete(Department).where(Department.bitrix_id.in_(department_ids)))
            db.commit()
