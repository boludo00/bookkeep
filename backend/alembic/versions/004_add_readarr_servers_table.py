"""add_readarr_servers_table

Revision ID: 004
Revises: 003
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'readarr_servers' not in inspector.get_table_names():
        op.create_table(
            'readarr_servers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('hostname', sa.String(), nullable=False),
            sa.Column('port', sa.Integer(), nullable=False, server_default='8787'),
            sa.Column('use_ssl', sa.Boolean(), nullable=True, server_default='0'),
            sa.Column('api_key', sa.String(), nullable=False),
            sa.Column('url_base', sa.String(), nullable=True),
            sa.Column('is_default', sa.Boolean(), nullable=True, server_default='0'),
            sa.Column('is_audiobook', sa.Boolean(), nullable=True, server_default='0'),
            sa.Column('ebook_quality_profile_id', sa.Integer(), nullable=True),
            sa.Column('ebook_root_folder', sa.String(), nullable=True),
            sa.Column('ebook_tags', sa.String(), nullable=True),
            sa.Column('audiobook_quality_profile_id', sa.Integer(), nullable=True),
            sa.Column('audiobook_root_folder', sa.String(), nullable=True),
            sa.Column('audiobook_tags', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_readarr_servers_id'), 'readarr_servers', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_readarr_servers_id'), table_name='readarr_servers')
    op.drop_table('readarr_servers')

