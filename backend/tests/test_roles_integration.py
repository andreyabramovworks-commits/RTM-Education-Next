import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.main import app
from app.models import BrowserSession, Employee, RoleChangeAudit


def test_admin_assigns_roles_but_cannot_assign_developer_or_change_id_36():
    assert SessionLocal is not None
    marker = uuid.uuid4().hex
    token = f"test-{marker}"
    with SessionLocal() as db:
        admin = Employee(bitrix_id=1_300_000_000 + int(marker[:6], 16), first_name="Test", last_name="Admin", bitrix_admin=True)
        student = Employee(bitrix_id=1_400_000_000 + int(marker[:6], 16), first_name="Test", last_name="Student")
        developer = Employee(bitrix_id=36, first_name="Andrey", last_name="Abramov")
        db.add_all([admin, student, developer])
        db.flush()
        ids = (admin.id, student.id, developer.id)
        db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=admin.id,
                              expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    try:
        client = TestClient(app)
        headers = {"Cookie": f"rtm_next_session={token}"}
        assert client.get("/admin/employees", headers=headers).status_code == 200
        settings = client.get("/admin/settings/status", headers=headers)
        assert settings.status_code == 200, settings.text
        assert set(settings.json()) == {"bitrix", "google", "delivery"}
        assert "access_token" not in settings.text and "refresh_token" not in settings.text
        assert client.get("/admin/settings/status").status_code == 401
        assert client.put(f"/admin/employees/{ids[1]}/role", headers=headers,
                          json={"role": "developer", "reason": "Test forbidden assignment"}).status_code == 422
        changed = client.put(f"/admin/employees/{ids[1]}/role", headers=headers,
                             json={"role": "teacher", "reason": "Approved training responsibility"})
        assert changed.status_code == 200, changed.text
        assert changed.json()["effective_role"] == "teacher"
        assert client.put(f"/admin/employees/{ids[2]}/role", headers=headers,
                          json={"role": "employee", "reason": "Attempt to demote developer"}).status_code == 403
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(RoleChangeAudit).where(RoleChangeAudit.employee_id == ids[1])) == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(RoleChangeAudit).where(RoleChangeAudit.employee_id.in_(ids)))
            db.execute(delete(BrowserSession).where(BrowserSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
            db.execute(delete(Employee).where(Employee.id.in_(ids)))
            db.commit()
