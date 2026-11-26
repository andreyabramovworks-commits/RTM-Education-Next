"""Add review tasks, draft decisions and append-only review history.

Revision ID: 0009_review
Revises: 0008_tests
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_review"
down_revision = "0008_tests"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS review")
    op.create_table("review_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.test_attempts.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("claimed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id")),
        sa.Column("draft", postgresql.JSONB(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("attempt_id"),
        sa.CheckConstraint("status IN ('pending','claimed','returned','completed')", name="ck_review_task_status"),
        schema="review")
    op.create_table("answer_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.answer_submissions.id"), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('accepted','rejected')", name="ck_answer_review_decision"),
        schema="review")
    op.create_table("review_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("review.review_tasks.id"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), schema="review")
    op.create_index("ix_review_tasks_status", "review_tasks", ["status", "updated_at"], schema="review")


def downgrade():
    op.drop_index("ix_review_tasks_status", table_name="review_tasks", schema="review")
    op.drop_table("review_actions", schema="review")
    op.drop_table("answer_reviews", schema="review")
    op.drop_table("review_tasks", schema="review")
    op.execute("DROP SCHEMA review")
