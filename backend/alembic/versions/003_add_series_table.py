"""add_series_table

Revision ID: 003
Revises: 002
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'series' not in inspector.get_table_names():
        # Create series table
        op.create_table(
            'series',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('hardcover_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('books_count', sa.Integer(), nullable=True),
            sa.Column('is_seed_data', sa.Boolean(), nullable=True),
            sa.Column('last_refreshed', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('series')} if 'series' in inspector.get_table_names() else set()
    if op.f('ix_series_hardcover_id') not in existing_indexes:
        op.create_index(op.f('ix_series_hardcover_id'), 'series', ['hardcover_id'], unique=True)
    if op.f('ix_series_id') not in existing_indexes:
        op.create_index(op.f('ix_series_id'), 'series', ['id'], unique=False)
    if op.f('ix_series_name') not in existing_indexes:
        op.create_index(op.f('ix_series_name'), 'series', ['name'], unique=False)


def downgrade() -> None:
    # Remove series table
    op.drop_index(op.f('ix_series_name'), table_name='series')
    op.drop_index(op.f('ix_series_id'), table_name='series')
    op.drop_index(op.f('ix_series_hardcover_id'), table_name='series')
    op.drop_table('series')
