"""add_seed_data_columns_to_books

Revision ID: 001
Revises: 
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns for seed data functionality
    # Check if columns exist first (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if table exists
    if 'books' not in inspector.get_table_names():
        return  # Table doesn't exist yet, skip migration
    
    existing_columns = [col['name'] for col in inspector.get_columns('books')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('books')]
    
    # Add hardcover_slug column if it doesn't exist
    if 'hardcover_slug' not in existing_columns:
        op.add_column('books', sa.Column('hardcover_slug', sa.String(), nullable=True))
        # Refresh column list after adding
        existing_columns.append('hardcover_slug')
    
    # Create index for hardcover_slug if column exists and index doesn't
    if 'hardcover_slug' in existing_columns and 'ix_books_hardcover_slug' not in existing_indexes:
        op.create_index(op.f('ix_books_hardcover_slug'), 'books', ['hardcover_slug'], unique=False)
    
    if 'ratings_count' not in existing_columns:
        op.add_column('books', sa.Column('ratings_count', sa.Integer(), nullable=True))
    
    if 'users_count' not in existing_columns:
        op.add_column('books', sa.Column('users_count', sa.Integer(), nullable=True))
    
    if 'activities_count' not in existing_columns:
        op.add_column('books', sa.Column('activities_count', sa.Integer(), nullable=True))
    
    if 'release_year' not in existing_columns:
        op.add_column('books', sa.Column('release_year', sa.Integer(), nullable=True))
    
    if 'is_seed_data' not in existing_columns:
        op.add_column('books', sa.Column('is_seed_data', sa.Boolean(), nullable=True, server_default='0'))
    
    if 'last_refreshed' not in existing_columns:
        op.add_column('books', sa.Column('last_refreshed', sa.DateTime(timezone=True), nullable=True))
    
    # Update unique constraint on hardcover_id if it doesn't exist
    # SQLite doesn't support ALTER TABLE ADD CONSTRAINT, so we'll skip this
    # The unique constraint will be handled by the model definition


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('books', 'last_refreshed')
    op.drop_column('books', 'is_seed_data')
    op.drop_column('books', 'release_year')
    op.drop_column('books', 'activities_count')
    op.drop_column('books', 'users_count')
    op.drop_column('books', 'ratings_count')
    op.drop_index(op.f('ix_books_hardcover_slug'), table_name='books')
    op.drop_column('books', 'hardcover_slug')

