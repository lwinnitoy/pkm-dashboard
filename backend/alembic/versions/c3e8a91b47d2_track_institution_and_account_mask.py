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


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('plaid_items', sa.Column('institution_id', sa.String(), nullable=True))
    op.create_index('ix_plaid_items_institution_id', 'plaid_items', ['institution_id'])
    op.add_column('accounts', sa.Column('mask', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('accounts', 'mask')
    op.drop_index('ix_plaid_items_institution_id', table_name='plaid_items')
    op.drop_column('plaid_items', 'institution_id')
