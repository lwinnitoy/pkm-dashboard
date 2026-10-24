"""recategorize Plaid transactions with the detailed-category map

Data only. `normalize_category` now reads Plaid's *detailed* category, which turns
card payments into Transfers (they were Loans, so counted as spending) and
groceries into Groceries (they were Dining). Rows already stored keep the old
category until Plaid sends them again, so clear every item's sync cursor: the
next sync re-walks each item's history under the same transaction ids, and the
upsert recategorizes in place. Merchant rules still win, as on any sync.

Revision ID: f4b9d2e7c1a3
Revises: e8f3c6d5b2a1
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f4b9d2e7c1a3'
down_revision: Union[str, Sequence[str], None] = 'e8f3c6d5b2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE plaid_items SET transactions_cursor = NULL")


def downgrade() -> None:
    # Nothing to undo: a cleared cursor only costs one fuller sync.
    pass
