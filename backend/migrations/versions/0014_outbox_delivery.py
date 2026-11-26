"""Track confirmed Bitrix delivery identifiers.

Revision ID: 0014_outbox_delivery
Revises: 0013_media
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_outbox_delivery"
down_revision = "0013_media"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("outbox_jobs", sa.Column("external_id", sa.String(120)), schema="integration")


def downgrade():
    op.drop_column("outbox_jobs", "external_id", schema="integration")
