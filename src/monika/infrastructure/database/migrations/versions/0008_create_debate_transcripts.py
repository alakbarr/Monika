"""create_debate_transcripts

Revision ID: 0008_create_debate_transcripts
Revises: 0007_sync_queue_schemas
Create Date: 2026-10-18 20:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_create_debate_transcripts"
down_revision: Union[str, Sequence[str], None] = "0007_sync_queue_schemas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create debate_transcripts table mandated by PRD.md §237."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "debate_transcripts" not in existing_tables:
        op.create_table(
            "debate_transcripts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("cycle_id", sa.String(64), nullable=True),
            sa.Column("symbol", sa.String(20), nullable=False),
            sa.Column("timeframe", sa.String(10), nullable=True, server_default="H1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("bull_perspective", sa.JSON(), nullable=True),
            sa.Column("bear_perspective", sa.JSON(), nullable=True),
            sa.Column("judge_adjudication", sa.JSON(), nullable=True),
            sa.Column("final_decision", sa.String(20), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("confluence_score", sa.Float(), nullable=True),
            sa.Column("risk_multiplier", sa.Float(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
        )

    # Re-inspect to create indexes safely
    insp = sa.inspect(bind)
    existing_indexes = (
        {idx.get("name") for idx in insp.get_indexes("debate_transcripts")}
        if "debate_transcripts" in insp.get_table_names()
        else set()
    )

    if "idx_debate_transcripts_cycle" not in existing_indexes:
        op.create_index("idx_debate_transcripts_cycle", "debate_transcripts", ["cycle_id"])
    if "idx_debate_transcripts_sym_created" not in existing_indexes:
        op.create_index("idx_debate_transcripts_sym_created", "debate_transcripts", ["symbol", "created_at"])


def downgrade() -> None:
    """Downgrade schema: Drop debate_transcripts table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "debate_transcripts" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("debate_transcripts")}
        if "idx_debate_transcripts_cycle" in existing_indexes:
            op.drop_index("idx_debate_transcripts_cycle", table_name="debate_transcripts")
        if "idx_debate_transcripts_sym_created" in existing_indexes:
            op.drop_index("idx_debate_transcripts_sym_created", table_name="debate_transcripts")
        op.drop_table("debate_transcripts")
