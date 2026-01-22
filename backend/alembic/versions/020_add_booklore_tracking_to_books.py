"""Add booklore tracking to books

Revision ID: 020
Revises: 019
Create Date: 2026-01-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    if not column_exists("books", "booklore_id"):
        op.add_column("books", sa.Column("booklore_id", sa.Integer(), nullable=True))
    if not column_exists("books", "booklore_added_on"):
        op.add_column("books", sa.Column("booklore_added_on", sa.DateTime(timezone=True), nullable=True))
    if not index_exists("books", "ix_books_booklore_id"):
        op.create_index(op.f("ix_books_booklore_id"), "books", ["booklore_id"], unique=True)


def downgrade() -> None:
    if index_exists("books", "ix_books_booklore_id"):
        op.drop_index(op.f("ix_books_booklore_id"), table_name="books")
    if column_exists("books", "booklore_added_on"):
        op.drop_column("books", "booklore_added_on")
    if column_exists("books", "booklore_id"):
        op.drop_column("books", "booklore_id")
