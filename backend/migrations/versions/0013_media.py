"""Private video and audio assets.

Revision ID: 0013_media
Revises: 0012_assignment_actions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_media"
down_revision = "0012_assignment_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("original_filename", sa.String(240), nullable=False),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("byte_length", sa.Integer()),
        sa.Column("storage_path", sa.Text()),
        sa.Column("rutube_url", sa.Text()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('video','audio')", name="ck_media_kind"),
        sa.CheckConstraint("source_type IN ('upload','rutube')", name="ck_media_source"),
        schema="content")


def downgrade():
    op.drop_table("media_assets", schema="content")
