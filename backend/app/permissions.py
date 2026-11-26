from fastapi import Depends, HTTPException

from app.auth import current_employee
from app.models import Employee

ROLE_RANK = {"employee": 0, "teacher": 1, "editor": 2, "admin": 3, "developer": 4}


def require_role(minimum: str):
    if minimum not in ROLE_RANK:
        raise ValueError("Unknown minimum role")

    def dependency(employee: Employee = Depends(current_employee)) -> Employee:
        if ROLE_RANK.get(employee.effective_role, -1) < ROLE_RANK[minimum]:
            raise HTTPException(403, "Insufficient role")
        return employee

    return dependency
