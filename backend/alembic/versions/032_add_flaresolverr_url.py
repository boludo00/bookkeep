"""add flaresolverr_url to direct_download_settings

Revision ID: 032
Revises: 031
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '032'
down_revision = '031b'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not column_exists('direct_download_settings', 'flaresolverr_url'):
        op.add_column(
            'direct_download_settings',
            sa.Column('flaresolverr_url', sa.String(), nullable=True)
        )


def downgrade():
    if column_exists('direct_download_settings', 'flaresolverr_url'):
        op.drop_column('direct_download_settings', 'flaresolverr_url')
