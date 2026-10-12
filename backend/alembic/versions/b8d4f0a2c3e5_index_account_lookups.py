"""index per-account lookups on transactions and investment transactions

Revision ID: b8d4f0a2c3e5
Revises: a7c3e9f1b2d4
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4f0a2c3e5'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f1b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(table: str, index: str) -> bool:
    return any(i["name"] == index for i in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _has_index('transactions', 'ix_transactions_account_id_date'):
        op.create_index('ix_transactions_account_id_date', 'transactions', ['account_id', 'date'])
    if not _has_index('investment_transactions', 'ix_investment_transactions_account_id'):
        op.create_index(
            'ix_investment_transactions_account_id', 'investment_transactions', ['account_id']
        )


def downgrade() -> None:
    if _has_index('investment_transactions', 'ix_investment_transactions_account_id'):
        op.drop_index('ix_investment_transactions_account_id', table_name='investment_transactions')
    if _has_index('transactions', 'ix_transactions_account_id_date'):
        op.drop_index('ix_transactions_account_id_date', table_name='transactions')
