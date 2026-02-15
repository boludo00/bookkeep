"""add audiobookshelf_servers table and audiobookshelf_id to books

Revision ID: 033
Revises: 032
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not table_exists('audiobookshelf_servers'):
        op.create_table(
            'audiobookshelf_servers',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('url', sa.String(), nullable=False),
            sa.Column('api_key', sa.String(), nullable=False),
            sa.Column('is_default', sa.Boolean(), server_default='false'),
            sa.Column('library_id', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        )

    if not column_exists('books', 'audiobookshelf_id'):
        op.add_column('books', sa.Column('audiobookshelf_id', sa.String(), nullable=True))
        op.create_index('ix_books_audiobookshelf_id', 'books', ['audiobookshelf_id'], unique=True)


def downgrade() -> None:
    if column_exists('books', 'audiobookshelf_id'):
        op.drop_index('ix_books_audiobookshelf_id', table_name='books')
        op.drop_column('books', 'audiobookshelf_id')

    if table_exists('audiobookshelf_servers'):
        op.drop_table('audiobookshelf_servers')
