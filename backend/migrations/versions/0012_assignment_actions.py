"""Audit individual assignment decisions.

Revision ID: 0012_assignment_actions
Revises: 0011_departments
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_assignment_actions"
down_revision = "0011_departments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assignment_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignments.id"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), schema="audit")
    op.create_index("ix_assignment_actions_assignment", "assignment_actions", ["assignment_id", "occurred_at"], schema="audit")


def downgrade():
    op.drop_index("ix_assignment_actions_assignment", table_name="assignment_actions", schema="audit")
    op.drop_table("assignment_actions", schema="audit")
