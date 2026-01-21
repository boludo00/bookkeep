"""add import status tracking

Revision ID: 027
Revises: 026
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade():
    # Add import_status field to track import state
    # Values: 'pending', 'importing', 'imported', 'failed', 'skipped'
    op.add_column('download_tasks', sa.Column('import_status', sa.String(length=20), nullable=True, server_default='pending'))

    # Add import_message for error messages or details
    op.add_column('download_tasks', sa.Column('import_message', sa.String(length=500), nullable=True))

    # Add imported_at timestamp
    op.add_column('download_tasks', sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True))

    # Update existing completed tasks to 'imported' status
    op.execute("UPDATE download_tasks SET import_status = 'imported' WHERE state IN ('complete', 'seeding')")


def downgrade():
    op.drop_column('download_tasks', 'imported_at')
    op.drop_column('download_tasks', 'import_message')
    op.drop_column('download_tasks', 'import_status')
