"""add oidc fields to users table

Revision ID: 035
Revises: 034
Create Date: 2026-03-01

"""
from alembic import op
import sqlalchemy as sa


revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_columns = [c['name'] for c in inspector.get_columns('users')]
    if 'oidc_subject' not in existing_columns:
        op.add_column('users', sa.Column('oidc_subject', sa.String(), nullable=True))

    existing_indexes = [i['name'] for i in inspector.get_indexes('users')]
    if 'ix_users_oidc_subject' not in existing_indexes:
        op.create_index('ix_users_oidc_subject', 'users', ['oidc_subject'], unique=True)

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('hashed_password', existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.drop_index('ix_users_oidc_subject', table_name='users')
    op.drop_column('users', 'oidc_subject')

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('hashed_password', existing_type=sa.String(), nullable=False)
