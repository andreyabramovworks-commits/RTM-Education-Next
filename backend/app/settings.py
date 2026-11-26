"""Read-only operational status for app administrators."""

import os

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bitrix_delivery import AUTH_FILE, CLIENT_ID, saved_auth, DeliveryError
from app.db import get_db
from app.google_documents import GoogleReadError, credentials_ready, read_document
from app.models import Employee, OutboxJob
from app.permissions import require_role


router = APIRouter(prefix="/admin/settings", tags=["settings"])


@router.get("/status")
def status(db: Session = Depends(get_db), _actor: Employee = Depends(require_role("admin"))):
    installed = False
    notification_scope_verified = False
    if AUTH_FILE.is_file():
        try:
            auth = saved_auth()
            installed = True
            notification_scope_verified = "im" in str(auth.get("scope", "")).split(",")
        except DeliveryError:
            pass
    queue = dict(db.execute(select(OutboxJob.status, func.count(OutboxJob.id)).group_by(OutboxJob.status)).all())
    google_ready = False
    probe_id = os.environ.get("GOOGLE_PROBE_DOCUMENT_ID", "")
    if credentials_ready() and probe_id:
        try:
            read_document(probe_id)
            google_ready = True
        except GoogleReadError:
            pass
    return {
        "bitrix": {"client_id_configured": bool(CLIENT_ID), "installed": installed,
                   "client_secret_configured": bool(os.environ.get("BITRIX_CLIENT_SECRET")),
                   "notification_scope_verified": notification_scope_verified},
        "google": {"credentials_present": credentials_ready(), "server_access_verified": google_ready},
        "delivery": {"pending": queue.get("pending", 0), "retry": queue.get("retry", 0),
                     "failed": queue.get("failed", 0), "uncertain": queue.get("uncertain", 0)},
    }
