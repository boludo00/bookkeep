"""add_series_id_to_books

Revision ID: 002
Revises: 001
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add series_id column to books table (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if table exists
    if 'books' not in inspector.get_table_names():
        return  # Table doesn't exist yet, skip migration
    
    existing_columns = [col['name'] for col in inspector.get_columns('books')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('books')]
    
    if 'series_id' not in existing_columns:
        op.add_column('books', sa.Column('series_id', sa.Integer(), nullable=True))
    
    # Create index only if column exists and index doesn't exist
    if 'series_id' in existing_columns and 'ix_books_series_id' not in existing_indexes:
        op.create_index(op.f('ix_books_series_id'), 'books', ['series_id'], unique=False)


def downgrade() -> None:
    # Remove series_id column from books table
    op.drop_index(op.f('ix_books_series_id'), table_name='books')
    op.drop_column('books', 'series_id')

