import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.db import get_db
from app.models import Article, ArticleRevision, Assignment, AssignmentAction, AssignmentCampaign, Course, Department, Employee, OutboxJob, TestDefinition, TestQuestion
from app.permissions import ROLE_RANK, require_role
from app.task_templates import render_task, validate_template

router = APIRouter(tags=["campaigns"])


class NewCampaign(BaseModel):
    target_type: str = Field(pattern="^(course|course_article|course_test|article_revision)$")
    target_id: uuid.UUID
    title: str = Field(min_length=1, max_length=240)
    recipient_bitrix_ids: list[int] = Field(default_factory=list)
    department_ids: list[int] = Field(default_factory=list)
    include_subdepartments: bool = False
    include_new_employees: bool = False
    reviewer_bitrix_ids: list[int] = Field(default_factory=list)
    due_mode: str = Field(pattern="^(relative|absolute)$")
    due_days: int | None = Field(default=None, ge=1, le=3650)
    due_at: datetime | None = None
    notify_enabled: bool = False
    task_enabled: bool = False
    task_title: str = Field(default="", max_length=240)
    task_description: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def valid_deadline(self):
        if not self.recipient_bitrix_ids and not self.department_ids:
            raise ValueError("Choose recipients or departments")
        if self.include_new_employees and not self.department_ids:
            raise ValueError("New employees require a department rule")
        if self.due_mode == "relative" and self.due_days is None:
            raise ValueError("Relative deadline needs days")
        if self.due_mode == "absolute" and (self.due_at is None or self.due_at.tzinfo is None):
            raise ValueError("Absolute deadline needs timezone")
        if self.task_enabled and not self.task_title.strip():
            raise ValueError("Task title is required")
        if self.task_enabled:
            validate_template(self.task_title)
            validate_template(self.task_description)
        return self


class Launch(BaseModel):
    confirmed: bool


