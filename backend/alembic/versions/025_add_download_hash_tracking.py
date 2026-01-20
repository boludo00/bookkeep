"""add download hash tracking

Revision ID: 025
Revises: 024
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    # Add hash field to download_tasks for tracking unique downloads
    op.add_column('download_tasks', sa.Column('info_hash', sa.String(length=64), nullable=True))
    op.create_index('ix_download_tasks_info_hash', 'download_tasks', ['info_hash'])

    # Add downloaded release hashes to books table for quick lookups
    op.add_column('books', sa.Column('downloaded_release_hashes', sa.Text(), nullable=True))


def downgrade():
    op.drop_index('ix_download_tasks_info_hash', table_name='download_tasks')
    op.drop_column('download_tasks', 'info_hash')
    op.drop_column('books', 'downloaded_release_hashes')
