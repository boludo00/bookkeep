"""add url_base to download_clients

Revision ID: 031
Revises: 030
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add url_base column to download_clients table
    if not column_exists('download_clients', 'url_base'):
        op.add_column('download_clients', sa.Column('url_base', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove url_base column
    if column_exists('download_clients', 'url_base'):
        op.drop_column('download_clients', 'url_base')
