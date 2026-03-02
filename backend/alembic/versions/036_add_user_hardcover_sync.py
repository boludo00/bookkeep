"""add user hardcover sync config table

Revision ID: 036
Revises: 035
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa

revision = '036'
down_revision = '035'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_hardcover_sync',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('hardcover_api_token', sa.String(), nullable=True),
        sa.Column('sync_to_read', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sync_list_ids', sa.Text(), nullable=True),  # JSON array of list IDs
        sa.Column('default_format', sa.String(), nullable=False, server_default='ebook'),  # ebook|audiobook|both
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )


def downgrade():
    op.drop_table('user_hardcover_sync')
