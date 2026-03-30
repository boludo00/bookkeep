"""add annas_archive_language to direct_download_settings

Revision ID: 037
Revises: 036
Create Date: 2026-03-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('direct_download_settings', sa.Column('annas_archive_language', sa.String(), nullable=True))


def downgrade():
    op.drop_column('direct_download_settings', 'annas_archive_language')
