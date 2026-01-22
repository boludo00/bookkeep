"""add can_download permission

Revision ID: 028
Revises: 027
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in the table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add can_download column to users table
    if not column_exists('users', 'can_download'):
        op.add_column('users', sa.Column('can_download', sa.Boolean(), nullable=True, server_default='true'))


def downgrade() -> None:
    # Remove can_download column
    if column_exists('users', 'can_download'):
        op.drop_column('users', 'can_download')
