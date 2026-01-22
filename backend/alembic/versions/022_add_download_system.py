"""add_download_system

Revision ID: 022
Revises: 021
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '022'
down_revision = '021'
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
    # Create download_clients table
    if not table_exists('download_clients'):
        op.create_table(
        'download_clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('protocol', sa.String(), nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('use_ssl', sa.Boolean(), nullable=True, default=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('password', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True, default=True),
        sa.Column('priority', sa.Integer(), nullable=True, default=0),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('path_mappings_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    if not index_exists('download_clients', 'ix_download_clients_name'):
        op.create_index('ix_download_clients_name', 'download_clients', ['name'], unique=True)

    # Create download_tasks table
    if not table_exists('download_tasks'):
        op.create_table(
        'download_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('format', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('release_title', sa.String(), nullable=True),
        sa.Column('download_url', sa.String(), nullable=True),
        sa.Column('protocol', sa.String(), nullable=True),
        sa.Column('indexer', sa.String(), nullable=True),
        sa.Column('indexer_id', sa.Integer(), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('state', sa.String(), nullable=False, default='queued'),
        sa.Column('progress', sa.Float(), nullable=True, default=0.0),
        sa.Column('download_speed', sa.Float(), nullable=True),
        sa.Column('upload_speed', sa.Float(), nullable=True),
        sa.Column('eta_seconds', sa.Integer(), nullable=True),
        sa.Column('downloaded_bytes', sa.BigInteger(), nullable=True),
        sa.Column('total_bytes', sa.BigInteger(), nullable=True),
        sa.Column('message', sa.String(), nullable=True),
        sa.Column('download_path', sa.String(), nullable=True),
        sa.Column('original_download_path', sa.String(), nullable=True),
        sa.Column('final_path', sa.String(), nullable=True),
        sa.Column('client_type', sa.String(), nullable=True),
        sa.Column('client_download_id', sa.String(), nullable=True),
        sa.Column('release_data_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['book_id'], ['books.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    if not index_exists('download_tasks', 'ix_download_tasks_book_id'):
        op.create_index('ix_download_tasks_book_id', 'download_tasks', ['book_id'])
    if not index_exists('download_tasks', 'ix_download_tasks_state'):
        op.create_index('ix_download_tasks_state', 'download_tasks', ['state'])


def downgrade():
    if table_exists('download_tasks'):
        if index_exists('download_tasks', 'ix_download_tasks_state'):
            op.drop_index('ix_download_tasks_state', table_name='download_tasks')
        if index_exists('download_tasks', 'ix_download_tasks_book_id'):
            op.drop_index('ix_download_tasks_book_id', table_name='download_tasks')
        op.drop_table('download_tasks')
    if table_exists('download_clients'):
        if index_exists('download_clients', 'ix_download_clients_name'):
            op.drop_index('ix_download_clients_name', table_name='download_clients')
        op.drop_table('download_clients')
