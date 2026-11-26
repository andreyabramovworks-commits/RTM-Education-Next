import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bitrix import PORTAL, call
from app.db import SessionLocal, get_db
from app.directory import sync_directory, sync_structure
from app.models import BrowserSession, Employee

router = APIRouter(prefix="/auth")
COOKIE = "rtm_next_session"
AUTH_FILE = Path(os.environ.get("BITRIX_AUTH_FILE", "/data/bitrix-auth.json"))
CLIENT_ID = os.environ.get("BITRIX_CLIENT_ID", "")
logger = logging.getLogger(__name__)


def saved_install() -> dict:
    try:
        return json.loads(AUTH_FILE.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Bitrix installation is unavailable") from exc


@router.post("/install")
def install(
    event: str = Form(),
    access_token: str = Form(alias="auth[access_token]"),
    refresh_token: str = Form(alias="auth[refresh_token]"),
    member_id: str = Form(alias="auth[member_id]"),
    application_token: str = Form(alias="auth[application_token]"),
):
    if event != "ONAPPINSTALL" or not CLIENT_ID:
        raise HTTPException(403)
    try:
        info = call("app.info", access_token)
    except (OSError, ValueError) as exc:
        raise HTTPException(403, "Bitrix installation verification failed") from exc
    if info.get("CODE") != CLIENT_ID:
        raise HTTPException(403)
    AUTH_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = AUTH_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"access_token": access_token, "refresh_token": refresh_token,
                                     "member_id": member_id, "application_token": application_token}))
    os.chmod(temporary, 0o600)
    temporary.replace(AUTH_FILE)
    return {"installed": True}


@router.post("/launch")
def launch(
    response: Response,
    request: Request,
    auth_id: str = Form(alias="AUTH_ID"),
    application_token: str = Form(alias="APPLICATION_TOKEN"),
    member_id: str = Form(alias="member_id"),
    db: Session = Depends(get_db),
):
    install = saved_install()
    if request.query_params.get("DOMAIN") != PORTAL:
        raise HTTPException(403)
    if not hmac.compare_digest(application_token, install.get("application_token", "")):
        raise HTTPException(403)
    if not hmac.compare_digest(member_id, install.get("member_id", "")):
        raise HTTPException(403)
    try:
        user = call("profile", auth_id)
        bitrix_id = int(user["ID"])
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(403, "Bitrix identity verification failed") from exc
    if user.get("ACTIVE") is False:
        raise HTTPException(403, "Employee is inactive")
    employee = db.scalar(select(Employee).where(Employee.bitrix_id == bitrix_id))
    if employee is None:
        employee = Employee(bitrix_id=bitrix_id, first_name="", last_name="")
        db.add(employee)
    employee.first_name = str(user.get("NAME") or "")[:160]
    employee.last_name = str(user.get("LAST_NAME") or "")[:160]
    employee.email = str(user.get("EMAIL") or "")[:320] or None
    employee.active = True
    employee.bitrix_admin = user.get("ADMIN") is True
    employee.updated_at = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    db.flush()
    db.add(BrowserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), employee_id=employee.id, expires_at=expires))
    db.commit()
    response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite="none", max_age=8 * 3600, path="/education-next")
    return {"id": str(employee.id), "name": f"{employee.first_name} {employee.last_name}".strip(), "role": employee.effective_role}


@router.post("/app")
def open_app(
    request: Request,
    background_tasks: BackgroundTasks,
    auth_id: str = Form(alias="AUTH_ID"),
    application_token: str = Form(alias="APPLICATION_TOKEN"),
    member_id: str = Form(alias="member_id"),
    db: Session = Depends(get_db),
):
    redirect = RedirectResponse("/education-next/", status_code=303)
    profile = launch(redirect, request, auth_id, application_token, member_id, db)
    if profile["role"] in ("admin", "developer"):
        background_tasks.add_task(sync_directory_job, auth_id)
    return redirect


def sync_directory_job(access_token: str) -> None:
    if SessionLocal is None:
        return
    try:
        with SessionLocal() as db:
            sync_directory(db, access_token)
            sync_structure(db, access_token)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Bitrix directory sync failed: %s", exc)


def current_employee(request: Request, db: Session = Depends(get_db)) -> Employee:
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(401)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = db.scalar(select(BrowserSession).where(BrowserSession.token_hash == token_hash, BrowserSession.expires_at > datetime.now(timezone.utc)))
    if row is None:
        raise HTTPException(401)
    employee = db.get(Employee, row.employee_id)
    if employee is None or not employee.active:
        raise HTTPException(403)
    return employee


@router.get("/me")
def me(employee: Employee = Depends(current_employee)):
    return {"id": str(employee.id), "name": f"{employee.first_name} {employee.last_name}".strip(), "role": employee.effective_role}


@router.post("/logout", status_code=204)
def logout(response: Response, request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        row = db.get(BrowserSession, hashlib.sha256(token.encode()).hexdigest())
        if row:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE, path="/education-next", secure=True, httponly=True, samesite="none")
