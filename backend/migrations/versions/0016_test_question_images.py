"""Preserve question images in historical attempt snapshots.

Revision ID: 0016_test_question_images
Revises: 0015_revision_attempt_allowances
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_test_question_images"
down_revision = "0015_revision_attempt_allowances"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("attempt_questions", sa.Column("image_asset_id", postgresql.UUID(as_uuid=True)), schema="learning")
    op.drop_constraint("ck_media_kind", "media_assets", schema="content", type_="check")
    op.create_check_constraint("ck_media_kind", "media_assets", "kind IN ('video','audio','image')", schema="content")


def downgrade():
    op.drop_constraint("ck_media_kind", "media_assets", schema="content", type_="check")
    op.create_check_constraint("ck_media_kind", "media_assets", "kind IN ('video','audio')", schema="content")
    op.drop_column("attempt_questions", "image_asset_id", schema="learning")
