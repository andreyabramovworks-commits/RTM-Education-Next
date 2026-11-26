from fastapi.testclient import TestClient

from app.main import app
from app.db import get_db
from app.models import Employee


def test_bitrix_admin_is_effective_admin_without_local_grant():
    user = Employee(bitrix_id=1, first_name="A", last_name="B", local_role="employee", bitrix_admin=True)
    assert user.effective_role == "admin"
    user.bitrix_id = 36
    assert user.effective_role == "developer"


def test_profile_requires_server_session():
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = TestClient(app).get("/auth/me")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_readiness_checks_database_connection():
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
