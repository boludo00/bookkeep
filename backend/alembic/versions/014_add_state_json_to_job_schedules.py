"""add state_json to job_schedules

Revision ID: 014
Revises: 013
Create Date: 2025-12-23 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'job_schedules' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('job_schedules')]
    
    if 'state_json' not in existing_columns:
        op.add_column('job_schedules', sa.Column('state_json', sa.Text(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'job_schedules' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('job_schedules')]
    
    if 'state_json' in existing_columns:
        op.drop_column('job_schedules', 'state_json')

