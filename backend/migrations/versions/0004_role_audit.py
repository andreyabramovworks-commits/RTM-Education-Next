"""Create append-only role assignment audit.

Revision ID: 0004_role_audit
Revises: 0003_articles_knowledge
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_role_audit"
down_revision = "0003_articles_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.create_table(
        "role_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("old_role", sa.String(20), nullable=False),
        sa.Column("new_role", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        schema="audit",
    )
    op.create_index("ix_role_changes_employee", "role_changes", ["employee_id", "changed_at"], schema="audit")


def downgrade():
    op.drop_index("ix_role_changes_employee", table_name="role_changes", schema="audit")
    op.drop_table("role_changes", schema="audit")
    op.execute("DROP SCHEMA audit")
