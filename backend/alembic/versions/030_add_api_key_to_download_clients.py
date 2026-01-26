"""add api_key to download_clients

Revision ID: 030
Revises: 029
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '030'
down_revision = '029'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add api_key column to download_clients table
    if not column_exists('download_clients', 'api_key'):
        op.add_column('download_clients', sa.Column('api_key', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove api_key column
    if column_exists('download_clients', 'api_key'):
        op.drop_column('download_clients', 'api_key')
