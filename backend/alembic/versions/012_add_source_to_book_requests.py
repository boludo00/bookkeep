"""add source column to book_requests

Revision ID: 012
Revises: 011
Create Date: 2025-12-23 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'book_requests' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('book_requests')]
    
    if 'source' not in existing_columns:
        op.add_column('book_requests', sa.Column('source', sa.String(), nullable=True, server_default='user_request'))
        
        # Update existing rows to have 'user_request' as source
        op.execute("UPDATE book_requests SET source = 'user_request' WHERE source IS NULL")


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'book_requests' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('book_requests')]
    
    if 'source' in existing_columns:
        op.drop_column('book_requests', 'source')

