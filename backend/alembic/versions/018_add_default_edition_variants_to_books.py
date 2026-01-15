"""add_default_edition_variants_to_books

Revision ID: 018
Revises: 017
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "books" not in inspector.get_table_names():
        return

    existing_columns = [col["name"] for col in inspector.get_columns("books")]

    if "default_physical_edition_id" not in existing_columns:
        op.add_column("books", sa.Column("default_physical_edition_id", sa.Integer(), nullable=True))
    if "default_ebook_edition_id" not in existing_columns:
        op.add_column("books", sa.Column("default_ebook_edition_id", sa.Integer(), nullable=True))
    if "default_audio_edition_id" not in existing_columns:
        op.add_column("books", sa.Column("default_audio_edition_id", sa.Integer(), nullable=True))

    # Backfill physical edition from legacy default_edition_id when present
    if "default_edition_id" in existing_columns and "default_physical_edition_id" not in existing_columns:
        op.execute(
            "UPDATE books SET default_physical_edition_id = default_edition_id "
            "WHERE default_physical_edition_id IS NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("books", schema=None) as batch_op:
        batch_op.drop_column("default_audio_edition_id")
        batch_op.drop_column("default_ebook_edition_id")
        batch_op.drop_column("default_physical_edition_id")
