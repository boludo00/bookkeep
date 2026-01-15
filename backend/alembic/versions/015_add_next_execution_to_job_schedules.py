"""add next_execution to job_schedules

Revision ID: 015
Revises: 014
Create Date: 2025-12-23 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'job_schedules' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('job_schedules')]
    
    if 'next_execution' not in existing_columns:
        op.add_column('job_schedules', sa.Column('next_execution', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'job_schedules' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('job_schedules')]
    
    if 'next_execution' in existing_columns:
        op.drop_column('job_schedules', 'next_execution')

