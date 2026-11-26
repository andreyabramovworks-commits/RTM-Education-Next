import hashlib
import json
from io import BytesIO
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app import auth, bitrix_delivery
from app.db import SessionLocal
from app.main import app
from app.models import BrowserSession, Employee


def test_developer_launch_can_upgrade_stale_installation_scope(monkeypatch, tmp_path: Path):
    saved = tmp_path / "bitrix-auth.json"
    saved.write_text(json.dumps({"access_token": "old", "refresh_token": "old-refresh",
        "member_id": "portal-test", "application_token": "app-token-test",
        "scope": "task,notifications,user,crm,department"}))
    monkeypatch.setattr(auth, "AUTH_FILE", saved)
    monkeypatch.setattr(auth, "CLIENT_ID", "local.test")
    monkeypatch.setattr(auth, "call", lambda method, token: {"CODE": "local.test"})
    monkeypatch.setattr(auth, "token_scopes", lambda token: ["task", "notifications", "user", "crm", "department", "im"])
    auth.capture_launch_auth("new", "new-refresh", "portal-test", "wrong-token")
    assert json.loads(saved.read_text())["access_token"] == "old"
    auth.capture_launch_auth("new", "new-refresh", "portal-test", "app-token-test")
    updated = json.loads(saved.read_text())
    assert updated["access_token"] == "new"
    assert updated["refresh_token"] == "new-refresh"
    assert updated["scope"].split(",")[-1] == "im"
    assert updated["application_token"] == "app-token-test"
    assert saved.stat().st_mode & 0o777 == 0o600


def test_token_refresh_persists_newly_granted_scope(monkeypatch, tmp_path: Path):
    saved = tmp_path / "bitrix-auth.json"
    saved.write_text(json.dumps({"access_token": "old", "refresh_token": "old-refresh",
        "member_id": "portal-test", "application_token": "app-token-test", "scope": "task"}))
    monkeypatch.setattr(bitrix_delivery, "AUTH_FILE", saved)
    monkeypatch.setattr(bitrix_delivery, "CLIENT_ID", "local.test")
    monkeypatch.setattr(bitrix_delivery, "CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(bitrix_delivery, "urlopen", lambda url, timeout: BytesIO(json.dumps({
        "access_token": "new", "refresh_token": "new-refresh", "scope": "task,im"}).encode()))
    bitrix_delivery.refresh_auth("old")
    updated = json.loads(saved.read_text())
    assert updated["scope"] == "task,im"
    assert updated["application_token"] == "app-token-test"


def test_only_developer_launch_with_refresh_token_can_update_background_credentials(monkeypatch):
    captured = []
    monkeypatch.setattr(auth, "launch", lambda *args, **kwargs: {"role": "developer"})
    monkeypatch.setattr(auth, "capture_launch_auth", lambda *args: captured.append(args))
    monkeypatch.setattr(auth, "sync_directory_job", lambda _token: None)
    client = TestClient(app, follow_redirects=False)
    data = {"AUTH_ID": "launch-test", "REFRESH_ID": "refresh-test",
            "APPLICATION_TOKEN": "app-token-test", "member_id": "portal-test"}
    response = client.post("/auth/app?DOMAIN=rtm-group.bitrix24.ru", data=data)
    assert response.status_code == 303
    assert captured == [("launch-test", "refresh-test", "portal-test", "app-token-test")]
    assert client.post("/auth/app?DOMAIN=rtm-group.bitrix24.ru",
        data={key: value for key, value in data.items() if key != "REFRESH_ID"}).status_code == 303
    assert len(captured) == 1


def test_install_and_launch_verify_portal_and_create_server_session(monkeypatch, tmp_path: Path):
    assert SessionLocal is not None, "Run against an isolated PostgreSQL test database"
    bitrix_id = 1_500_000_000 + int(uuid.uuid4().hex[:6], 16)
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "bitrix-auth.json")
    monkeypatch.setattr(auth, "CLIENT_ID", "local.test")
    monkeypatch.setattr(auth, "sync_directory_job", lambda _token: None)

    def fake_call(method, token):
        assert token in ("access-test", "launch-test")
        if method == "app.info":
            return {"CODE": "local.test"}
        if method == "profile":
            return {"ID": str(bitrix_id), "NAME": "Test", "LAST_NAME": "Admin", "ADMIN": True}
        raise AssertionError(method)

    monkeypatch.setattr(auth, "call", fake_call)
    client = TestClient(app, follow_redirects=False)
    install_data = {
        "event": "ONAPPINSTALL", "auth[access_token]": "access-test",
        "auth[refresh_token]": "refresh-test", "auth[member_id]": "portal-test",
        "auth[application_token]": "app-token-test",
    }
    result = client.post("/auth/install", data=install_data)
    assert result.status_code == 200
    assert auth.AUTH_FILE.is_file()
    assert auth.AUTH_FILE.stat().st_mode & 0o777 == 0o600
    launch_data = {"AUTH_ID": "launch-test", "APPLICATION_TOKEN": "app-token-test", "member_id": "portal-test"}
    assert client.post("/auth/app?DOMAIN=wrong.example", data=launch_data).status_code == 403
    assert client.post("/auth/app?DOMAIN=rtm-group.bitrix24.ru", data={**launch_data, "APPLICATION_TOKEN": "wrong"}).status_code == 403

    employee_id = None
    token = None
    try:
        launched = client.post("/auth/app?DOMAIN=rtm-group.bitrix24.ru", data=launch_data)
        assert launched.status_code == 303, launched.text
        assert launched.headers["location"] == "/education-next/"
        token = launched.cookies[auth.COOKIE]
        assert "httponly" in launched.headers["set-cookie"].lower()
        profile = client.get("/auth/me", headers={"Cookie": f"{auth.COOKIE}={token}"})
        assert profile.status_code == 200
        assert profile.json()["role"] == "admin"
        employee_id = uuid.UUID(profile.json()["id"])
    finally:
        with SessionLocal() as db:
            if token:
                db.execute(delete(BrowserSession).where(BrowserSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
            if employee_id:
                db.execute(delete(Employee).where(Employee.id == employee_id))
            db.commit()
