"""add prowlarr servers table

Revision ID: 023
Revises: 022
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    # Create prowlarr_servers table
    op.create_table(
        'prowlarr_servers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('use_ssl', sa.Boolean(), nullable=True),
        sa.Column('api_key', sa.String(), nullable=False),
        sa.Column('url_base', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(op.f('ix_prowlarr_servers_id'), 'prowlarr_servers', ['id'], unique=False)
    op.create_index(op.f('ix_prowlarr_servers_name'), 'prowlarr_servers', ['name'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_prowlarr_servers_name'), table_name='prowlarr_servers')
    op.drop_index(op.f('ix_prowlarr_servers_id'), table_name='prowlarr_servers')
    op.drop_table('prowlarr_servers')
