"""add download hash tracking

Revision ID: 025
Revises: 024
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade():
    # Add hash field to download_tasks for tracking unique downloads
    if not column_exists('download_tasks', 'info_hash'):
        op.add_column('download_tasks', sa.Column('info_hash', sa.String(length=64), nullable=True))
    if not index_exists('download_tasks', 'ix_download_tasks_info_hash'):
        op.create_index('ix_download_tasks_info_hash', 'download_tasks', ['info_hash'])

    # Add downloaded release hashes to books table for quick lookups
    if not column_exists('books', 'downloaded_release_hashes'):
        op.add_column('books', sa.Column('downloaded_release_hashes', sa.Text(), nullable=True))


def downgrade():
    if index_exists('download_tasks', 'ix_download_tasks_info_hash'):
        op.drop_index('ix_download_tasks_info_hash', table_name='download_tasks')
    if column_exists('download_tasks', 'info_hash'):
        op.drop_column('download_tasks', 'info_hash')
    if column_exists('books', 'downloaded_release_hashes'):
        op.drop_column('books', 'downloaded_release_hashes')
