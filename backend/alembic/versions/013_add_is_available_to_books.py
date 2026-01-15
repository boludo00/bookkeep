"""add is_available to books

Revision ID: 013
Revises: 012
Create Date: 2025-12-23 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'books' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('books')]
    
    if 'is_available' not in existing_columns:
        op.add_column('books', sa.Column('is_available', sa.Boolean(), nullable=True, server_default=sa.text('false')))
        
        # Set is_available = True for books that have an "available" request
        op.execute("""
            UPDATE books SET is_available = TRUE
            WHERE id IN (
                SELECT DISTINCT book_id FROM book_requests WHERE status = 'available'
            )
        """)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'books' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('books')]
    
    if 'is_available' in existing_columns:
        op.drop_column('books', 'is_available')
