"""Add readarr tracking fields to book_requests

Revision ID: 021
Revises: 020
Create Date: 2026-01-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add readarr tracking fields to book_requests table
    if not column_exists("book_requests", "readarr_received"):
        op.add_column("book_requests", sa.Column("readarr_received", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not column_exists("book_requests", "readarr_search_triggered"):
        op.add_column("book_requests", sa.Column("readarr_search_triggered", sa.Boolean(), nullable=True))
    if not column_exists("book_requests", "readarr_search_status_code"):
        op.add_column("book_requests", sa.Column("readarr_search_status_code", sa.Integer(), nullable=True))
    if not column_exists("book_requests", "readarr_message"):
        op.add_column("book_requests", sa.Column("readarr_message", sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove readarr tracking fields from book_requests table
    if column_exists("book_requests", "readarr_message"):
        op.drop_column("book_requests", "readarr_message")
    if column_exists("book_requests", "readarr_search_status_code"):
        op.drop_column("book_requests", "readarr_search_status_code")
    if column_exists("book_requests", "readarr_search_triggered"):
        op.drop_column("book_requests", "readarr_search_triggered")
    if column_exists("book_requests", "readarr_received"):
        op.drop_column("book_requests", "readarr_received")
