"""Add edition_id to book_requests

Revision ID: 019
Revises: 018
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade():
    if not _column_exists('book_requests', 'edition_id'):
        with op.batch_alter_table('book_requests', schema=None) as batch_op:
            batch_op.add_column(sa.Column('edition_id', sa.Integer(), nullable=True))


def downgrade():
    if _column_exists('book_requests', 'edition_id'):
        with op.batch_alter_table('book_requests', schema=None) as batch_op:
            batch_op.drop_column('edition_id')
