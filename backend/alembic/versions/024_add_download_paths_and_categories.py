"""Add download paths and categories

Revision ID: 024
Revises: 023
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    # Add ebook_category and audiobook_category to download_clients
    op.add_column('download_clients', sa.Column('ebook_category', sa.String(), nullable=True))
    op.add_column('download_clients', sa.Column('audiobook_category', sa.String(), nullable=True))


def downgrade():
    op.drop_column('download_clients', 'audiobook_category')
    op.drop_column('download_clients', 'ebook_category')
