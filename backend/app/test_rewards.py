"""Award a passed test exactly once per assignment and test."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TestAttempt, TestCompletionReward


def award_passed_test(db: Session, attempt: TestAttempt, now: datetime) -> TestCompletionReward:
    existing = db.scalar(select(TestCompletionReward).where(
        TestCompletionReward.assignment_id == attempt.assignment_id,
        TestCompletionReward.test_id == attempt.test_id))
    if existing is not None:
        return existing
    reward = TestCompletionReward(assignment_id=attempt.assignment_id, test_id=attempt.test_id,
        attempt_id=attempt.id, points=attempt.reward_points_snapshot, awarded_at=now)
    db.add(reward)
    db.flush()
    return reward
