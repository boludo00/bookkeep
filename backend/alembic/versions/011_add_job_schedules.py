"""add job_schedules table

Revision ID: 011
Revises: 010
Create Date: 2025-12-23 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None

# Default job schedules
DEFAULT_JOBS = [
    {"job_name": "refresh_seed_data", "interval_seconds": 24 * 60 * 60},  # 24 hours
    {"job_name": "check_processing_requests", "interval_seconds": 5 * 60},  # 5 minutes
    {"job_name": "sync_from_booklore", "interval_seconds": 24 * 60 * 60},  # 24 hours
]


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'job_schedules' not in inspector.get_table_names():
        op.create_table('job_schedules',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('job_name', sa.String(), nullable=False),
            sa.Column('interval_seconds', sa.Integer(), nullable=False),
            sa.Column('last_execution', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_enabled', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_job_schedules_id'), 'job_schedules', ['id'], unique=False)
        op.create_index(op.f('ix_job_schedules_job_name'), 'job_schedules', ['job_name'], unique=True)
        
        # Insert default jobs
        job_schedules = sa.table('job_schedules',
            sa.column('job_name', sa.String),
            sa.column('interval_seconds', sa.Integer),
            sa.column('is_enabled', sa.Boolean),
        )
        
        for job in DEFAULT_JOBS:
            op.execute(
                job_schedules.insert().values(
                    job_name=job["job_name"],
                    interval_seconds=job["interval_seconds"],
                    is_enabled=True,
                )
            )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'job_schedules' in inspector.get_table_names():
        op.drop_index(op.f('ix_job_schedules_job_name'), table_name='job_schedules')
        op.drop_index(op.f('ix_job_schedules_id'), table_name='job_schedules')
        op.drop_table('job_schedules')

