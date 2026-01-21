"""add client state tracking

Revision ID: 026
Revises: 025
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade():
    # Add client_state field to download_tasks for storing raw client state (e.g., "stalledDL", "uploading")
    op.add_column('download_tasks', sa.Column('client_state', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('download_tasks', 'client_state')
