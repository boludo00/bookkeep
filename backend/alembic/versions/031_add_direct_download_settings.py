"""add direct download settings table

Revision ID: 031
Revises: 030
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade():
    # Create direct_download_settings table
    if not table_exists('direct_download_settings'):
        op.create_table(
            'direct_download_settings',
            sa.Column('id', sa.Integer(), nullable=False),
            # Master toggle
            sa.Column('enabled', sa.Boolean(), nullable=True, server_default='false'),
            # Anna's Archive settings
            sa.Column('annas_archive_enabled', sa.Boolean(), nullable=True, server_default='true'),
            sa.Column('annas_archive_mirror', sa.String(), nullable=True),
            # Z-Library settings
            sa.Column('zlibrary_enabled', sa.Boolean(), nullable=True, server_default='false'),
            sa.Column('zlibrary_email', sa.String(), nullable=True),
            sa.Column('zlibrary_password', sa.String(), nullable=True),
            sa.Column('zlibrary_domain', sa.String(), nullable=True),
            # Rate limiting
            sa.Column('requests_per_minute', sa.Integer(), nullable=True, server_default='10'),
            # Metadata
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )

    # Create indexes
    if not index_exists('direct_download_settings', 'ix_direct_download_settings_id'):
        op.create_index(op.f('ix_direct_download_settings_id'), 'direct_download_settings', ['id'], unique=False)


def downgrade():
    if table_exists('direct_download_settings'):
        if index_exists('direct_download_settings', 'ix_direct_download_settings_id'):
            op.drop_index(op.f('ix_direct_download_settings_id'), table_name='direct_download_settings')
        op.drop_table('direct_download_settings')
