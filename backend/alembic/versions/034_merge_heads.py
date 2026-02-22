"""merge migration heads 031 and 033

Revision ID: 034
Revises: 031, 033
Create Date: 2026-02-21

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '034'
down_revision = ('031', '033')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
