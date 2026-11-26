import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import Article, BrowserSession, Course, CourseItem, CourseSection, Employee


def test_course_roles_and_version_conflict():
    assert SessionLocal is not None, "Run against an isolated PostgreSQL test database"
    marker = uuid.uuid4().hex
    employees = {}
    with SessionLocal() as db:
        for index, role in enumerate(("employee", "teacher", "editor"), start=1):
            person = Employee(bitrix_id=1_000_000_000 + int(marker[:6], 16) * 10 + index,
                              first_name="Test", last_name=role, local_role=role)
            db.add(person)
            db.flush()
            token = f"test-{marker}-{role}"
            db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=person.id,
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
            employees[role] = (person.id, token)
        db.commit()

    course_id = None
    copied_id = None
    try:
        client = TestClient(app)
        def headers(role: str):
            return {"Cookie": f"rtm_next_session={employees[role][1]}"}

        assert client.get("/admin/courses").status_code == 401
        assert client.get("/admin/courses", headers=headers("employee")).status_code == 403
        assert client.get("/admin/courses", headers=headers("teacher")).status_code == 200
        assert client.post("/admin/courses", headers=headers("teacher"), json={"title": "Denied"}).status_code == 403
        created = client.post("/admin/courses", headers=headers("editor"), json={"title": "Test course"})
        assert created.status_code == 201, created.text
        course_id = uuid.UUID(created.json()["id"])
        version = created.json()["row_version"]
        payload = {"title": "Updated", "description": "Test", "mode": "free", "row_version": version}
        assert client.put(f"/admin/courses/{course_id}", headers=headers("editor"), json=payload).status_code == 200
        assert client.put(f"/admin/courses/{course_id}", headers=headers("editor"), json=payload).status_code == 409
        current = client.get(f"/admin/courses/{course_id}", headers=headers("teacher"))
        assert current.status_code == 200
        section = client.post(f"/admin/courses/{course_id}/sections", headers=headers("editor"),
                              json={"title": "Introduction", "row_version": current.json()["row_version"]})
        assert section.status_code == 201, section.text
        section_id = section.json()["id"]
        article = client.post(f"/admin/courses/{course_id}/sections/{section_id}/articles", headers=headers("editor"),
            json={"title": "Introduction article", "row_version": section.json()["row_version"]})
        assert article.status_code == 201, article.text
        assert client.post(f"/admin/courses/{course_id}/sections/{section_id}/articles", headers=headers("teacher"),
            json={"title": "Denied", "row_version": article.json()["row_version"]}).status_code == 403
        program = client.get(f"/admin/courses/{course_id}", headers=headers("teacher")).json()
        assert len(program["sections"]) == 1
        assert program["sections"][0]["items"][0]["article_id"] == article.json()["article_id"]
        changed = client.put(f"/admin/courses/{course_id}/articles/{article.json()['article_id']}", headers=headers("editor"),
            json={"title": "New title", "summary": "", "body": {"type": "doc", "content": []}, "row_version": 1})
        assert changed.status_code == 200, changed.text
        assert changed.json()["row_version"] == 2
        second_section = client.post(f"/admin/courses/{course_id}/sections", headers=headers("editor"),
            json={"title": "Practice", "row_version": article.json()["row_version"]})
        assert second_section.status_code == 201, second_section.text
        second_article = client.post(f"/admin/courses/{course_id}/sections/{second_section.json()['id']}/articles",
            headers=headers("editor"), json={"title": "Practice article", "row_version": second_section.json()["row_version"]})
        assert second_article.status_code == 201, second_article.text
        ordered = {"row_version": second_article.json()["row_version"], "sections": [
            {"id": second_section.json()["id"], "item_ids": [article.json()["id"], second_article.json()["id"]]},
            {"id": section_id, "item_ids": []},
        ]}
        assert client.put(f"/admin/courses/{course_id}/program/order", headers=headers("teacher"), json=ordered).status_code == 403
        reordered = client.put(f"/admin/courses/{course_id}/program/order", headers=headers("editor"), json=ordered)
        assert reordered.status_code == 200, reordered.text
        assert client.put(f"/admin/courses/{course_id}/program/order", headers=headers("editor"), json=ordered).status_code == 409
        current = client.get(f"/admin/courses/{course_id}", headers=headers("teacher")).json()
        assert [row["id"] for row in current["sections"]] == [second_section.json()["id"], section_id]
        assert [row["id"] for row in current["sections"][0]["items"]] == [article.json()["id"], second_article.json()["id"]]
        copied = client.post(f"/admin/courses/{course_id}/copy", headers=headers("editor"))
        assert copied.status_code == 201, copied.text
        copied_id = uuid.UUID(copied.json()["id"])
        assert copied.json()["status"] == "draft"
        assert copied.json()["sections"][0]["items"][0]["id"] != article.json()["id"]
        assert copied.json()["sections"][0]["items"][0]["article_id"] != article.json()["article_id"]
        copied_section_id = copied.json()["sections"][0]["id"]
        copied_item = client.post(f"/admin/courses/{copied_id}/sections/{copied_section_id}/copy-item",
            headers=headers("editor"), json={"source_item_id": article.json()["id"],
                                      "row_version": copied.json()["row_version"]})
        assert copied_item.status_code == 201, copied_item.text
        assert copied_item.json()["article_id"] not in (article.json()["article_id"],
            copied.json()["sections"][0]["items"][0]["article_id"])
    finally:
        with SessionLocal() as db:
            if copied_id:
                db.execute(delete(CourseItem).where(CourseItem.course_id == copied_id))
                db.execute(delete(Article).where(Article.owner_course_id == copied_id))
                db.execute(delete(CourseSection).where(CourseSection.course_id == copied_id))
                db.execute(delete(Course).where(Course.id == copied_id))
            if course_id:
                db.execute(delete(CourseItem).where(CourseItem.course_id == course_id))
                db.execute(delete(Article).where(Article.owner_course_id == course_id))
                db.execute(delete(CourseSection).where(CourseSection.course_id == course_id))
                db.execute(delete(Course).where(Course.id == course_id))
            for employee_id, token in employees.values():
                db.execute(delete(BrowserSession).where(BrowserSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
                db.execute(delete(Employee).where(Employee.id == employee_id))
            db.commit()
