"""Read model for the active campaigns shown in the two review-center domains."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, and_, case, cast, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (Article, ArticleRevision, Assignment, AssignmentAction, AssignmentCampaign,
    Course, CourseItem, CourseSection, Department, Employee, ItemCompletion, ReviewTask,
    TestAttempt, TestCompletionReward, TestDefinition)
from app.permissions import require_role

router = APIRouter(prefix="/admin/review-center", tags=["review-center"])

ACTIVE_TARGETS = {
    "materials": ("article_revision", "course_article", "course_test"),
    "courses": ("course",),
}
FINISHED = ("completed", "exempted", "cancelled")


@router.get("/reviewers")
def review_reviewer_options(context: str = Query(default="materials", pattern="^(materials|courses)$"),
                            db: Session = Depends(get_db),
                            _actor: Employee = Depends(require_role("teacher"))):
    assigned = db.scalars(select(AssignmentCampaign.reviewer_ids).where(
        AssignmentCampaign.status == "active",
        AssignmentCampaign.target_type.in_(ACTIVE_TARGETS[context]))).all()
    bitrix_ids = {int(value) for values in assigned for value in values if str(value).isdigit()}
    if not bitrix_ids:
        return []
    people = db.scalars(select(Employee).where(Employee.bitrix_id.in_(bitrix_ids))
        .order_by(Employee.last_name, Employee.first_name)).all()
    return [{"bitrix_id": person.bitrix_id,
             "name": f"{person.first_name} {person.last_name}".strip()} for person in people]


def department_scope(db: Session, department_id: int) -> set[int]:
    departments = db.scalars(select(Department)).all()
    if department_id not in {row.bitrix_id for row in departments}:
        raise HTTPException(422, "Unknown department")
    children: dict[int, set[int]] = {}
    for row in departments:
        if row.parent_id is not None:
            children.setdefault(row.parent_id, set()).add(row.bitrix_id)
    result = {department_id}
    pending = [department_id]
    while pending:
        for child in children.get(pending.pop(), set()):
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def filtered_assignments(db: Session, context: str, search: str, department_id: int | None,
                         status: str | None, target_type: str | None = None,
                         due_from: datetime | None = None, due_to: datetime | None = None,
                         progress_band: str | None = None, mine: Employee | None = None,
                         reviewer_bitrix_id: int | None = None, revision_number: int | None = None,
                         confirmation_method: str | None = None):
    now = datetime.now(timezone.utc)
    required_total = select(func.count(CourseItem.id)).where(
        CourseItem.course_id == AssignmentCampaign.target_id, CourseItem.required.is_(True),
    ).correlate(AssignmentCampaign).scalar_subquery()
    required_done = select(func.count(ItemCompletion.id)).join(
        CourseItem, CourseItem.id == ItemCompletion.course_item_id,
    ).where(ItemCompletion.assignment_id == Assignment.id, CourseItem.required.is_(True),
    ).correlate(Assignment).scalar_subquery()
    query = select(
        Assignment.id.label("assignment_id"), Assignment.employee_id,
        Assignment.status, Assignment.due_at, Assignment.assigned_at, Assignment.completed_at,
        AssignmentCampaign.id.label("campaign_id"), AssignmentCampaign.title.label("campaign_title"),
        AssignmentCampaign.target_type, AssignmentCampaign.target_id,
        AssignmentCampaign.reviewer_ids,
        AssignmentCampaign.launched_at, AssignmentCampaign.due_at.label("campaign_due_at"),
        Employee.bitrix_id, Employee.first_name, Employee.last_name, Employee.department_ids,
        required_total.label("required_total"), required_done.label("required_done"),
    ).join(AssignmentCampaign, AssignmentCampaign.id == Assignment.campaign_id
    ).join(Employee, Employee.id == Assignment.employee_id
    ).where(AssignmentCampaign.status == "active",
            AssignmentCampaign.target_type.in_(ACTIVE_TARGETS[context]))
    if search.strip():
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        revision_title = select(ArticleRevision.id).join(Article, Article.id == ArticleRevision.article_id
        ).where(ArticleRevision.id == AssignmentCampaign.target_id,
                Article.title.ilike(term, escape="\\")).exists()
        article_title = select(Article.id).where(Article.id == AssignmentCampaign.target_id,
            Article.title.ilike(term, escape="\\")).exists()
        test_title = select(TestDefinition.id).where(TestDefinition.id == AssignmentCampaign.target_id,
            TestDefinition.title.ilike(term, escape="\\")).exists()
        course_title = select(Course.id).where(Course.id == AssignmentCampaign.target_id,
            Course.title.ilike(term, escape="\\")).exists()
        query = query.where(or_(AssignmentCampaign.title.ilike(term, escape="\\"),
            Employee.first_name.ilike(term, escape="\\"),
            Employee.last_name.ilike(term, escape="\\"),
            (Employee.first_name + " " + Employee.last_name).ilike(term, escape="\\"),
            cast(Employee.bitrix_id, String).ilike(term, escape="\\"),
            cast(AssignmentCampaign.id, String).ilike(term, escape="\\"),
            revision_title, article_title, test_title, course_title))
    if department_id is not None:
        scope = department_scope(db, department_id)
        query = query.where(or_(*(Employee.department_ids.contains([value]) for value in scope)))
    if target_type:
        query = query.where(AssignmentCampaign.target_type == target_type)
    if mine:
        query = query.where(or_(AssignmentCampaign.created_by == mine.id,
            AssignmentCampaign.reviewer_ids.contains([mine.bitrix_id])))
    if reviewer_bitrix_id is not None:
        query = query.where(AssignmentCampaign.reviewer_ids.contains([reviewer_bitrix_id]))
    if revision_number is not None:
        matching_revision = select(ArticleRevision.id).where(
            ArticleRevision.id == AssignmentCampaign.target_id,
            ArticleRevision.revision_no == revision_number).exists()
        query = query.where(AssignmentCampaign.target_type == "article_revision", matching_revision)
    manual = select(AssignmentAction.id).where(AssignmentAction.assignment_id == Assignment.id,
        AssignmentAction.action == "confirm_complete").exists()
    test = select(TestAttempt.id).where(TestAttempt.assignment_id == Assignment.id,
        TestAttempt.status == "passed").exists()
    if confirmation_method == "manual":
        query = query.where(manual)
    elif confirmation_method == "test":
        query = query.where(test, ~manual)
    elif confirmation_method == "button":
        query = query.where(Assignment.status == "completed",
            AssignmentCampaign.target_type.in_(("article_revision", "course_article")), ~manual, ~test)
    if due_from:
        query = query.where(Assignment.due_at >= due_from)
    if due_to:
        query = query.where(Assignment.due_at <= due_to)
    if progress_band:
        progress = func.round(case((required_total > 0, 100.0 * required_done / required_total), else_=0.0))
        lower, upper = {
            "0": (0, 0), "1-25": (1, 25), "26-50": (26, 50),
            "51-75": (51, 75), "76-99": (76, 99), "100": (100, 100),
        }[progress_band]
        query = query.where(progress.between(lower, upper))
    if status == "overdue":
        query = query.where(Assignment.due_at < now, Assignment.status.not_in(FINISHED))
    elif status:
        query = query.where(Assignment.status == status)
    return query.subquery()


def metric_columns(source):
    overdue = and_(source.c.due_at < datetime.now(timezone.utc), source.c.status.not_in(FINISHED))
    return {
        "assignments": func.count(source.c.assignment_id),
        "completed": func.count(source.c.assignment_id).filter(source.c.status == "completed"),
        "not_started": func.count(source.c.assignment_id).filter(source.c.status == "not_started"),
        "in_progress": func.count(source.c.assignment_id).filter(source.c.status == "in_progress"),
        "pending_review": func.count(source.c.assignment_id).filter(source.c.status == "pending_review"),
        "returned": func.count(source.c.assignment_id).filter(source.c.status == "returned"),
        "exempted": func.count(source.c.assignment_id).filter(source.c.status == "exempted"),
        "overdue": func.count(source.c.assignment_id).filter(overdue),
        "required_total": func.coalesce(func.sum(source.c.required_total), 0),
        "required_done": func.coalesce(func.sum(source.c.required_done), 0),
        "average_progress": func.coalesce(func.avg(case(
            (source.c.required_total > 0, 100.0 * source.c.required_done / source.c.required_total),
            else_=0.0)), 0),
    }


@router.get("/overview")
def review_overview(context: str = Query(default="materials", pattern="^(materials|courses)$"),
                    group: str = Query(default="targets", pattern="^(targets|employees)$"),
                    search: str = Query(default="", max_length=240),
                    department_id: int | None = None,
                    status: str | None = Query(default=None, pattern="^(not_started|in_progress|pending_review|returned|completed|exempted|cancelled|overdue)$"),
                    target_type: str | None = Query(default=None, pattern="^(article_revision|course_article|course_test|course)$"),
                    due_from: datetime | None = None, due_to: datetime | None = None,
                    progress_band: str | None = Query(default=None, pattern="^(0|1-25|26-50|51-75|76-99|100)$"),
                    mine: bool = False,
                    reviewer_bitrix_id: int | None = Query(default=None, gt=0),
                    revision_number: int | None = Query(default=None, gt=0),
                    confirmation_method: str | None = Query(default=None, pattern="^(button|test|manual)$"),
                    limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0),
                    db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if target_type and target_type not in ACTIVE_TARGETS[context]:
        raise HTTPException(422, "Target type does not belong to this review area")
    if due_from and due_to and due_from > due_to:
        raise HTTPException(422, "Invalid deadline range")
    if progress_band and context != "courses":
        raise HTTPException(422, "Progress filter applies to courses only")
    if revision_number and context != "materials":
        raise HTTPException(422, "Revision filter applies to materials only")
    if confirmation_method and context != "materials":
        raise HTTPException(422, "Confirmation filter applies to materials only")
    source = filtered_assignments(db, context, search, department_id, status, target_type, due_from, due_to,
        progress_band, actor if mine else None, reviewer_bitrix_id, revision_number, confirmation_method)
    metrics = metric_columns(source)
    summary = db.execute(select(func.count(distinct(source.c.employee_id)).label("employees"),
        *(column.label(name) for name, column in metrics.items()))).mappings().one()
    if group == "targets":
        keys = (source.c.target_type, source.c.target_id)
        statement = select(*keys, *(column.label(name) for name, column in metrics.items())
        ).group_by(*keys)
        statement = statement.order_by(func.max(source.c.launched_at).desc().nullslast(), source.c.target_id)
    else:
        keys = (source.c.employee_id, source.c.bitrix_id, source.c.first_name,
                source.c.last_name, source.c.department_ids)
        statement = select(*keys, *(column.label(name) for name, column in metrics.items())
        ).group_by(*keys)
        statement = statement.order_by(source.c.last_name, source.c.first_name, source.c.employee_id)
    grouped = statement.subquery()
    total = db.scalar(select(func.count()).select_from(grouped)) or 0
    rows = db.execute(statement.limit(limit).offset(offset)).mappings().all()
    campaigns_by_target: dict[tuple[str, uuid.UUID], list[dict]] = {}
    if group == "targets" and rows:
        selected_ids = [row["target_id"] for row in rows]
        campaign_keys = (source.c.campaign_id, source.c.campaign_title, source.c.target_type,
            source.c.target_id, source.c.launched_at, source.c.campaign_due_at)
        campaign_rows = db.execute(select(*campaign_keys,
            *(column.label(name) for name, column in metrics.items()))
            .where(source.c.target_id.in_(selected_ids)).group_by(*campaign_keys)
            .order_by(source.c.launched_at.desc().nullslast(), source.c.campaign_id)).mappings().all()
        for campaign in campaign_rows:
            item = dict(campaign)
            key = (item["target_type"], item["target_id"])
            item["campaign_id"] = str(item["campaign_id"])
            item["target_id"] = str(item["target_id"])
            item["launched_at"] = item["launched_at"].isoformat() if item["launched_at"] else None
            item["campaign_due_at"] = item["campaign_due_at"].isoformat() if item["campaign_due_at"] else None
            item["completion_percent"] = round(100 * item["completed"] / item["assignments"]) if item["assignments"] else 0
            item["progress_percent"] = round(item["average_progress"]) if context == "courses" else 0
            campaigns_by_target.setdefault(key, []).append(item)
    titles: dict[uuid.UUID, tuple[str, int | None, str | None]] = {}
    if group == "targets":
        revision_ids = [row["target_id"] for row in rows if row["target_type"] == "article_revision"]
        for revision, article in db.execute(select(ArticleRevision, Article).join(
            Article, Article.id == ArticleRevision.article_id).where(ArticleRevision.id.in_(revision_ids))):
            titles[revision.id] = (article.title, revision.revision_no, revision.revision_date.isoformat())
        article_ids = [row["target_id"] for row in rows if row["target_type"] == "course_article"]
        for article in db.scalars(select(Article).where(Article.id.in_(article_ids))):
            titles[article.id] = (article.title, None, None)
        test_ids = [row["target_id"] for row in rows if row["target_type"] == "course_test"]
        for test in db.scalars(select(TestDefinition).where(TestDefinition.id.in_(test_ids))):
            titles[test.id] = (test.title, None, None)
        course_ids = [row["target_id"] for row in rows if row["target_type"] == "course"]
        for course in db.scalars(select(Course).where(Course.id.in_(course_ids))):
            titles[course.id] = (course.title, None, course.updated_at.isoformat())
    serialized = []
    for row in rows:
        data = dict(row)
        if group == "targets":
            campaigns = campaigns_by_target.get((row["target_type"], row["target_id"]), [])
            fallback = campaigns[0]["campaign_title"] if campaigns else "Материал"
            title, revision_no, revision_date = titles.get(row["target_id"], (fallback, None, None))
            data.update(target_title=title, revision_number=revision_no, revision_date=revision_date,
                campaigns=campaigns, campaign_count=len(campaigns))
        for key in ("campaign_id", "target_id", "employee_id"):
            if key in data:
                data[key] = str(data[key])
        for key in ("launched_at", "campaign_due_at"):
            if key in data and data[key] is not None:
                data[key] = data[key].isoformat()
        data["completion_percent"] = (round(100 * data["completed"] / data["assignments"])
            if data["assignments"] else 0)
        data["progress_percent"] = (round(100 * data["required_done"] / data["required_total"])
            if context == "courses" and group == "employees" and data["required_total"]
            else round(data["average_progress"]) if context == "courses" else 0)
        serialized.append(data)
    summary_data = dict(summary)
    if context == "courses":
        by_employee = select(source.c.employee_id,
            func.sum(source.c.required_done).label("done"),
            func.sum(source.c.required_total).label("total"),
        ).group_by(source.c.employee_id).subquery()
        mean = db.scalar(select(func.avg(case(
            (by_employee.c.total > 0, 100.0 * by_employee.c.done / by_employee.c.total),
            else_=0.0))))
        summary_data["progress_percent"] = round(mean or 0)
    else:
        summary_data["progress_percent"] = 0
    return {"context": context, "group": group, "summary": summary_data,
            "rows": serialized, "total": total, "offset": offset, "limit": limit}


@router.get("/assignments")
def review_assignments(context: str = Query(pattern="^(materials|courses)$"),
                       campaign_id: uuid.UUID | None = None, employee_id: uuid.UUID | None = None,
                       search: str = Query(default="", max_length=240),
                       department_id: int | None = None,
                       status: str | None = Query(default=None, pattern="^(not_started|in_progress|pending_review|returned|completed|exempted|cancelled|overdue)$"),
                       target_type: str | None = Query(default=None, pattern="^(article_revision|course_article|course_test|course)$"),
                       due_from: datetime | None = None, due_to: datetime | None = None,
                       progress_band: str | None = Query(default=None, pattern="^(0|1-25|26-50|51-75|76-99|100)$"),
                       mine: bool = False,
                       reviewer_bitrix_id: int | None = Query(default=None, gt=0),
                       revision_number: int | None = Query(default=None, gt=0),
                       confirmation_method: str | None = Query(default=None, pattern="^(button|test|manual)$"),
                       limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       db: Session = Depends(get_db), actor: Employee = Depends(require_role("teacher"))):
    if (campaign_id is None) == (employee_id is None):
        raise HTTPException(422, "Choose exactly one campaign or employee")
    if target_type and target_type not in ACTIVE_TARGETS[context]:
        raise HTTPException(422, "Target type does not belong to this review area")
    if due_from and due_to and due_from > due_to:
        raise HTTPException(422, "Invalid deadline range")
    if progress_band and context != "courses":
        raise HTTPException(422, "Progress filter applies to courses only")
    if revision_number and context != "materials":
        raise HTTPException(422, "Revision filter applies to materials only")
    if confirmation_method and context != "materials":
        raise HTTPException(422, "Confirmation filter applies to materials only")
    source = filtered_assignments(db, context, search, department_id, status, target_type, due_from, due_to,
        progress_band, actor if mine else None, reviewer_bitrix_id, revision_number, confirmation_method)
    query = select(source)
    if campaign_id is not None:
        query = query.where(source.c.campaign_id == campaign_id)
    else:
        query = query.where(source.c.employee_id == employee_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(source.c.launched_at.desc(), source.c.assignment_id)
        .limit(limit).offset(offset)).mappings().all()
    assignment_ids = [row["assignment_id"] for row in rows]
    manual_ids = set(db.scalars(select(AssignmentAction.assignment_id).where(
        AssignmentAction.assignment_id.in_(assignment_ids),
        AssignmentAction.action == "confirm_complete")).all()) if assignment_ids else set()
    attempts = db.scalars(select(TestAttempt).where(TestAttempt.assignment_id.in_(assignment_ids))
        .order_by(TestAttempt.started_at.desc())).all() if assignment_ids else []
    passed_ids = {attempt.assignment_id for attempt in attempts if attempt.status == "passed"}
    rewards = {row.attempt_id: row.points for row in db.scalars(select(TestCompletionReward).where(
        TestCompletionReward.assignment_id.in_(assignment_ids))).all()} if assignment_ids else {}
    review_ids = {row.attempt_id: row.id for row in db.scalars(select(ReviewTask).where(
        ReviewTask.attempt_id.in_([attempt.id for attempt in attempts]))).all()} if attempts else {}
    by_assignment: dict[uuid.UUID, list[dict]] = {}
    for attempt in attempts:
        by_assignment.setdefault(attempt.assignment_id, []).append({
            "id": str(attempt.id), "test_id": str(attempt.test_id),
            "course_item_id": str(attempt.course_item_id) if attempt.course_item_id else None,
            "status": attempt.status, "attempt_no": attempt.attempt_no,
            "correct_count": attempt.correct_count, "auto_count": attempt.auto_count,
            "reward_points": rewards.get(attempt.id, 0),
            "started_at": attempt.started_at.isoformat(),
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "review_id": str(review_ids[attempt.id]) if attempt.id in review_ids else None,
        })
    result = []
    reviewer_ids = {int(value) for row in rows for value in row["reviewer_ids"] if str(value).isdigit()}
    reviewer_names = {person.bitrix_id: f"{person.first_name} {person.last_name}".strip()
        for person in db.scalars(select(Employee).where(Employee.bitrix_id.in_(reviewer_ids))).all()}
    target_titles: dict[uuid.UUID, tuple[str, int | None]] = {}
    revision_ids = [row["target_id"] for row in rows if row["target_type"] == "article_revision"]
    for revision, article in db.execute(select(ArticleRevision, Article).join(
        Article, Article.id == ArticleRevision.article_id).where(ArticleRevision.id.in_(revision_ids))):
        target_titles[revision.id] = (article.title, revision.revision_no)
    article_ids = [row["target_id"] for row in rows if row["target_type"] == "course_article"]
    for article in db.scalars(select(Article).where(Article.id.in_(article_ids))):
        target_titles[article.id] = (article.title, None)
    test_ids = [row["target_id"] for row in rows if row["target_type"] == "course_test"]
    for test in db.scalars(select(TestDefinition).where(TestDefinition.id.in_(test_ids))):
        target_titles[test.id] = (test.title, None)
    course_ids = [row["target_id"] for row in rows if row["target_type"] == "course"]
    for course in db.scalars(select(Course).where(Course.id.in_(course_ids))):
        target_titles[course.id] = (course.title, None)
    now = datetime.now(timezone.utc)
    for row in rows:
        target_title, revision_no = target_titles.get(row["target_id"], (row["campaign_title"], None))
        method = ("manual" if row["assignment_id"] in manual_ids else
            "test" if row["assignment_id"] in passed_ids else
            "button" if row["status"] == "completed" and row["target_type"] in ("article_revision", "course_article")
            else None)
        result.append({
            "id": str(row["assignment_id"]), "campaign_id": str(row["campaign_id"]),
            "campaign_title": row["campaign_title"], "target_type": row["target_type"],
            "target_id": str(row["target_id"]), "employee_id": str(row["employee_id"]),
            "target_title": target_title, "revision_number": revision_no,
            "reviewer_names": [reviewer_names[int(value)] for value in row["reviewer_ids"]
                if str(value).isdigit() and int(value) in reviewer_names],
            "confirmation_method": method,
            "bitrix_id": row["bitrix_id"],
            "employee_name": f'{row["first_name"]} {row["last_name"]}'.strip(),
            "department_ids": row["department_ids"], "status": row["status"],
            "is_overdue": bool(row["due_at"] and row["due_at"] < now and row["status"] not in FINISHED),
            "assigned_at": row["assigned_at"].isoformat(),
            "due_at": row["due_at"].isoformat() if row["due_at"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "attempts": by_assignment.get(row["assignment_id"], []),
        })
    return {"rows": result, "total": total, "offset": offset, "limit": limit}


@router.get("/assignments/{assignment_id}")
def review_assignment_detail(assignment_id: uuid.UUID, db: Session = Depends(get_db),
                             _actor: Employee = Depends(require_role("teacher"))):
    assignment = db.get(Assignment, assignment_id)
    campaign = db.get(AssignmentCampaign, assignment.campaign_id) if assignment else None
    if campaign is None or campaign.status != "active":
        raise HTTPException(404)
    employee = db.get(Employee, assignment.employee_id)
    department_titles = [row.title for row in db.scalars(select(Department).where(
        Department.bitrix_id.in_(employee.department_ids))).all()]
    actions = db.scalars(select(AssignmentAction).where(AssignmentAction.assignment_id == assignment.id)
        .order_by(AssignmentAction.occurred_at.desc())).all()
    attempts = db.scalars(select(TestAttempt).where(TestAttempt.assignment_id == assignment.id)
        .order_by(TestAttempt.started_at.desc())).all()
    rewards = {row.attempt_id: row.points for row in db.scalars(select(TestCompletionReward).where(
        TestCompletionReward.assignment_id == assignment.id)).all()}
    reviews = {row.attempt_id: row for row in db.scalars(select(ReviewTask).where(
        ReviewTask.attempt_id.in_([attempt.id for attempt in attempts]))).all()} if attempts else {}
    target_title = campaign.title
    revision = None
    course = None
    course_updated_at = None
    sections = []
    required_total = required_done = 0
    if campaign.target_type == "article_revision":
        revision = db.get(ArticleRevision, campaign.target_id)
        article = db.get(Article, revision.article_id) if revision else None
        target_title = article.title if article else campaign.title
    elif campaign.target_type == "course":
        course = db.get(Course, campaign.target_id)
        target_title = course.title if course else campaign.title
        if course:
            course_updated_at = course.updated_at.isoformat()
            course_sections = db.scalars(select(CourseSection).where(CourseSection.course_id == course.id)
                .order_by(CourseSection.position)).all()
            items = db.scalars(select(CourseItem).where(CourseItem.course_id == course.id)
                .order_by(CourseItem.position)).all()
            done = {row.course_item_id: row.completed_at for row in db.scalars(select(ItemCompletion).where(
                ItemCompletion.assignment_id == assignment.id)).all()}
            required_total = sum(item.required for item in items)
            required_done = sum(item.required and item.id in done for item in items)
            article_ids = [item.article_id for item in items if item.article_id]
            test_ids = [item.test_id for item in items if item.test_id]
            articles = {row.id: row.title for row in db.scalars(select(Article).where(
                Article.id.in_(article_ids))).all()} if article_ids else {}
            tests = {row.id: row.title for row in db.scalars(select(TestDefinition).where(
                TestDefinition.id.in_(test_ids))).all()} if test_ids else {}
            sections = [{"id": str(section.id), "title": section.title,
                "items": [{"id": str(item.id), "kind": item.kind,
                    "title": articles.get(item.article_id) if item.article_id else tests.get(item.test_id, "Тест"),
                    "required": item.required, "completed_at": done[item.id].isoformat() if item.id in done else None}
                    for item in items if item.section_id == section.id]}
                for section in course_sections]
    elif campaign.target_type == "course_article":
        article = db.get(Article, campaign.target_id)
        target_title = article.title if article else campaign.title
    elif campaign.target_type == "course_test":
        test = db.get(TestDefinition, campaign.target_id)
        target_title = test.title if test else campaign.title
    now = datetime.now(timezone.utc)
    return {
        "id": str(assignment.id), "campaign_id": str(campaign.id), "campaign_title": campaign.title,
        "target_type": campaign.target_type, "target_title": target_title,
        "revision_number": revision.revision_no if revision else None,
        "revision_date": revision.revision_date.isoformat() if revision else None,
        "course_updated_at": course_updated_at,
        "employee_id": str(employee.id), "employee_name": f"{employee.first_name} {employee.last_name}".strip(),
        "bitrix_id": employee.bitrix_id, "department_ids": employee.department_ids,
        "department_titles": department_titles,
        "status": assignment.status,
        "is_overdue": bool(assignment.due_at and assignment.due_at < now and assignment.status not in FINISHED),
        "assigned_at": assignment.assigned_at.isoformat(),
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
        "required_total": required_total, "required_done": required_done,
        "sections": sections,
        "attempts": [{"id": str(attempt.id), "attempt_no": attempt.attempt_no,
            "course_item_id": str(attempt.course_item_id) if attempt.course_item_id else None,
            "status": attempt.status, "correct_count": attempt.correct_count,
            "auto_count": attempt.auto_count, "reward_points": rewards.get(attempt.id, 0),
            "started_at": attempt.started_at.isoformat(),
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "review_id": str(reviews[attempt.id].id) if attempt.id in reviews else None}
            for attempt in attempts],
        "history": [{"id": str(action.id), "action": action.action, "reason": action.reason,
            "details": action.details, "occurred_at": action.occurred_at.isoformat()}
            for action in actions],
    }
