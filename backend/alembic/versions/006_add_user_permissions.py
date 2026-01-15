"""add user permissions

Revision ID: 006
Revises: 005
Create Date: 2025-12-23 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    # Add permission columns to users table (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if table exists
    if 'users' not in inspector.get_table_names():
        return  # Table doesn't exist yet, skip migration
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Add columns only if they don't exist, then set defaults for existing rows
    if 'can_request_ebook' not in existing_columns:
        op.add_column('users', sa.Column('can_request_ebook', sa.Boolean(), nullable=True))
        op.execute("UPDATE users SET can_request_ebook = TRUE WHERE can_request_ebook IS NULL")
    
    if 'can_request_audiobook' not in existing_columns:
        op.add_column('users', sa.Column('can_request_audiobook', sa.Boolean(), nullable=True))
        op.execute("UPDATE users SET can_request_audiobook = TRUE WHERE can_request_audiobook IS NULL")
    
    if 'auto_approve_ebooks' not in existing_columns:
        op.add_column('users', sa.Column('auto_approve_ebooks', sa.Boolean(), nullable=True))
        op.execute("UPDATE users SET auto_approve_ebooks = TRUE WHERE auto_approve_ebooks IS NULL")
    
    if 'auto_approve_audiobooks' not in existing_columns:
        op.add_column('users', sa.Column('auto_approve_audiobooks', sa.Boolean(), nullable=True))
        op.execute("UPDATE users SET auto_approve_audiobooks = TRUE WHERE auto_approve_audiobooks IS NULL")
    
    # Also update any NULL values that might exist (in case columns were added but not updated)
    op.execute("UPDATE users SET can_request_ebook = TRUE WHERE can_request_ebook IS NULL")
    op.execute("UPDATE users SET can_request_audiobook = TRUE WHERE can_request_audiobook IS NULL")
    op.execute("UPDATE users SET auto_approve_ebooks = TRUE WHERE auto_approve_ebooks IS NULL")
    op.execute("UPDATE users SET auto_approve_audiobooks = TRUE WHERE auto_approve_audiobooks IS NULL")
    
    # Remove physical book columns if they exist (cleanup)
    if 'can_request_physical' in existing_columns:
        op.drop_column('users', 'can_request_physical')
    if 'auto_approve_physical' in existing_columns:
        op.drop_column('users', 'auto_approve_physical')


def downgrade():
    # Remove permission columns from users table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'users' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'auto_approve_audiobooks' in existing_columns:
        op.drop_column('users', 'auto_approve_audiobooks')
    if 'auto_approve_ebooks' in existing_columns:
        op.drop_column('users', 'auto_approve_ebooks')
    if 'can_request_audiobook' in existing_columns:
        op.drop_column('users', 'can_request_audiobook')
    if 'can_request_ebook' in existing_columns:
        op.drop_column('users', 'can_request_ebook')
