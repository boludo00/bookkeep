"""add import status tracking

Revision ID: 027
Revises: 026
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Add import_status field to track import state
    # Values: 'pending', 'importing', 'imported', 'failed', 'skipped'
    if not column_exists('download_tasks', 'import_status'):
        op.add_column('download_tasks', sa.Column('import_status', sa.String(length=20), nullable=True, server_default='pending'))

    # Add import_message for error messages or details
    if not column_exists('download_tasks', 'import_message'):
        op.add_column('download_tasks', sa.Column('import_message', sa.String(length=500), nullable=True))

    # Add imported_at timestamp
    if not column_exists('download_tasks', 'imported_at'):
        op.add_column('download_tasks', sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True))

    # Update existing completed tasks to 'imported' status
    op.execute("UPDATE download_tasks SET import_status = 'imported' WHERE state IN ('complete', 'seeding') AND import_status IS NULL")


def downgrade():
    if column_exists('download_tasks', 'imported_at'):
        op.drop_column('download_tasks', 'imported_at')
    if column_exists('download_tasks', 'import_message'):
        op.drop_column('download_tasks', 'import_message')
    if column_exists('download_tasks', 'import_status'):
        op.drop_column('download_tasks', 'import_status')
