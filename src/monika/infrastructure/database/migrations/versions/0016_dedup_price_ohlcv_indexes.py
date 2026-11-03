"""dedup price_ohlcv redundant btree index

Revision ID: 0016_dedup_price_ohlcv_indexes
Revises: 0015_decision_refl_pos_idx
Create Date: 2026-11-03 11:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_dedup_price_ohlcv_indexes"
down_revision: Union[str, Sequence[str], None] = "0015_decision_refl_pos_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Drop redundant idx_price_sym_tf_ts index duplicate of uq_price_sym_tf_ts."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "price_ohlcv" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("price_ohlcv")}
        if "idx_price_sym_tf_ts" in existing_indexes:
            op.drop_index(
                "idx_price_sym_tf_ts",
                table_name="price_ohlcv",
            )


def downgrade() -> None:
    """Downgrade schema: Recreate idx_price_sym_tf_ts index on price_ohlcv."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "price_ohlcv" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("price_ohlcv")}
        if "idx_price_sym_tf_ts" not in existing_indexes:
            op.create_index(
                "idx_price_sym_tf_ts",
                "price_ohlcv",
                ["symbol", "timeframe", "timestamp"],
                unique=False,
            )
