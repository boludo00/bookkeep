"""Add download paths and categories

Revision ID: 024
Revises: 023
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Add ebook_category and audiobook_category to download_clients
    if not column_exists('download_clients', 'ebook_category'):
        op.add_column('download_clients', sa.Column('ebook_category', sa.String(), nullable=True))
    if not column_exists('download_clients', 'audiobook_category'):
        op.add_column('download_clients', sa.Column('audiobook_category', sa.String(), nullable=True))


def downgrade():
    if column_exists('download_clients', 'audiobook_category'):
        op.drop_column('download_clients', 'audiobook_category')
    if column_exists('download_clients', 'ebook_category'):
        op.drop_column('download_clients', 'ebook_category')
