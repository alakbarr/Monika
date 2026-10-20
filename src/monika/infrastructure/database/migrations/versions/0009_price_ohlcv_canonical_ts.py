"""Add canonical_timestamp and deduplication tables for PriceOHLCV.

Revision ID: 0009_price_ohlcv_canonical_ts
Revises: 0008_create_debate_transcripts
Create Date: 2026-10-20 17:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_price_ohlcv_canonical_ts"
down_revision: Union[str, Sequence[str], None] = "0008_create_debate_transcripts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add canonical_timestamp and audit reject table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Create audit table for rejected/deduplicated price rows
    if "price_ohlcv_rejected" not in existing_tables:
        op.create_table(
            "price_ohlcv_rejected",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("original_id", sa.Integer(), nullable=True),
            sa.Column("symbol", sa.String(20), nullable=False),
            sa.Column("timeframe", sa.String(10), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("canonical_timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("open", sa.Float(), nullable=False),
            sa.Column("high", sa.Float(), nullable=False),
            sa.Column("low", sa.Float(), nullable=False),
            sa.Column("close", sa.Float(), nullable=False),
            sa.Column("volume", sa.Float(), nullable=False),
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("reason", sa.String(255), nullable=False),
        )

    # 2. Add canonical_timestamp to price_ohlcv if not present
    if "price_ohlcv" in existing_tables:
        existing_cols = {col["name"] for col in insp.get_columns("price_ohlcv")}
        if "canonical_timestamp" not in existing_cols:
            op.add_column(
                "price_ohlcv",
                sa.Column("canonical_timestamp", sa.DateTime(timezone=True), nullable=True),
            )

        # 3. Add canonical index and unique constraint
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("price_ohlcv")}
        if "idx_price_sym_tf_canonical_ts" not in existing_indexes:
            op.create_index(
                "idx_price_sym_tf_canonical_ts",
                "price_ohlcv",
                ["symbol", "timeframe", "canonical_timestamp"],
            )

    # 4. Add unique constraint on technical_indicators if not present
    if "technical_indicators" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("technical_indicators")}
        if "idx_indicator_sym_tf_ts_name" not in existing_indexes:
            op.create_index(
                "idx_indicator_sym_tf_ts_name",
                "technical_indicators",
                ["symbol", "timeframe", "timestamp", "indicator_name"],
            )


def downgrade() -> None:
    """Downgrade schema: Remove canonical_timestamp and indexes."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "technical_indicators" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("technical_indicators")}
        if "idx_indicator_sym_tf_ts_name" in existing_indexes:
            op.drop_index("idx_indicator_sym_tf_ts_name", table_name="technical_indicators")

    if "price_ohlcv" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("price_ohlcv")}
        if "idx_price_sym_tf_canonical_ts" in existing_indexes:
            op.drop_index("idx_price_sym_tf_canonical_ts", table_name="price_ohlcv")

        existing_cols = {col["name"] for col in insp.get_columns("price_ohlcv")}
        if "canonical_timestamp" in existing_cols:
            op.drop_column("price_ohlcv", "canonical_timestamp")

    if "price_ohlcv_rejected" in existing_tables:
        op.drop_table("price_ohlcv_rejected")
