"""Allow individual attempts for revision tests outside a course.

Revision ID: 0015_revision_attempt_allowances
Revises: 0014_outbox_delivery
"""
from alembic import op

revision = "0015_revision_attempt_allowances"
down_revision = "0014_outbox_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("attempt_allowances", "course_item_id", nullable=True, schema="learning")


def downgrade():
    op.alter_column("attempt_allowances", "course_item_id", nullable=False, schema="learning")
