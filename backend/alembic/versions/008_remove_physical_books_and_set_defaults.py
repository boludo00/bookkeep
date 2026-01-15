"""remove physical books and set defaults

Revision ID: 008
Revises: 007
Create Date: 2025-12-23 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    # Remove physical book columns if they exist (cleanup)
    # Note: Migration 006 should have already handled this, but this ensures cleanup
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'users' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Remove physical book columns if they exist
    if 'can_request_physical' in existing_columns:
        op.drop_column('users', 'can_request_physical')
    if 'auto_approve_physical' in existing_columns:
        op.drop_column('users', 'auto_approve_physical')
    
    # Ensure defaults are set (safety net - migration 006 and 007 should have handled this)
    if 'can_request_ebook' in existing_columns:
        op.execute("UPDATE users SET can_request_ebook = TRUE WHERE can_request_ebook IS NULL OR can_request_ebook = FALSE")
    if 'can_request_audiobook' in existing_columns:
        op.execute("UPDATE users SET can_request_audiobook = TRUE WHERE can_request_audiobook IS NULL OR can_request_audiobook = FALSE")
    if 'auto_approve_ebooks' in existing_columns:
        op.execute("UPDATE users SET auto_approve_ebooks = TRUE WHERE auto_approve_ebooks IS NULL OR auto_approve_ebooks = FALSE")
    if 'auto_approve_audiobooks' in existing_columns:
        op.execute("UPDATE users SET auto_approve_audiobooks = TRUE WHERE auto_approve_audiobooks IS NULL OR auto_approve_audiobooks = FALSE")


def downgrade():
    # Re-add physical book columns if needed
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'users' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'can_request_physical' not in existing_columns:
        op.add_column('users', sa.Column('can_request_physical', sa.Boolean(), nullable=True))
    if 'auto_approve_physical' not in existing_columns:
        op.add_column('users', sa.Column('auto_approve_physical', sa.Boolean(), nullable=True))
