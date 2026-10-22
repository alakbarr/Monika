"""sync technical indicators and telegram topic indexes

Revision ID: 0011_sync_indexes_constraints
Revises: 0010_paper_trade_initial_risk
Create Date: 2026-10-22 11:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_sync_indexes_constraints"
down_revision: Union[str, Sequence[str], None] = "0010_paper_trade_initial_risk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Drop duplicate index on technical_indicators and enforce unique session_id."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Drop duplicate index on technical_indicators if both indexes exist
    if "technical_indicators" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("technical_indicators")}
        if "idx_indicator_sym_tf_ts_name" in existing_indexes and "idx_indicator_sym_tf_ts" in existing_indexes:
            op.drop_index("idx_indicator_sym_tf_ts_name", table_name="technical_indicators")

    # 2. Sync ix_telegram_topic_bindings_session_id to UNIQUE
    if "telegram_topic_bindings" in existing_tables:
        existing_indexes = {idx.get("name"): idx for idx in insp.get_indexes("telegram_topic_bindings")}
        if "ix_telegram_topic_bindings_session_id" in existing_indexes:
            if not existing_indexes["ix_telegram_topic_bindings_session_id"].get("unique"):
                op.drop_index("ix_telegram_topic_bindings_session_id", table_name="telegram_topic_bindings")
                op.create_index(
                    "ix_telegram_topic_bindings_session_id",
                    "telegram_topic_bindings",
                    ["session_id"],
                    unique=True,
                )
        else:
            op.create_index(
                "ix_telegram_topic_bindings_session_id",
                "telegram_topic_bindings",
                ["session_id"],
                unique=True,
            )


def downgrade() -> None:
    """Downgrade schema: Restore duplicate index and non-unique session_id index."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Revert telegram_topic_bindings session_id index to non-unique
    if "telegram_topic_bindings" in existing_tables:
        existing_indexes = {idx.get("name"): idx for idx in insp.get_indexes("telegram_topic_bindings")}
        if "ix_telegram_topic_bindings_session_id" in existing_indexes:
            if existing_indexes["ix_telegram_topic_bindings_session_id"].get("unique"):
                op.drop_index("ix_telegram_topic_bindings_session_id", table_name="telegram_topic_bindings")
                op.create_index(
                    "ix_telegram_topic_bindings_session_id",
                    "telegram_topic_bindings",
                    ["session_id"],
                    unique=False,
                )

    # 2. Restore duplicate index on technical_indicators
    if "technical_indicators" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("technical_indicators")}
        if "idx_indicator_sym_tf_ts_name" not in existing_indexes:
            op.create_index(
                "idx_indicator_sym_tf_ts_name",
                "technical_indicators",
                ["symbol", "timeframe", "timestamp", "indicator_name"],
                unique=False,
            )
