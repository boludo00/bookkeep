"""add prowlarr indexer filter

Revision ID: 029
Revises: 028
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '029'
down_revision = '028'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add indexer_ids_json column to prowlarr_servers table
    if not column_exists('prowlarr_servers', 'indexer_ids_json'):
        op.add_column('prowlarr_servers', sa.Column('indexer_ids_json', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove indexer_ids_json column
    if column_exists('prowlarr_servers', 'indexer_ids_json'):
        op.drop_column('prowlarr_servers', 'indexer_ids_json')
