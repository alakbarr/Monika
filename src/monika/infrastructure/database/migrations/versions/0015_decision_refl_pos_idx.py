"""add missing index on decision_reflections.position_id

Revision ID: 0015_decision_refl_pos_idx
Revises: 0014_widen_source_strategy_id
Create Date: 2026-10-30 02:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_decision_refl_pos_idx"
down_revision: Union[str, Sequence[str], None] = "0014_widen_source_strategy_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add ix_decision_reflections_position_id index on decision_reflections(position_id)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "decision_reflections" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("decision_reflections")}
        if "ix_decision_reflections_position_id" not in existing_indexes:
            op.create_index(
                "ix_decision_reflections_position_id",
                "decision_reflections",
                ["position_id"],
                unique=False,
            )


def downgrade() -> None:
    """Downgrade schema: Drop ix_decision_reflections_position_id index on decision_reflections."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "decision_reflections" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("decision_reflections")}
        if "ix_decision_reflections_position_id" in existing_indexes:
            op.drop_index(
                "ix_decision_reflections_position_id",
                table_name="decision_reflections",
            )
