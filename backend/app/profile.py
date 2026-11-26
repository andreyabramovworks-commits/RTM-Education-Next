"""The employee's own test rewards."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.db import get_db
from app.models import Assignment, Employee, TestCompletionReward, TestDefinition

router = APIRouter(tags=["profile"])


@router.get("/my/profile")
def my_profile(db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    total = db.scalar(select(func.coalesce(func.sum(TestCompletionReward.points), 0))
        .join(Assignment, Assignment.id == TestCompletionReward.assignment_id)
        .where(Assignment.employee_id == employee.id)) or 0
    rewards = db.execute(select(TestCompletionReward, TestDefinition.title)
        .join(Assignment, Assignment.id == TestCompletionReward.assignment_id)
        .join(TestDefinition, TestDefinition.id == TestCompletionReward.test_id)
        .where(Assignment.employee_id == employee.id)
        .order_by(TestCompletionReward.awarded_at.desc(), TestCompletionReward.id.desc())
        .limit(20)).all()
    return {"name": f"{employee.first_name} {employee.last_name}".strip(),
            "points": total,
            "rewards": [{"id": str(reward.id), "test_title": title, "points": reward.points,
                         "awarded_at": reward.awarded_at.isoformat()} for reward, title in rewards]}
