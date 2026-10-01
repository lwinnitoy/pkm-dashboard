"""track institution id and account mask

Lets a re-link be recognized as the same institution (Plaid mints a new item_id
and new account_ids each time through Link) and existing account rows rebound to
their new Plaid ids instead of being duplicated.

Revision ID: c3e8a91b47d2
Revises: b1c4f7a29e3d
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e8a91b47d2'
down_revision: Union[str, Sequence[str], None] = 'b1c4f7a29e3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, index: str) -> bool:
    return any(i["name"] == index for i in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    """Upgrade schema.

    Each step checks first because Replit's publish step diffs the dev database
    against production and applies the difference *before* `alembic upgrade head`
    runs, so these objects may already exist when this migration gets to them.
    """
    if not _has_column('plaid_items', 'institution_id'):
        op.add_column('plaid_items', sa.Column('institution_id', sa.String(), nullable=True))
    if not _has_index('plaid_items', 'ix_plaid_items_institution_id'):
        op.create_index('ix_plaid_items_institution_id', 'plaid_items', ['institution_id'])
    if not _has_column('accounts', 'mask'):
        op.add_column('accounts', sa.Column('mask', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if _has_column('accounts', 'mask'):
        op.drop_column('accounts', 'mask')
    if _has_index('plaid_items', 'ix_plaid_items_institution_id'):
        op.drop_index('ix_plaid_items_institution_id', table_name='plaid_items')
    if _has_column('plaid_items', 'institution_id'):
        op.drop_column('plaid_items', 'institution_id')
