"""Add telegram_topic_bindings table

Revision ID: l1a2b3c4d5e6
Revises: k1a2b3c4d5e6
Create Date: 2026-09-14 02:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l1a2b3c4d5e6'
down_revision: Union[str, None] = 'k1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_tables(conn) -> set:
    try:
        insp = sa.inspect(conn)
        return set(insp.get_table_names())
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'telegram_topic_bindings' not in tables:
        op.create_table(
            'telegram_topic_bindings',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('chat_id', sa.BigInteger(), nullable=False),
            sa.Column('topic_id', sa.Integer(), nullable=False),
            sa.Column('topic_name', sa.String(length=255), nullable=False, server_default=''),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('chat_id', 'topic_id', name='uq_telegram_topic_chat_topic'),
            sa.UniqueConstraint('session_id', name='uq_telegram_topic_session_id'),
        )
        op.create_index('ix_telegram_topic_bindings_chat_id', 'telegram_topic_bindings', ['chat_id'])
        op.create_index('ix_telegram_topic_bindings_topic_id', 'telegram_topic_bindings', ['topic_id'])
        op.create_index('ix_telegram_topic_bindings_session_id', 'telegram_topic_bindings', ['session_id'])
        op.create_index('idx_tg_topic_chat_topic', 'telegram_topic_bindings', ['chat_id', 'topic_id'])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)
    if 'telegram_topic_bindings' in tables:
        op.drop_index('idx_tg_topic_chat_topic', table_name='telegram_topic_bindings')
        op.drop_index('ix_telegram_topic_bindings_session_id', table_name='telegram_topic_bindings')
        op.drop_index('ix_telegram_topic_bindings_topic_id', table_name='telegram_topic_bindings')
        op.drop_index('ix_telegram_topic_bindings_chat_id', table_name='telegram_topic_bindings')
        op.drop_table('telegram_topic_bindings')
