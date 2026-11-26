import uuid

from sqlalchemy import delete, select

from app import directory
from app.db import SessionLocal
from app.models import Department, Employee


def test_directory_sync_preserves_assigned_role_and_deactivates_removed_user(monkeypatch):
    assert SessionLocal is not None
    first_id = 1_600_000_000 + int(uuid.uuid4().hex[:6], 16)
    second_id = first_id + 1
    with SessionLocal() as db:
        db.add(Employee(bitrix_id=first_id, first_name="Old", last_name="Name", local_role="editor"))
        db.commit()
    monkeypatch.setattr(directory, "list_users", lambda _token: [
        {"ID": str(first_id), "NAME": "New", "LAST_NAME": "Name", "ACTIVE": True,
         "UF_DEPARTMENT": [first_id]},
        {"ID": str(second_id), "NAME": "Inactive", "LAST_NAME": "User", "ACTIVE": False},
    ])
    monkeypatch.setattr(directory, "list_departments", lambda _token: [
        {"ID": str(first_id), "NAME": "Test department", "PARENT": "0"},
    ])
    try:
        with SessionLocal() as db:
            assert directory.sync_directory(db, "test-token") == 2
            assert directory.sync_structure(db, "test-token") == 1
            first = db.scalar(select(Employee).where(Employee.bitrix_id == first_id))
            second = db.scalar(select(Employee).where(Employee.bitrix_id == second_id))
            assert first is not None and first.first_name == "New" and first.effective_role == "editor"
            assert first.department_ids == [first_id]
            assert db.get(Department, first_id).title == "Test department"
            assert second is not None and not second.active
    finally:
        with SessionLocal() as db:
            db.execute(delete(Employee).where(Employee.bitrix_id.in_([first_id, second_id])))
            db.execute(delete(Department).where(Department.bitrix_id == first_id))
            db.commit()
