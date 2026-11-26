"""Retain published revision evidence when an administrator withdraws a revision.

Revision ID: 0019_revision_soft_delete
Revises: 0018_employee_first_seen
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0019_revision_soft_delete"
down_revision = "0018_employee_first_seen"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("article_revisions", sa.Column("deleted_at", sa.DateTime(timezone=True)), schema="content")
    op.add_column("article_revisions", sa.Column("deleted_by", UUID(as_uuid=True)), schema="content")
    op.add_column("article_revisions", sa.Column("delete_reason", sa.Text()), schema="content")
    op.create_foreign_key("fk_article_revisions_deleted_by", "article_revisions", "employees",
        ["deleted_by"], ["id"], source_schema="content", referent_schema="identity")


def downgrade():
    op.drop_constraint("fk_article_revisions_deleted_by", "article_revisions", schema="content", type_="foreignkey")
    op.drop_column("article_revisions", "delete_reason", schema="content")
    op.drop_column("article_revisions", "deleted_by", schema="content")
    op.drop_column("article_revisions", "deleted_at", schema="content")
