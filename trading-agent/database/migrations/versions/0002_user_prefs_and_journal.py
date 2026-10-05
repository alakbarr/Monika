"""user_preferences_and_journal

Revision ID: u2p3j4c5d6e7
Revises: t1a2b3c4d5e6
Create Date: 2026-10-04 15:28:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'u2p3j4c5d6e7'
down_revision: Union[str, None] = 't1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    if 'user_preferences' not in existing_tables:
        op.create_table(
            'user_preferences',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.String(length=64), nullable=False),
            sa.Column('category', sa.String(length=32), nullable=False),
            sa.Column('key', sa.String(length=64), nullable=False),
            sa.Column('value_json', sa.Text(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_user_preferences_user_id'), 'user_preferences', ['user_id'], unique=False)
        op.create_index(op.f('ix_user_preferences_category'), 'user_preferences', ['category'], unique=False)
        op.create_index('idx_user_pref_lookup', 'user_preferences', ['user_id', 'category', 'is_active'], unique=False)

    if 'user_journal_entries' not in existing_tables:
        op.create_table(
            'user_journal_entries',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.String(length=64), nullable=False),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
            sa.Column('symbol', sa.String(length=20), nullable=True),
            sa.Column('sentiment_tag', sa.String(length=32), nullable=True),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('ticket_ref', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_user_journal_entries_user_id'), 'user_journal_entries', ['user_id'], unique=False)
        op.create_index(op.f('ix_user_journal_entries_timestamp'), 'user_journal_entries', ['timestamp'], unique=False)
        op.create_index(op.f('ix_user_journal_entries_sentiment_tag'), 'user_journal_entries', ['sentiment_tag'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_journal_entries_sentiment_tag'), table_name='user_journal_entries')
    op.drop_index(op.f('ix_user_journal_entries_timestamp'), table_name='user_journal_entries')
    op.drop_index(op.f('ix_user_journal_entries_user_id'), table_name='user_journal_entries')
    op.drop_table('user_journal_entries')

    op.drop_index('idx_user_pref_lookup', table_name='user_preferences')
    op.drop_index(op.f('ix_user_preferences_category'), table_name='user_preferences')
    op.drop_index(op.f('ix_user_preferences_user_id'), table_name='user_preferences')
    op.drop_table('user_preferences')
