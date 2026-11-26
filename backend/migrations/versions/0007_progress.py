"""Track acknowledgement per assigned course item and article revision.

Revision ID: 0007_progress
Revises: 0006_campaigns
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_progress"
down_revision = "0006_campaigns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "item_completions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignments.id"), nullable=False),
        sa.Column("course_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.course_items.id"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.UniqueConstraint("assignment_id", "course_item_id"),
        schema="learning",
    )
    op.create_table(
        "revision_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignments.id"), nullable=False),
        sa.Column("article_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.article_revisions.id"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.UniqueConstraint("assignment_id"),
        schema="learning",
    )


def downgrade():
    op.drop_table("revision_acknowledgements", schema="learning")
    op.drop_table("item_completions", schema="learning")
