"""add technical_indicators unique constraint

Revision ID: 0018_add_technical_indicators_unique_constraint
Revises: 0017_add_activity_log_composite_index
Create Date: 2026-11-04 21:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_add_technical_indicators_unique_constraint"
down_revision: Union[str, Sequence[str], None] = "0017_add_activity_log_composite_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create unique constraint on technical_indicators(symbol, timeframe, timestamp, indicator_name)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    is_pg = bind.dialect.name == "postgresql"

    if "technical_indicators" in existing_tables:
        # 1. Deduplicate any existing records before enforcing uniqueness
        try:
            if is_pg:
                bind.execute(
                    sa.text(
                        """
                        DELETE FROM technical_indicators a USING technical_indicators b
                        WHERE a.id < b.id
                          AND a.symbol = b.symbol
                          AND a.timeframe = b.timeframe
                          AND a.timestamp = b.timestamp
                          AND a.indicator_name = b.indicator_name;
                        """
                    )
                )
            else:
                bind.execute(
                    sa.text(
                        """
                        DELETE FROM technical_indicators
                        WHERE id NOT IN (
                            SELECT MAX(id) FROM technical_indicators
                            GROUP BY symbol, timeframe, timestamp, indicator_name
                        );
                        """
                    )
                )
        except Exception:
            pass

        # 2. Inspect existing unique constraints
        existing_uqs: set[str] = set()
        if hasattr(insp, "get_unique_constraints"):
            try:
                existing_uqs = {
                    uq.get("name") for uq in insp.get_unique_constraints("technical_indicators") if isinstance(uq, dict)
                }
            except Exception:
                pass
        if "uq_technical_indicators_record" not in existing_uqs:
            with op.batch_alter_table("technical_indicators") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_technical_indicators_record",
                    ["symbol", "timeframe", "timestamp", "indicator_name"],
                )


def downgrade() -> None:
    """Downgrade schema: Drop unique constraint on technical_indicators."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "technical_indicators" in existing_tables:
        existing_uqs: set[str] = set()
        if hasattr(insp, "get_unique_constraints"):
            try:
                existing_uqs = {
                    uq.get("name") for uq in insp.get_unique_constraints("technical_indicators") if isinstance(uq, dict)
                }
            except Exception:
                pass
        if "uq_technical_indicators_record" in existing_uqs:
            with op.batch_alter_table("technical_indicators") as batch_op:
                batch_op.drop_constraint("uq_technical_indicators_record", type_="unique")
