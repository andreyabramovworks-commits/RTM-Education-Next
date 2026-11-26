"""Bounded free-answer corrections and one reward per assignment/test.

Revision ID: 0017_test_corrections_rewards
Revises: 0016_test_question_images
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_test_corrections_rewards"
down_revision = "0016_test_question_images"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_definitions", sa.Column("reward_points", sa.Integer(), nullable=False, server_default="0"), schema="content")
    op.add_column("test_definitions", sa.Column("correction_days", sa.Integer(), nullable=False, server_default="7"), schema="content")
    op.add_column("test_attempts", sa.Column("reward_points_snapshot", sa.Integer(), nullable=False, server_default="0"), schema="learning")
    op.add_column("test_attempts", sa.Column("correction_days_snapshot", sa.Integer(), nullable=False, server_default="7"), schema="learning")
    op.add_column("test_attempts", sa.Column("correction_deadline_at", sa.DateTime(timezone=True)), schema="learning")
    op.create_table("test_completion_rewards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.assignments.id"), nullable=False),
        sa.Column("test_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("content.test_definitions.id"), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning.test_attempts.id"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assignment_id", "test_id"), schema="learning")


def downgrade():
    op.drop_table("test_completion_rewards", schema="learning")
    op.drop_column("test_attempts", "correction_deadline_at", schema="learning")
    op.drop_column("test_attempts", "correction_days_snapshot", schema="learning")
    op.drop_column("test_attempts", "reward_points_snapshot", schema="learning")
    op.drop_column("test_definitions", "correction_days", schema="content")
    op.drop_column("test_definitions", "reward_points", schema="content")
