"""add author_id to books

Revision ID: 005
Revises: 004
Create Date: 2025-12-23 00:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column already exists (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('books')]
    
    if 'author_id' not in columns:
        op.add_column('books', sa.Column('author_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_books_author_id'), 'books', ['author_id'], unique=False)


def downgrade():
    # Check if column exists before dropping (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('books')]
    
    if 'author_id' in columns:
        op.drop_index(op.f('ix_books_author_id'), table_name='books')
        op.drop_column('books', 'author_id')

