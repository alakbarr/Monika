"""add_benchmark_tables_and_cache_cost_columns

Revision ID: 0003_benchmark_cache_cost
Revises: c83c5e451412
Create Date: 2026-10-05 12:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_benchmark_cache_cost"
down_revision: Union[str, Sequence[str], None] = "c83c5e451412"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    # 1. Create llm_benchmark_run if missing
    if "llm_benchmark_run" not in existing_tables:
        op.create_table(
            "llm_benchmark_run",
            sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("judge_model", sa.String(length=160), nullable=False),
            sa.Column("reference_model", sa.String(length=160), nullable=False),
            sa.Column("tasks_json", sa.Text(), nullable=True),
            sa.Column("models_json", sa.Text(), nullable=True),
        )

    # 2. Create llm_benchmark_result if missing
    if "llm_benchmark_result" not in existing_tables:
        op.create_table(
            "llm_benchmark_result",
            sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
            sa.Column(
                "run_id",
                sa.Integer(),
                sa.ForeignKey("llm_benchmark_run.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("task_id", sa.String(length=80), nullable=False, index=True),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("model_name", sa.String(length=160), nullable=False, index=True),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("context_key", sa.String(length=160), nullable=False),
            sa.Column("input_tokens", sa.Integer(), default=0),
            sa.Column("output_tokens", sa.Integer(), default=0),
            sa.Column("cost_usd", sa.Float(), default=0.0),
            sa.Column("latency_s", sa.Float(), default=0.0),
            sa.Column("schema_valid", sa.Boolean(), default=False),
            sa.Column("deterministic_score", sa.Float(), nullable=True),
            sa.Column("judge_scores_json", sa.Text(), nullable=True),
            sa.Column("judge_overall", sa.Float(), nullable=True),
            sa.Column("overall_score", sa.Float(), nullable=True),
            sa.Column("raw_output", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("cached_tokens", sa.Integer(), default=0),
            sa.Column("cost_usd_no_cache", sa.Float(), default=0.0),
            sa.Column("cost_usd_with_cache", sa.Float(), default=0.0),
            sa.Column("thinking_tokens", sa.Integer(), default=0),
            sa.Column("provider_route", sa.String(length=80), default="direct"),
        )
    else:
        # Table exists: check and add missing columns
        existing_cols = [c["name"] for c in insp.get_columns("llm_benchmark_result")]
        new_cols = [
            ("cached_tokens", sa.Column("cached_tokens", sa.Integer(), server_default="0")),
            ("cost_usd_no_cache", sa.Column("cost_usd_no_cache", sa.Float(), server_default="0.0")),
            ("cost_usd_with_cache", sa.Column("cost_usd_with_cache", sa.Float(), server_default="0.0")),
            ("thinking_tokens", sa.Column("thinking_tokens", sa.Integer(), server_default="0")),
            ("provider_route", sa.Column("provider_route", sa.String(length=80), server_default="direct")),
        ]
        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                op.add_column("llm_benchmark_result", col_def)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "llm_benchmark_result" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("llm_benchmark_result")}
        with op.batch_alter_table("llm_benchmark_result") as batch_op:
            for col_name in (
                "provider_route",
                "thinking_tokens",
                "cost_usd_with_cache",
                "cost_usd_no_cache",
                "cached_tokens",
            ):
                if col_name in existing_cols:
                    batch_op.drop_column(col_name)
