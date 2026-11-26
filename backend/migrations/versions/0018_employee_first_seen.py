"""Track the first Bitrix directory observation for dynamic campaign recipients.

Revision ID: 0018_employee_first_seen
Revises: 0017_test_corrections_rewards
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_employee_first_seen"
down_revision = "0017_test_corrections_rewards"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("first_seen_at", sa.DateTime(timezone=True),
        nullable=False, server_default=sa.text("'1970-01-01 00:00:00+00'::timestamptz")), schema="identity")
    op.alter_column("employees", "first_seen_at", server_default=sa.text("now()"), schema="identity")


def downgrade():
    op.drop_column("employees", "first_seen_at", schema="identity")
