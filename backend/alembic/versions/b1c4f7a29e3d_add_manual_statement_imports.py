"""add manual statement imports

Relaxes the Plaid-shaped NOT NULLs on accounts/transactions so a row can exist
without a Plaid identity, and adds the CSV/Excel import tracking columns.

Revision ID: b1c4f7a29e3d
Revises: af551b736483
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c4f7a29e3d'
down_revision: Union[str, Sequence[str], None] = 'af551b736483'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'import_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('preset', sa.String(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('rows_parsed', sa.Integer(), nullable=False),
        sa.Column('rows_imported', sa.Integer(), nullable=False),
        sa.Column('rows_duplicate', sa.Integer(), nullable=False),
        sa.Column('rows_conflicting', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_import_batches_account_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_import_batches_account_id', 'import_batches', ['account_id'])
    op.create_index('ix_import_batches_period_start', 'import_batches', ['period_start'])
    op.create_index('ix_import_batches_period_end', 'import_batches', ['period_end'])

    # SQLite can't ALTER a column's nullability in place; batch mode rebuilds the
    # table. Works unchanged on Postgres, where it becomes a plain ALTER.
    with op.batch_alter_table('accounts') as batch:
        batch.alter_column('plaid_item_id', existing_type=sa.Integer(), nullable=True)
        batch.alter_column('plaid_account_id', existing_type=sa.String(), nullable=True)
        batch.add_column(
            sa.Column('source', sa.String(), nullable=False, server_default='plaid')
        )
    op.create_index('ix_accounts_source', 'accounts', ['source'])

    with op.batch_alter_table('transactions') as batch:
        batch.alter_column('plaid_transaction_id', existing_type=sa.String(), nullable=True)
        batch.add_column(sa.Column('import_fingerprint', sa.String(), nullable=True))
        batch.add_column(
            sa.Column('source', sa.String(), nullable=False, server_default='plaid')
        )
        batch.add_column(sa.Column('import_batch_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_transactions_import_batch_id', 'import_batches', ['import_batch_id'], ['id']
        )
    op.create_index(
        'ix_transactions_import_fingerprint', 'transactions', ['import_fingerprint'], unique=True
    )
    op.create_index('ix_transactions_source', 'transactions', ['source'])


def _inspector():
    return sa.inspect(op.get_bind())


def _fk_name(table: str, referred_table: str) -> str | None:
    """The actual constraint name, which differs by how the table was created.

    This migration names it `fk_transactions_import_batch_id`, but a database
    bootstrapped from the models instead (SQLite dev uses `create_all`) gets the
    backend's auto-generated name. Looking it up handles both, and returns None
    when there's nothing to drop.
    """
    for fk in _inspector().get_foreign_keys(table):
        if fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _has_index(table: str, index: str) -> bool:
    return any(i["name"] == index for i in _inspector().get_indexes(table))


def downgrade() -> None:
    """Downgrade schema.

    Written to tolerate a partially-applied upgrade: each drop checks that its
    target exists first. A downgrade that fails halfway leaves the schema
    somewhere no migration describes, which is far harder to recover from than
    a few redundant lookups.
    """
    for index in ('ix_transactions_source', 'ix_transactions_import_fingerprint'):
        if _has_index('transactions', index):
            op.drop_index(index, table_name='transactions')

    constraint = _fk_name('transactions', 'import_batches')
    with op.batch_alter_table('transactions') as batch:
        if constraint:
            batch.drop_constraint(constraint, type_='foreignkey')
        for column in ('import_batch_id', 'source', 'import_fingerprint'):
            if _has_column('transactions', column):
                batch.drop_column(column)
        batch.alter_column('plaid_transaction_id', existing_type=sa.String(), nullable=False)

    if _has_index('accounts', 'ix_accounts_source'):
        op.drop_index('ix_accounts_source', table_name='accounts')
    with op.batch_alter_table('accounts') as batch:
        if _has_column('accounts', 'source'):
            batch.drop_column('source')
        batch.alter_column('plaid_account_id', existing_type=sa.String(), nullable=False)
        batch.alter_column('plaid_item_id', existing_type=sa.Integer(), nullable=False)

    if 'import_batches' in _inspector().get_table_names():
        op.drop_table('import_batches')  # takes its indexes with it
