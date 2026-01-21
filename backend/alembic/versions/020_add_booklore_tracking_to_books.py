"""Add booklore tracking to books

Revision ID: 020
Revises: 019
Create Date: 2026-01-17
"""

from alembic import op
import sqlalchemy as sa


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("books", sa.Column("booklore_id", sa.Integer(), nullable=True))
    op.add_column("books", sa.Column("booklore_added_on", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_books_booklore_id"), "books", ["booklore_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_books_booklore_id"), table_name="books")
    op.drop_column("books", "booklore_added_on")
    op.drop_column("books", "booklore_id")
