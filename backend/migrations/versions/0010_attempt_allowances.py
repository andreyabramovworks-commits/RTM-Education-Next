"""Add append-only individual attempt allowances.

Revision ID: 0010_attempt_allowances
Revises: 0009_review
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_attempt_allowances"
down_revision = "0009_review"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("attempt_allowances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignments.id"), nullable=False),
        sa.Column("course_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.course_items.id"), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("delta > 0 AND delta <= 100", name="ck_attempt_allowance_delta"),
        schema="learning")


def downgrade():
    op.drop_table("attempt_allowances", schema="learning")
