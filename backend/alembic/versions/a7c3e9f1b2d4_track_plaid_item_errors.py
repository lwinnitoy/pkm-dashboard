"""track each Plaid item's last sync error

`last_error_code` / `last_error_at` record why a login last failed to sync (e.g.
ITEM_LOGIN_REQUIRED), so the Accounts page can offer "Reconnect" on that bank.

Revision ID: a7c3e9f1b2d4
Revises: f4b9d2e7c1a3
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f1b2d4'
down_revision: Union[str, Sequence[str], None] = 'f4b9d2e7c1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column('plaid_items', 'last_error_code'):
        op.add_column('plaid_items', sa.Column('last_error_code', sa.String(), nullable=True))
    if not _has_column('plaid_items', 'last_error_at'):
        op.add_column('plaid_items', sa.Column('last_error_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    present = [c for c in ('last_error_at', 'last_error_code') if _has_column('plaid_items', c)]
    if present:
        with op.batch_alter_table('plaid_items') as batch:
            for column in present:
                batch.drop_column(column)
