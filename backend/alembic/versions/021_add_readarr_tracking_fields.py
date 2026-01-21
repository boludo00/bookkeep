"""Add readarr tracking fields to book_requests

Revision ID: 021
Revises: 020
Create Date: 2026-01-17
"""

from alembic import op
import sqlalchemy as sa


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add readarr tracking fields to book_requests table
    op.add_column("book_requests", sa.Column("readarr_received", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("book_requests", sa.Column("readarr_search_triggered", sa.Boolean(), nullable=True))
    op.add_column("book_requests", sa.Column("readarr_search_status_code", sa.Integer(), nullable=True))
    op.add_column("book_requests", sa.Column("readarr_message", sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove readarr tracking fields from book_requests table
    op.drop_column("book_requests", "readarr_message")
    op.drop_column("book_requests", "readarr_search_status_code")
    op.drop_column("book_requests", "readarr_search_triggered")
    op.drop_column("book_requests", "readarr_received")
