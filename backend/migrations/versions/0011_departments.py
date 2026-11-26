"""Store Bitrix24 department tree and user membership.

Revision ID: 0011_departments
Revises: 0010_attempt_allowances
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_departments"
down_revision = "0010_attempt_allowances"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("department_ids", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb")), schema="identity")
    op.create_table("departments",
        sa.Column("bitrix_id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), schema="identity")
    op.execute("ALTER TABLE knowledge.knowledge_access_grants DROP CONSTRAINT ck_grant_subject")
    op.create_check_constraint("ck_grant_subject", "knowledge_access_grants",
        "subject_type IN ('employee','department','subdepartment')", schema="knowledge")


def downgrade():
    op.drop_constraint("ck_grant_subject", "knowledge_access_grants", schema="knowledge")
    op.create_check_constraint("ck_grant_subject", "knowledge_access_grants",
        "subject_type IN ('employee','department')", schema="knowledge")
    op.drop_table("departments", schema="identity")
    op.drop_column("employees", "department_ids", schema="identity")
