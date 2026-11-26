"""Add stable course items for articles and tests.

Revision ID: 0005_course_items
Revises: 0004_role_audit
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_course_items"
down_revision = "0004_role_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "course_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.courses.id"), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.course_sections.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.articles.id")),
        sa.Column("test_id", postgresql.UUID(as_uuid=True)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("section_id", "position"),
        sa.CheckConstraint("kind IN ('article','test')", name="ck_course_item_kind"),
        schema="learning",
    )
    op.create_index("ix_course_items_course", "course_items", ["course_id"], schema="learning")


def downgrade():
    op.drop_index("ix_course_items_course", table_name="course_items", schema="learning")
    op.drop_table("course_items", schema="learning")
