"""Add ebook_available and audiobook_available to books

Revision ID: 016
Revises: 015
Create Date: 2025-01-01

"""
from alembic import op
import sqlalchemy as sa


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns

# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    if not _column_exists("books", "ebook_available"):
        with op.batch_alter_table('books', schema=None) as batch_op:
            batch_op.add_column(sa.Column('ebook_available', sa.Boolean(), nullable=True))

    if not _column_exists("books", "audiobook_available"):
        with op.batch_alter_table('books', schema=None) as batch_op:
            batch_op.add_column(sa.Column('audiobook_available', sa.Boolean(), nullable=True))

    if _column_exists("books", "ebook_available"):
        op.execute("UPDATE books SET ebook_available = is_available WHERE is_available = TRUE")
        op.execute("UPDATE books SET ebook_available = FALSE WHERE ebook_available IS NULL")

    if _column_exists("books", "audiobook_available"):
        op.execute("UPDATE books SET audiobook_available = FALSE WHERE audiobook_available IS NULL")

    with op.batch_alter_table('books', schema=None) as batch_op:
        if _column_exists("books", "ebook_available"):
            batch_op.alter_column(
                'ebook_available',
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        if _column_exists("books", "audiobook_available"):
            batch_op.alter_column(
                'audiobook_available',
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )


def downgrade():
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.drop_column('audiobook_available')
        batch_op.drop_column('ebook_available')
