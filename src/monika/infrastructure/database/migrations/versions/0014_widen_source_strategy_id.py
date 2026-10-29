"""widen source_strategy_id in asset_analysis to varchar 100

Revision ID: 0014_widen_source_strategy_id
Revises: 0013_token_usage_cost_source_and_is_paid
Create Date: 2026-10-29 07:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_widen_source_strategy_id"
down_revision: Union[str, Sequence[str], None] = "0013_token_usage_cost_source_and_is_paid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Expand source_strategy_id from VARCHAR(50) to VARCHAR(100)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "asset_analysis" in existing_tables:
        existing_cols = {c["name"]: c for c in insp.get_columns("asset_analysis")}
        if "source_strategy_id" in existing_cols:
            with op.batch_alter_table("asset_analysis") as batch_op:
                batch_op.alter_column(
                    "source_strategy_id",
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=100),
                    existing_nullable=True,
                )


def downgrade() -> None:
    """Downgrade schema: Shrink source_strategy_id from VARCHAR(100) to VARCHAR(50)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "asset_analysis" in existing_tables:
        existing_cols = {c["name"]: c for c in insp.get_columns("asset_analysis")}
        if "source_strategy_id" in existing_cols:
            with op.batch_alter_table("asset_analysis") as batch_op:
                batch_op.alter_column(
                    "source_strategy_id",
                    existing_type=sa.String(length=100),
                    type_=sa.String(length=50),
                    existing_nullable=True,
                )
