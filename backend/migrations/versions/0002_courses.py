"""Create live courses and one-level sections.

Revision ID: 0002_courses
Revises: 0001_identity
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_courses"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS learning")
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('free','sequential')", name="ck_courses_mode"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_courses_status"),
        schema="learning",
    )
    op.create_table(
        "course_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.courses.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("course_id", "position"),
        schema="learning",
    )


def downgrade():
    op.drop_table("course_sections", schema="learning")
    op.drop_table("courses", schema="learning")
    op.execute("DROP SCHEMA learning")