class IndividualDecision(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool


class ChangeDue(IndividualDecision):
    due_at: datetime


class Reminder(IndividualDecision):
    request_id: uuid.UUID


class AddRecipients(IndividualDecision):
    recipient_bitrix_ids: list[int] = Field(min_length=1, max_length=500)


class ChangeNewEmployees(IndividualDecision):
    enabled: bool


def audit_assignment(db: Session, assignment: Assignment, actor: Employee,
                     action: str, reason: str, details: dict) -> None:
    db.add(AssignmentAction(assignment_id=assignment.id, actor_id=actor.id, action=action,
        reason=reason, details=details, occurred_at=datetime.now(timezone.utc)))


def campaign_target_title(db: Session, campaign: AssignmentCampaign) -> str:
    if campaign.target_type == "course":
        course = db.get(Course, campaign.target_id)
        return course.title if course else campaign.title
    if campaign.target_type == "course_article":
        article = db.get(Article, campaign.target_id)
        return article.title if article else campaign.title
    if campaign.target_type == "course_test":
        test = db.get(TestDefinition, campaign.target_id)
        return test.title if test else campaign.title
    revision = db.get(ArticleRevision, campaign.target_id)
    if revision:
        article = db.get(Article, revision.article_id)
        if article:
            return article.title
    return campaign.title


def create_assignment(db: Session, campaign: AssignmentCampaign, employee: Employee,
                      now: datetime, source: dict) -> Assignment:
    due_at = now + timedelta(days=campaign.due_days) if campaign.due_mode == "relative" else campaign.due_at
    assignment = Assignment(campaign_id=campaign.id, employee_id=employee.id,
        status="not_started", assigned_at=now, due_at=due_at, recipient_source=source)
    db.add(assignment)
    db.flush()
    if campaign.notify_enabled:
        db.add(OutboxJob(kind="bitrix_notification", idempotency_key=f"{assignment.id}:notification",
            payload={"assignment_id": str(assignment.id), "bitrix_id": employee.bitrix_id}))
    if campaign.task_enabled:
        name = f"{employee.first_name} {employee.last_name}".strip()
        target_title = campaign_target_title(db, campaign)
        db.add(OutboxJob(kind="bitrix_task", idempotency_key=f"{assignment.id}:task",
            payload={"assignment_id": str(assignment.id), "bitrix_id": employee.bitrix_id,
                     "title": render_task(campaign.task_title, target_title, name, due_at),
                     "description": render_task(campaign.task_description, target_title, name, due_at),
                     "due_at": due_at.isoformat() if due_at else None}))
    return assignment


def ensure_revision_assignable(db: Session, campaign: AssignmentCampaign) -> None:
    if campaign.target_type != "article_revision":
        return
    revision = db.get(ArticleRevision, campaign.target_id)
    if revision is None or revision.deleted_at is not None:
        raise HTTPException(409, "Revision is withdrawn")


def sync_new_employee_assignments(db: Session) -> int:
    """Assign employees first discovered after an active department rule was enabled."""
    campaigns = db.scalars(select(AssignmentCampaign).where(AssignmentCampaign.status == "active")
        .order_by(AssignmentCampaign.id).with_for_update()).all()
    eligible = [campaign for campaign in campaigns
        if campaign.recipient_policy.get("include_new_employees")
        and campaign.recipient_policy.get("new_employee_from")
        and campaign.recipient_policy.get("department_ids")
        and (campaign.target_type != "article_revision" or
            (revision := db.get(ArticleRevision, campaign.target_id)) is not None
            and revision.deleted_at is None)]
    if not eligible:
        db.rollback()
        return 0
    departments = {row.bitrix_id: row.parent_id for row in db.scalars(select(Department)).all()}
    now = datetime.now(timezone.utc)
    total = 0
    for campaign in eligible:
        policy = dict(campaign.recipient_policy)
        cutoff = datetime.fromisoformat(policy["new_employee_from"])
        selected = set(policy["department_ids"])
        existing = set(db.scalars(select(Assignment.employee_id).where(
            Assignment.campaign_id == campaign.id)).all())
        employees = db.scalars(select(Employee).where(Employee.active.is_(True),
            Employee.first_seen_at > cutoff, Employee.first_seen_at <= now)).all()
        added = []
        for employee in employees:
            if employee.id in existing:
                continue
            matched = []
            for department_id in employee.department_ids:
                cursor = department_id
                visited = set()
                while cursor and cursor not in visited:
                    if cursor in selected:
                        matched.append(department_id)
                        break
                    if not policy.get("include_subdepartments"):
                        break
                    visited.add(cursor)
                    cursor = departments.get(cursor)
            if not matched:
                continue
            assignment = create_assignment(db, campaign, employee, now,
                {"type": "new_employee_department", "bitrix_id": employee.bitrix_id,
                 "department_ids": sorted(set(matched))})
            audit_assignment(db, assignment, db.get(Employee, campaign.created_by),
                "auto_add_recipient", "Новый сотрудник по правилу подразделения кампании",
                {"campaign_id": str(campaign.id), "first_seen_at": employee.first_seen_at.isoformat(),
                 "department_ids": sorted(set(matched))})
            added.append(employee.bitrix_id)
            existing.add(employee.id)
        if added:
            policy["employee_ids"] = sorted(set(policy.get("employee_ids", [])) | set(added))
            campaign.recipient_policy = policy
            total += len(added)
    db.commit()
    return total


def editable_assignment(db: Session, assignment_id: uuid.UUID) -> Assignment:
    assignment = db.scalar(select(Assignment).where(Assignment.id == assignment_id).with_for_update())
    if assignment is None:
        raise HTTPException(404)
    if assignment.status in ("completed", "exempted", "cancelled"):
        raise HTTPException(409, "Assignment is closed")
    return assignment


def campaign_data(campaign: AssignmentCampaign, count: int = 0) -> dict:
    return {"id": str(campaign.id), "target_type": campaign.target_type, "target_id": str(campaign.target_id),
            "title": campaign.title, "status": campaign.status, "recipient_count": count,
            "due_mode": campaign.due_mode, "due_days": campaign.due_days,
            "due_at": campaign.due_at.isoformat() if campaign.due_at else None,
            "notify_enabled": campaign.notify_enabled, "task_enabled": campaign.task_enabled,
            "task_title": campaign.task_title, "task_description": campaign.task_description,
            "reviewer_ids": campaign.reviewer_ids,
            "include_new_employees": bool(campaign.recipient_policy.get("include_new_employees")),
            "has_department_rule": bool(campaign.recipient_policy.get("department_ids")),
            "launched_at": campaign.launched_at.isoformat() if campaign.launched_at else None}


@router.get("/admin/campaigns/{campaign_id}/preview")
def campaign_preview(campaign_id: uuid.UUID, db: Session = Depends(get_db),
                     _actor: Employee = Depends(require_role("teacher"))):
    campaign = db.get(AssignmentCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(404)
    ids = campaign.recipient_policy.get("employee_ids", [])
    recipients = db.scalars(select(Employee).where(Employee.bitrix_id.in_(ids), Employee.active.is_(True))
        .order_by(Employee.last_name, Employee.first_name)).all()
    if len(recipients) != len(ids):
        raise HTTPException(409, "A recipient is inactive or missing")
    example = recipients[0] if recipients else None
    due_at = (datetime.now(timezone.utc) + timedelta(days=campaign.due_days)
              if campaign.due_mode == "relative" else campaign.due_at)
    name = f"{example.first_name} {example.last_name}".strip() if example else ""
    target_title = campaign_target_title(db, campaign)
    inactive_ids = campaign.recipient_policy.get("inactive_excluded_ids", [])
    inactive_rows = db.scalars(select(Employee).where(Employee.bitrix_id.in_(inactive_ids))).all() if inactive_ids else []
    inactive_names = {row.bitrix_id: f"{row.first_name} {row.last_name}".strip() for row in inactive_rows}
    selected_directly = set(campaign.recipient_policy.get("selected_employee_ids", []))
    recipient_preview = []
    for employee in recipients:
        employee_name = f"{employee.first_name} {employee.last_name}".strip()
        recipient_preview.append({"bitrix_id": employee.bitrix_id, "name": employee_name,
            "source": "individual" if employee.bitrix_id in selected_directly else "department",
            "due_at": due_at.isoformat() if due_at else None,
            "task_title": render_task(campaign.task_title, target_title, employee_name, due_at) if campaign.task_enabled else None,
            "task_description": render_task(campaign.task_description, target_title, employee_name, due_at) if campaign.task_enabled else None})
    return {"recipient_count": len(recipients), "example_recipient": name,
            "due_at": due_at.isoformat() if due_at else None,
            "relative_due_is_estimate": campaign.due_mode == "relative",
            "duplicates_excluded": campaign.recipient_policy.get("duplicates_excluded", 0),
            "duplicate_recipients": [row["name"] for row in recipient_preview if row["bitrix_id"] in
                campaign.recipient_policy.get("duplicate_bitrix_ids", [])],
            "inactive_excluded": [{"bitrix_id": bitrix_id, "name": inactive_names.get(bitrix_id, f"#{bitrix_id}")}
                for bitrix_id in inactive_ids],
            "recipients": recipient_preview,
            "task_title": render_task(campaign.task_title, target_title, name, due_at) if campaign.task_enabled else None,
            "task_description": render_task(campaign.task_description, target_title, name, due_at) if campaign.task_enabled else None}


@router.post("/admin/campaigns", status_code=201)
def create_campaign(payload: NewCampaign, db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if payload.target_type == "course":
        course = db.get(Course, payload.target_id)
        if course is None or course.status != "active":
            raise HTTPException(422, "Course must be active before assignment")
    elif payload.target_type == "course_article":
        article = db.get(Article, payload.target_id)
        if article is None or article.owner_course_id is None:
            raise HTTPException(404)
    elif payload.target_type == "course_test":
        test = db.get(TestDefinition, payload.target_id)
        if test is None or test.owner_course_id is None:
            raise HTTPException(404)
    else:
        revision = db.get(ArticleRevision, payload.target_id)
        if revision is None or revision.deleted_at is not None:
            raise HTTPException(404)
    departments = {row.bitrix_id: row for row in db.scalars(select(Department)).all()}
    selected_departments = set(payload.department_ids)
    if any(department_id not in departments for department_id in selected_departments):
        raise HTTPException(422, "Unknown department")
    included_departments = set(selected_departments)
    if payload.include_subdepartments:
        for department in departments.values():
            cursor = department.bitrix_id
            visited: set[int] = set()
            while cursor and cursor not in visited:
                if cursor in selected_departments:
                    included_departments.add(department.bitrix_id)
                    break
                visited.add(cursor)
                parent = departments.get(cursor)
                cursor = parent.parent_id if parent else None
    department_members = db.scalars(select(Employee)).all() if included_departments else []
    department_recipients = [person for person in department_members if person.active]
    inactive_ids = sorted(person.bitrix_id for person in department_members if not person.active
        and included_departments.intersection(person.department_ids))
    direct_recipients = set(payload.recipient_bitrix_ids)
    department_ids = {person.bitrix_id for person in department_recipients
        if included_departments.intersection(person.department_ids)}
    recipients = sorted(direct_recipients | department_ids)
    occurrences = Counter(payload.recipient_bitrix_ids)
    for person in department_recipients:
        selected_memberships = included_departments.intersection(person.department_ids)
        if selected_memberships:
            occurrences[person.bitrix_id] += len(selected_memberships)
    if not recipients:
        raise HTTPException(422, "No active recipients")
    rows = db.scalars(select(Employee).where(Employee.bitrix_id.in_(recipients), Employee.active.is_(True))).all()
    if len(rows) != len(recipients):
        raise HTTPException(422, "Recipients must be active employees")
    reviewers = sorted(set(payload.reviewer_bitrix_ids))
    reviewer_rows = db.scalars(select(Employee).where(Employee.bitrix_id.in_(reviewers), Employee.active.is_(True))).all() if reviewers else []
    if len(reviewer_rows) != len(reviewers) or any(ROLE_RANK.get(row.effective_role, -1) < ROLE_RANK["teacher"] for row in reviewer_rows):
        raise HTTPException(422, "Reviewers must be active teachers")
    if payload.due_mode == "absolute" and payload.due_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Deadline must be in the future")
    campaign = AssignmentCampaign(target_type=payload.target_type, target_id=payload.target_id,
        title=payload.title.strip(), status="draft", recipient_policy={"employee_ids": recipients,
            "selected_employee_ids": sorted(set(payload.recipient_bitrix_ids)),
            "department_ids": sorted(selected_departments), "include_subdepartments": payload.include_subdepartments,
            "include_new_employees": payload.include_new_employees,
            "duplicates_excluded": sum(count - 1 for count in occurrences.values() if count > 1),
            "duplicate_bitrix_ids": sorted(bitrix_id for bitrix_id, count in occurrences.items() if count > 1),
            "inactive_excluded_ids": inactive_ids},
        reviewer_ids=reviewers, due_mode=payload.due_mode, due_days=payload.due_days if payload.due_mode == "relative" else None,
        due_at=payload.due_at if payload.due_mode == "absolute" else None,
        notify_enabled=payload.notify_enabled, task_enabled=payload.task_enabled,
        task_title=payload.task_title.strip(), task_description=payload.task_description,
        created_by=actor.id)
    db.add(campaign)
    db.commit()
    return campaign_data(campaign, len(recipients))


@router.get("/admin/campaigns")
def list_campaigns(target_type: str | None = None, target_id: uuid.UUID | None = None,
                   limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db),
                   _actor: Employee = Depends(require_role("teacher"))):
    query = select(AssignmentCampaign)
    if target_type:
        query = query.where(AssignmentCampaign.target_type == target_type)
    if target_id:
        query = query.where(AssignmentCampaign.target_id == target_id)
    rows = db.scalars(query.order_by(AssignmentCampaign.created_at.desc()).limit(limit)).all()
    return [campaign_data(row, len(row.recipient_policy.get("employee_ids", []))) for row in rows]


@router.get("/admin/campaigns/{campaign_id}/assignments")
def list_campaign_assignments(campaign_id: uuid.UUID, db: Session = Depends(get_db),
                              _actor: Employee = Depends(require_role("teacher"))):
    if db.get(AssignmentCampaign, campaign_id) is None:
        raise HTTPException(404)
    rows = db.execute(select(Assignment, Employee).join(Employee, Employee.id == Assignment.employee_id)
        .where(Assignment.campaign_id == campaign_id).order_by(Employee.last_name, Employee.first_name)).all()
    return [{"id": str(assignment.id), "employee_name": f"{person.first_name} {person.last_name}".strip(),
             "employee_bitrix_id": person.bitrix_id, "status": assignment.status,
             "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
             "is_overdue": bool(assignment.due_at and assignment.due_at < datetime.now(timezone.utc)
                 and assignment.status not in ("completed", "exempted", "cancelled"))}
            for assignment, person in rows]


@router.post("/admin/campaigns/{campaign_id}/recipients")
def add_campaign_recipients(campaign_id: uuid.UUID, payload: AddRecipients,
                            db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    campaign = db.scalar(select(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id).with_for_update())
    if campaign is None:
        raise HTTPException(404)
    if campaign.status != "active":
        raise HTTPException(409, "Campaign is not active")
    ensure_revision_assignable(db, campaign)
    requested = set(payload.recipient_bitrix_ids)
    employees = db.scalars(select(Employee).where(Employee.bitrix_id.in_(requested), Employee.active.is_(True))).all()
    if len(employees) != len(requested):
        raise HTTPException(422, "Recipients must be active employees")
    existing = set(db.scalars(select(Employee.bitrix_id).join(Assignment, Assignment.employee_id == Employee.id)
        .where(Assignment.campaign_id == campaign_id)).all())
    now = datetime.now(timezone.utc)
    added = []
    for employee in employees:
        if employee.bitrix_id in existing:
            continue
        assignment = create_assignment(db, campaign, employee, now,
            {"type": "manual", "bitrix_id": employee.bitrix_id})
        audit_assignment(db, assignment, actor, "add_recipient", payload.reason.strip(),
            {"campaign_id": str(campaign.id), "employee_bitrix_id": employee.bitrix_id})
        added.append(employee.bitrix_id)
    policy = dict(campaign.recipient_policy)
    policy["employee_ids"] = sorted(set(policy.get("employee_ids", [])) | set(added))
    campaign.recipient_policy = policy
    db.commit()
    return {"added_ids": sorted(added), "already_assigned_ids": sorted(requested - set(added)),
            "recipient_count": len(policy["employee_ids"])}


@router.put("/admin/campaigns/{campaign_id}/new-employees")
def change_new_employees(campaign_id: uuid.UUID, payload: ChangeNewEmployees,
                         db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    campaign = db.scalar(select(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id).with_for_update())
    if campaign is None:
        raise HTTPException(404)
    if campaign.status != "active":
        raise HTTPException(409, "Campaign is not active")
    policy = dict(campaign.recipient_policy)
    if payload.enabled and not policy.get("department_ids"):
        raise HTTPException(422, "New employees require a department rule")
    previous = bool(policy.get("include_new_employees"))
    if previous != payload.enabled:
        now = datetime.now(timezone.utc)
        policy["include_new_employees"] = payload.enabled
        policy["new_employee_from"] = now.isoformat() if payload.enabled else None
        history = list(policy.get("changes", []))
        history.append({"action": "new_employee_rule", "enabled": payload.enabled,
                        "actor_id": str(actor.id), "reason": payload.reason.strip(), "at": now.isoformat()})
        policy["changes"] = history
        campaign.recipient_policy = policy
        db.commit()
    return campaign_data(campaign, len(policy.get("employee_ids", [])))


@router.get("/admin/campaigns/{campaign_id}/delivery")
def campaign_delivery(campaign_id: uuid.UUID, db: Session = Depends(get_db),
                      _actor: Employee = Depends(require_role("teacher"))):
    if db.get(AssignmentCampaign, campaign_id) is None:
        raise HTTPException(404)
    rows = db.execute(select(Assignment, Employee).join(Employee, Employee.id == Assignment.employee_id)
        .where(Assignment.campaign_id == campaign_id)).all()
    names = {str(assignment.id): f"{person.first_name} {person.last_name}".strip()
             for assignment, person in rows}
    jobs = db.scalars(select(OutboxJob).where(OutboxJob.payload["assignment_id"].astext.in_(list(names)))
        .order_by(OutboxJob.created_at, OutboxJob.id)).all() if names else []
    included = jobs
    return {"jobs": [{"id": str(job.id), "employee_name": names[job.payload["assignment_id"]],
        "kind": job.kind, "status": job.status, "attempts": job.attempts,
        "last_error": job.last_error, "external_id": job.external_id} for job in included],
        "counts": {status: sum(job.status == status for job in included)
                   for status in ("pending", "retry", "sending", "sent", "failed", "uncertain")}}


@router.post("/admin/outbox/{job_id}/retry")
def retry_delivery(job_id: uuid.UUID, payload: IndividualDecision, db: Session = Depends(get_db),
                   actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    job = db.scalar(select(OutboxJob).where(OutboxJob.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(404)
    if job.status != "failed":
        raise HTTPException(409, "Only confirmed failures can be retried")
    assignment = db.get(Assignment, uuid.UUID(job.payload["assignment_id"]))
    if assignment is None:
        raise HTTPException(404)
    old_error = job.last_error
    job.status = "retry"
    job.next_run_at = datetime.now(timezone.utc)
    audit_assignment(db, assignment, actor, "retry_delivery", payload.reason.strip(),
        {"job_id": str(job.id), "kind": job.kind, "previous_error": old_error})
    db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/admin/assignments/{assignment_id}/due")
def change_assignment_due(assignment_id: uuid.UUID, payload: ChangeDue, db: Session = Depends(get_db),
                          actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10 or payload.due_at.tzinfo is None:
        raise HTTPException(422, "Confirmed reason and timezone are required")
    assignment = editable_assignment(db, assignment_id)
    previous = assignment.due_at.isoformat() if assignment.due_at else None
    assignment.due_at = payload.due_at
    audit_assignment(db, assignment, actor, "change_due", payload.reason.strip(),
        {"previous_due_at": previous, "new_due_at": payload.due_at.isoformat()})
    db.commit()
    return {"id": str(assignment.id), "due_at": assignment.due_at.isoformat(), "status": assignment.status}


@router.post("/admin/assignments/{assignment_id}/remind", status_code=201)
def remind_assignment(assignment_id: uuid.UUID, payload: Reminder, db: Session = Depends(get_db),
                      actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    assignment = editable_assignment(db, assignment_id)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id)
    if campaign is None or campaign.status != "active":
        raise HTTPException(409, "Campaign is not active")
    person = db.get(Employee, assignment.employee_id)
    if person is None or not person.active:
        raise HTTPException(409, "Employee is not active")
    key = f"{assignment.id}:remind:{payload.request_id}"
    existing = db.scalar(select(OutboxJob).where(OutboxJob.idempotency_key == key))
    if existing:
        return {"id": str(existing.id), "status": existing.status}
    job = OutboxJob(kind="bitrix_notification", idempotency_key=key,
        payload={"assignment_id": str(assignment.id), "bitrix_id": person.bitrix_id,
                 "message": f"Напоминание об обучении: {campaign.title}. Откройте RTM Обучение Next в Битрикс24."})
    db.add(job)
    db.flush()
    audit_assignment(db, assignment, actor, "remind", payload.reason.strip(), {"job_id": str(job.id)})
    db.commit()
    return {"id": str(job.id), "status": job.status}


@router.post("/admin/assignments/{assignment_id}/exempt")
def exempt_assignment(assignment_id: uuid.UUID, payload: IndividualDecision,
                      db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    assignment = editable_assignment(db, assignment_id)
    previous = assignment.status
    assignment.status = "exempted"
    audit_assignment(db, assignment, actor, "exempt", payload.reason.strip(), {"previous_status": previous})
    db.commit()
    return {"id": str(assignment.id), "status": assignment.status}


@router.post("/admin/assignments/{assignment_id}/confirm-complete")
def confirm_assignment_complete(assignment_id: uuid.UUID, payload: IndividualDecision,
                                db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed or len(payload.reason.strip()) < 10:
        raise HTTPException(422, "Confirmed reason is required")
    assignment = editable_assignment(db, assignment_id)
    previous = assignment.status
    assignment.status = "completed"
    assignment.completed_at = datetime.now(timezone.utc)
    audit_assignment(db, assignment, actor, "confirm_complete", payload.reason.strip(),
        {"previous_status": previous, "method": "manual"})
    db.commit()
    return {"id": str(assignment.id), "status": assignment.status}


@router.post("/admin/campaigns/{campaign_id}/launch")
def launch_campaign(campaign_id: uuid.UUID, payload: Launch, db: Session = Depends(get_db),
                    _actor: Employee = Depends(require_role("teacher"))):
    if not payload.confirmed:
        raise HTTPException(422, "Launch needs explicit confirmation")
    campaign = db.scalar(select(AssignmentCampaign).where(AssignmentCampaign.id == campaign_id).with_for_update())
    if campaign is None:
        raise HTTPException(404)
    if campaign.status == "active":
        count = len(campaign.recipient_policy.get("employee_ids", []))
        return campaign_data(campaign, count)
    if campaign.status != "draft":
        raise HTTPException(409, "Campaign is not a draft")
    if campaign.target_type == "course":
        course = db.get(Course, campaign.target_id)
        if course is None or course.status != "active":
            raise HTTPException(409, "Course is not active")
    elif campaign.target_type == "article_revision":
        ensure_revision_assignable(db, campaign)
        test = db.scalar(select(TestDefinition).where(TestDefinition.article_revision_id == campaign.target_id))
        if test and not db.scalar(select(TestQuestion.id).where(TestQuestion.test_id == test.id).limit(1)):
            raise HTTPException(409, "Revision test has no questions")
    elif campaign.target_type == "course_test":
        if not db.scalar(select(TestQuestion.id).where(TestQuestion.test_id == campaign.target_id).limit(1)):
            raise HTTPException(409, "Test has no questions")
    now = datetime.now(timezone.utc)
    recipient_ids = campaign.recipient_policy.get("employee_ids", [])
    recipients = db.scalars(select(Employee).where(Employee.bitrix_id.in_(recipient_ids), Employee.active.is_(True))).all()
    if len(recipients) != len(recipient_ids):
        raise HTTPException(409, "A recipient is inactive or missing")
    for employee in recipients:
        selected_directly = employee.bitrix_id in campaign.recipient_policy.get("selected_employee_ids", [])
        create_assignment(db, campaign, employee, now,
            {"type": "employee" if selected_directly else "department",
             "bitrix_id": employee.bitrix_id,
             "department_ids": sorted(set(employee.department_ids) & set(campaign.recipient_policy.get("department_ids", [])))})
    campaign.status = "active"
    campaign.launched_at = now
    if campaign.recipient_policy.get("include_new_employees"):
        campaign.recipient_policy = {**campaign.recipient_policy, "new_employee_from": now.isoformat()}
    db.commit()
    return campaign_data(campaign, len(recipients))


@router.get("/my/assignments")
def my_assignments(db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    rows = db.execute(select(Assignment, AssignmentCampaign).join(AssignmentCampaign,
        AssignmentCampaign.id == Assignment.campaign_id).where(Assignment.employee_id == employee.id)
        .order_by(Assignment.assigned_at.desc())).all()
    return [{"id": str(assignment.id), "campaign_id": str(campaign.id), "title": campaign.title,
             "target_type": campaign.target_type, "target_id": str(campaign.target_id),
             "status": assignment.status, "assigned_at": assignment.assigned_at.isoformat(),
             "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
             "is_overdue": bool(assignment.due_at and assignment.due_at < datetime.now(timezone.utc)
                                and assignment.status not in ("completed", "exempted", "cancelled"))}
            for assignment, campaign in rows]
