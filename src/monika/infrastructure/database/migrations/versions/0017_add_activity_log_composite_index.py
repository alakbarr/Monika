"""add activity_log composite index

Revision ID: 0017_add_activity_log_composite_index
Revises: 0016_dedup_price_ohlcv_indexes
Create Date: 2026-11-04 20:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_add_activity_log_composite_index"
down_revision: Union[str, Sequence[str], None] = "0016_dedup_price_ohlcv_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create composite index on activity_log(category, timestamp)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "activity_log" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("activity_log")}
        if "ix_activity_log_category_timestamp" not in existing_indexes:
            op.create_index(
                "ix_activity_log_category_timestamp",
                "activity_log",
                ["category", "timestamp"],
                unique=False,
            )


def downgrade() -> None:
    """Downgrade schema: Drop composite index on activity_log(category, timestamp)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "activity_log" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("activity_log")}
        if "ix_activity_log_category_timestamp" in existing_indexes:
            op.drop_index(
                "ix_activity_log_category_timestamp",
                table_name="activity_log",
            )
