"""add client state tracking

Revision ID: 026
Revises: 025
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Add client_state field to download_tasks for storing raw client state (e.g., "stalledDL", "uploading")
    if not column_exists('download_tasks', 'client_state'):
        op.add_column('download_tasks', sa.Column('client_state', sa.String(length=50), nullable=True))


def downgrade():
    if column_exists('download_tasks', 'client_state'):
        op.drop_column('download_tasks', 'client_state')
