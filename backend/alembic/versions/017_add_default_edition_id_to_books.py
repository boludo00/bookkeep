"""add_default_edition_id_to_books

Revision ID: 017
Revises: 016
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "books" not in inspector.get_table_names():
        return

    existing_columns = [col["name"] for col in inspector.get_columns("books")]
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("books")]

    if "default_edition_id" not in existing_columns:
        op.add_column("books", sa.Column("default_edition_id", sa.Integer(), nullable=True))

    if "default_edition_id" in existing_columns and "ix_books_default_edition_id" not in existing_indexes:
        op.create_index(op.f("ix_books_default_edition_id"), "books", ["default_edition_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_books_default_edition_id"), table_name="books")
    op.drop_column("books", "default_edition_id")
