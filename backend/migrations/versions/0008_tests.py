"""Create test definitions, questions, options and immutable attempt snapshots.

Revision ID: 0008_tests
Revises: 0007_progress
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_tests"
down_revision = "0007_progress"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("test_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.courses.id")),
        sa.Column("article_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.article_revisions.id")),
        sa.Column("title", sa.String(240), nullable=False), sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("time_limit_minutes", sa.Integer()), sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("min_correct", sa.Integer(), nullable=False),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False), sa.Column("shuffle_options", sa.Boolean(), nullable=False),
        sa.Column("show_results", sa.Boolean(), nullable=False), sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(owner_course_id IS NOT NULL) <> (article_revision_id IS NOT NULL)", name="ck_test_owner"),
        schema="content")
    op.create_table("test_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.test_definitions.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False), sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("image_asset_id", postgresql.UUID(as_uuid=True)),
        sa.UniqueConstraint("test_id", "position"),
        sa.CheckConstraint("kind IN ('single','multiple','free_text')", name="ck_test_question_kind"),
        schema="content")
    op.create_table("test_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.test_questions.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False), sa.Column("image_asset_id", postgresql.UUID(as_uuid=True)),
        sa.UniqueConstraint("question_id", "position"), schema="content")
    op.create_table("test_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignments.id"), nullable=False),
        sa.Column("course_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.course_items.id")),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.test_definitions.id"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True)), sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("correct_count", sa.Integer()), sa.Column("auto_count", sa.Integer()),
        sa.Column("min_correct_snapshot", sa.Integer(), nullable=False),
        sa.Column("show_results_snapshot", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("assignment_id", "course_item_id", "attempt_no"),
        sa.CheckConstraint("status IN ('in_progress','pending_review','returned','passed','failed','expired')", name="ck_test_attempt_status"),
        schema="learning")
    op.create_table("attempt_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.test_attempts.id"), nullable=False),
        sa.Column("source_question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False), sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("options_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("correct_option_ids", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("attempt_id", "position"), schema="learning")
    op.create_table("answer_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.attempt_questions.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("is_correct", sa.Boolean()), sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("attempt_question_id", "version"), schema="learning")


def downgrade():
    op.drop_table("answer_submissions", schema="learning")
    op.drop_table("attempt_questions", schema="learning")
    op.drop_table("test_attempts", schema="learning")
    op.drop_table("test_options", schema="content")
    op.drop_table("test_questions", schema="content")
    op.drop_table("test_definitions", schema="content")
