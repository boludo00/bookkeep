"""fix user permissions null values

Revision ID: 007
Revises: 006
Create Date: 2025-12-23 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    # This migration ensures all NULL values are set to defaults
    # Migration 006 should have already handled this, but this is a safety net
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if 'users' not in inspector.get_table_names():
        return
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Ensure all permission columns have default values (no NULLs)
    if 'can_request_ebook' in existing_columns:
        op.execute("UPDATE users SET can_request_ebook = TRUE WHERE can_request_ebook IS NULL")
    if 'can_request_audiobook' in existing_columns:
        op.execute("UPDATE users SET can_request_audiobook = TRUE WHERE can_request_audiobook IS NULL")
    if 'auto_approve_ebooks' in existing_columns:
        op.execute("UPDATE users SET auto_approve_ebooks = TRUE WHERE auto_approve_ebooks IS NULL")
    if 'auto_approve_audiobooks' in existing_columns:
        op.execute("UPDATE users SET auto_approve_audiobooks = TRUE WHERE auto_approve_audiobooks IS NULL")


def downgrade():
    # No-op: values can remain as they are
    pass
