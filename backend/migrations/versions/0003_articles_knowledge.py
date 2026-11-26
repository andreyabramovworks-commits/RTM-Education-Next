"""Create articles, revisions, knowledge folders and allow grants.

Revision ID: 0003_articles_knowledge
Revises: 0002_courses
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_articles_knowledge"
down_revision = "0002_courses"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS content")
    op.execute("CREATE SCHEMA IF NOT EXISTS knowledge")
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.courses.id")),
        sa.Column("copied_from_article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.articles.id")),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="content",
    )
    op.create_table(
        "article_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.articles.id"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("revision_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("body_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "revision_no"),
        sa.UniqueConstraint("article_id", "revision_date"),
        schema="content",
    )
    op.create_table(
        "knowledge_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge.knowledge_folders.id")),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True)),
        schema="knowledge",
    )
    op.create_table(
        "knowledge_folder_articles",
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.articles.id"), primary_key=True),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge.knowledge_folders.id"), nullable=False),
        schema="knowledge",
    )
    op.create_index("ix_folder_articles_folder", "knowledge_folder_articles", ["folder_id"], schema="knowledge")
    op.create_table(
        "knowledge_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(20), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.UniqueConstraint("target_type", "target_id", "subject_type", "subject_id"),
        sa.CheckConstraint("target_type IN ('folder','article')", name="ck_grant_target"),
        sa.CheckConstraint("subject_type IN ('employee','department')", name="ck_grant_subject"),
        schema="knowledge",
    )
    op.create_index("ix_grants_subject", "knowledge_access_grants", ["subject_type", "subject_id"], schema="knowledge")


def downgrade():
    op.drop_index("ix_grants_subject", table_name="knowledge_access_grants", schema="knowledge")
    op.drop_table("knowledge_access_grants", schema="knowledge")
    op.drop_index("ix_folder_articles_folder", table_name="knowledge_folder_articles", schema="knowledge")
    op.drop_table("knowledge_folder_articles", schema="knowledge")
    op.drop_table("knowledge_folders", schema="knowledge")
    op.drop_table("article_revisions", schema="content")
    op.drop_table("articles", schema="content")
    op.execute("DROP SCHEMA knowledge")
    op.execute("DROP SCHEMA content")
