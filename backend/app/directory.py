import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.bitrix import list_departments, list_users
from app.models import Department, Employee

logger = logging.getLogger(__name__)


def sync_directory(db: Session, access_token: str) -> int:
    users = list_users(access_token)
    now = datetime.now(timezone.utc)
    count = 0
    for user in users:
        if user.get("USER_TYPE", "employee") != "employee":
            continue
        try:
            bitrix_id = int(user["ID"])
        except (ValueError, TypeError, KeyError):
            logger.warning("Skipping Bitrix user with invalid ID")
            continue
        if bitrix_id <= 0:
            continue
        active_value = user.get("ACTIVE", True)
        active = active_value in (True, "Y", "true", "1", 1)
        values = {
            "bitrix_id": bitrix_id,
            "first_name": str(user.get("NAME") or "")[:160],
            "last_name": str(user.get("LAST_NAME") or "")[:160],
            "email": str(user.get("EMAIL") or "")[:320] or None,
            "active": active,
            "department_ids": sorted({int(value) for value in user.get("UF_DEPARTMENT", [])
                                      if str(value).isdigit() and int(value) > 0}),
            "updated_at": now,
        }
        statement = insert(Employee).values(**values).on_conflict_do_update(
            index_elements=[Employee.bitrix_id],
            set_={key: values[key] for key in ("first_name", "last_name", "email", "active", "department_ids", "updated_at")},
        )
        db.execute(statement)
        count += 1
    db.commit()
    return count


def sync_structure(db: Session, access_token: str) -> int:
    rows = list_departments(access_token)
    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        try:
            bitrix_id = int(row["ID"])
            parent_id = int(row.get("PARENT") or 0) or None
        except (KeyError, ValueError, TypeError):
            logger.warning("Skipping invalid Bitrix department")
            continue
        if bitrix_id <= 0:
            continue
        values = {"bitrix_id": bitrix_id, "parent_id": parent_id,
                  "title": str(row.get("NAME") or "")[:240], "updated_at": now}
        db.execute(insert(Department).values(**values).on_conflict_do_update(
            index_elements=[Department.bitrix_id], set_={key: values[key] for key in ("parent_id", "title", "updated_at")}))
        count += 1
    db.commit()
    return count
