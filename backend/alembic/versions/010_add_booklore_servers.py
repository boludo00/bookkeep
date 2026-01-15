"""add booklore_servers table

Revision ID: 010
Revises: 009
Create Date: 2025-12-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'booklore_servers' not in inspector.get_table_names():
        op.create_table('booklore_servers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('url', sa.String(), nullable=False),
            sa.Column('username', sa.String(), nullable=False),
            sa.Column('password', sa.String(), nullable=False),
            sa.Column('is_default', sa.Boolean(), default=False),
            sa.Column('access_token', sa.Text(), nullable=True),
            sa.Column('refresh_token', sa.Text(), nullable=True),
            sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_booklore_servers_id'), 'booklore_servers', ['id'], unique=False)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'booklore_servers' in inspector.get_table_names():
        op.drop_index(op.f('ix_booklore_servers_id'), table_name='booklore_servers')
        op.drop_table('booklore_servers')

