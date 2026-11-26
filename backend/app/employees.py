import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Department, Employee, RoleChangeAudit
from app.permissions import require_role

router = APIRouter(prefix="/admin/employees", tags=["employees"])
ASSIGNABLE = {"employee", "teacher", "editor", "admin"}


class RoleChange(BaseModel):
    role: str
    reason: str = Field(min_length=10, max_length=1000)


def employee_data(employee: Employee) -> dict:
    return {"id": str(employee.id), "bitrix_id": employee.bitrix_id,
            "name": f"{employee.first_name} {employee.last_name}".strip(),
            "local_role": employee.local_role, "effective_role": employee.effective_role,
            "active": employee.active}


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), _actor: Employee = Depends(require_role("teacher"))):
    rows = db.scalars(select(Department).order_by(Department.title, Department.bitrix_id)).all()
    return [{"id": row.bitrix_id, "parent_id": row.parent_id, "title": row.title} for row in rows]


@router.get("/recipients")
def search_recipients(search: str = Query(default="", max_length=160),
                      db: Session = Depends(get_db), _actor: Employee = Depends(require_role("teacher"))):
    query = select(Employee).where(Employee.active.is_(True))
    if search.strip():
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condition = or_(Employee.first_name.ilike(f"%{escaped}%", escape="\\"),
                        Employee.last_name.ilike(f"%{escaped}%", escape="\\"))
        if search.strip().isdigit():
            condition = or_(condition, Employee.bitrix_id == int(search.strip()))
        query = query.where(condition)
    rows = db.scalars(query.order_by(Employee.last_name, Employee.first_name, Employee.id).limit(50)).all()
    return [{"bitrix_id": row.bitrix_id, "name": f"{row.first_name} {row.last_name}".strip(),
             "can_review": row.effective_role in ("teacher", "editor", "admin", "developer")}
            for row in rows]


@router.get("")
def list_employees(
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db), _actor: Employee = Depends(require_role("admin")),
):
    rows = db.scalars(select(Employee).order_by(Employee.last_name, Employee.first_name, Employee.id).offset(offset).limit(limit)).all()
    return [employee_data(row) for row in rows]


@router.put("/{employee_id}/role")
def change_role(employee_id: uuid.UUID, payload: RoleChange, db: Session = Depends(get_db), actor: Employee = Depends(require_role("admin"))):
    if payload.role not in ASSIGNABLE:
        raise HTTPException(422, "Role cannot be assigned")
    reason = payload.reason.strip()
    if len(reason) < 10:
        raise HTTPException(422, "Reason must contain at least 10 non-space characters")
    employee = db.scalar(select(Employee).where(Employee.id == employee_id).with_for_update())
    if employee is None:
        raise HTTPException(404)
    if employee.bitrix_id == 36 or employee.id == actor.id:
        raise HTTPException(403, "Protected role")
    if not employee.active:
        raise HTTPException(409, "Inactive employee")
    old_role = employee.local_role
    if old_role == payload.role:
        return employee_data(employee)
    employee.local_role = payload.role
    db.add(RoleChangeAudit(actor_id=actor.id, employee_id=employee.id, old_role=old_role,
                           new_role=payload.role, reason=reason))
    db.commit()
    return employee_data(employee)
