"""add readarr_book_id to book_requests

Revision ID: 009
Revises: 008
Create Date: 2025-12-23 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    # Add readarr_book_id column to book_requests table (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'book_requests' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('book_requests')]
    
    if 'readarr_book_id' not in existing_columns:
        op.add_column('book_requests', sa.Column('readarr_book_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_book_requests_readarr_book_id'), 'book_requests', ['readarr_book_id'], unique=False)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'book_requests' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('book_requests')]
    
    if 'readarr_book_id' in existing_columns:
        op.drop_index(op.f('ix_book_requests_readarr_book_id'), table_name='book_requests')
        op.drop_column('book_requests', 'readarr_book_id')

