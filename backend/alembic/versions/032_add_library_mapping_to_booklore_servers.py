"""add library mapping to booklore_servers

Revision ID: 032
Revises: 030
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '032'
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
    if not column_exists('booklore_servers', 'ebook_library_id'):
        op.add_column('booklore_servers', sa.Column('ebook_library_id', sa.Integer(), nullable=True))
    if not column_exists('booklore_servers', 'audiobook_library_id'):
        op.add_column('booklore_servers', sa.Column('audiobook_library_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    if column_exists('booklore_servers', 'audiobook_library_id'):
        op.drop_column('booklore_servers', 'audiobook_library_id')
    if column_exists('booklore_servers', 'ebook_library_id'):
        op.drop_column('booklore_servers', 'ebook_library_id')
