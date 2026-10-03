"""add insights (learning / news / progress cards)

Content for the Goals and Budgets pages lives in this table rather than in the
frontend, so it can be rewritten by a scheduled job or an external pipeline
without a UI change. See docs/insights.md.

Revision ID: e8f3c6d5b2a1
Revises: d7e2b5c4a1f0
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f3c6d5b2a1'
down_revision: Union[str, Sequence[str], None] = 'd7e2b5c4a1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_index(table: str, index: str) -> bool:
    return any(i["name"] == index for i in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    """Upgrade schema.

    Each step checks first: Replit's publish step diffs the dev database against
    production and applies the difference *before* `alembic upgrade head` runs,
    so the table may already exist when this migration gets to it.
    """
    if not _has_table('insights'):
        op.create_table(
            'insights',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('key', sa.String(), nullable=False),
            sa.Column('page', sa.String(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('summary', sa.String(), nullable=True),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('sources', sa.JSON(), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False),
            sa.Column('origin', sa.String(), nullable=False),
            sa.Column('model', sa.String(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _has_index('insights', 'ix_insights_key'):
        op.create_index('ix_insights_key', 'insights', ['key'], unique=True)
    if not _has_index('insights', 'ix_insights_page'):
        op.create_index('ix_insights_page', 'insights', ['page'])


def downgrade() -> None:
    """Downgrade schema."""
    if not _has_table('insights'):
        return
    if _has_index('insights', 'ix_insights_page'):
        op.drop_index('ix_insights_page', table_name='insights')
    if _has_index('insights', 'ix_insights_key'):
        op.drop_index('ix_insights_key', table_name='insights')
    op.drop_table('insights')
