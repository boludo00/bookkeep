"""add can_download permission

Revision ID: 028
Revises: 027
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add can_download column to users table
    op.add_column('users', sa.Column('can_download', sa.Boolean(), nullable=True, server_default='true'))


def downgrade() -> None:
    # Remove can_download column
    op.drop_column('users', 'can_download')
