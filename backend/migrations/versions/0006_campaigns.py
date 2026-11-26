"""Add campaigns, individual assignments and durable integration outbox.

Revision ID: 0006_campaigns
Revises: 0005_course_items
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_campaigns"
down_revision = "0005_course_items"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")
    op.create_table(
        "assignment_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("recipient_policy", postgresql.JSONB(), nullable=False),
        sa.Column("reviewer_ids", postgresql.JSONB(), nullable=False),
        sa.Column("due_mode", sa.String(20), nullable=False),
        sa.Column("due_days", sa.Integer()),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("notify_enabled", sa.Boolean(), nullable=False),
        sa.Column("task_enabled", sa.Boolean(), nullable=False),
        sa.Column("task_title", sa.String(240), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("launched_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("target_type IN ('course','course_article','course_test','article_revision')", name="ck_campaign_target"),
        sa.CheckConstraint("status IN ('draft','active','completed','closed','cancelled')", name="ck_campaign_status"),
        sa.CheckConstraint("due_mode IN ('relative','absolute')", name="ck_campaign_due_mode"),
        schema="learning",
    )
    op.create_table(
        "assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignment_campaigns.id"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("recipient_source", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("campaign_id", "employee_id"),
        sa.CheckConstraint("status IN ('not_started','in_progress','pending_review','returned','completed','exempted','cancelled')", name="ck_assignment_status"),
        schema="learning",
    )
    op.create_index("ix_assignments_employee", "assignments", ["employee_id", "assigned_at"], schema="learning")
    op.create_table(
        "outbox_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
        schema="integration",
    )
    op.create_index("ix_outbox_ready", "outbox_jobs", ["status", "next_run_at"], schema="integration")


def downgrade():
    op.drop_index("ix_outbox_ready", table_name="outbox_jobs", schema="integration")
    op.drop_table("outbox_jobs", schema="integration")
    op.drop_index("ix_assignments_employee", table_name="assignments", schema="learning")
    op.drop_table("assignments", schema="learning")
    op.drop_table("assignment_campaigns", schema="learning")
    op.execute("DROP SCHEMA integration")
