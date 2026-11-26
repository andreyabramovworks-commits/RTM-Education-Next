"""Create identity schema and server sessions.

Revision ID: 0001_identity
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bitrix_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("first_name", sa.String(160), nullable=False),
        sa.Column("last_name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("bitrix_admin", sa.Boolean(), nullable=False),
        sa.Column("local_role", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="identity",
    )
    op.create_table(
        "browser_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="identity",
    )
    op.create_index("ix_sessions_expires_at", "browser_sessions", ["expires_at"], schema="identity")


def downgrade():
    op.drop_index("ix_sessions_expires_at", table_name="browser_sessions", schema="identity")
    op.drop_table("browser_sessions", schema="identity")
    op.drop_table("employees", schema="identity")
    op.execute("DROP SCHEMA identity")
