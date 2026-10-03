"""add a balance anchor to manual accounts

A CSV/Excel statement has no balance column, so a manual account's balance is
entered by hand as of a date (the anchor) and rolled forward through the
transactions imported after it. See app/imports/balance.py.

Revision ID: d7e2b5c4a1f0
Revises: c3e8a91b47d2
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e2b5c4a1f0'
down_revision: Union[str, Sequence[str], None] = 'c3e8a91b47d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    """Upgrade schema.

    Each step checks first because Replit's publish step diffs the dev database
    against production and applies the difference *before* `alembic upgrade head`
    runs, so these columns may already exist when this migration gets to them.
    """
    if not _has_column('accounts', 'balance_anchor'):
        op.add_column('accounts', sa.Column('balance_anchor', sa.Float(), nullable=True))
    if not _has_column('accounts', 'balance_anchor_date'):
        op.add_column('accounts', sa.Column('balance_anchor_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        if _has_column('accounts', 'balance_anchor_date'):
            batch_op.drop_column('balance_anchor_date')
        if _has_column('accounts', 'balance_anchor'):
            batch_op.drop_column('balance_anchor')
