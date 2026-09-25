"""Add llm_benchmark_run and llm_benchmark_result tables for LLM benchmark evaluations

Revision ID: s1a2b3c4d5e6
Revises: r1a2b3c4d5e6
Create Date: 2026-09-26 01:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's1a2b3c4d5e6'
down_revision: Union[str, None] = 'r1a2b3c4d5e6'
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

    if 'llm_benchmark_run' not in tables:
        op.create_table(
            'llm_benchmark_run',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('judge_model', sa.String(length=160), nullable=False),
            sa.Column('reference_model', sa.String(length=160), nullable=False),
            sa.Column('tasks_json', sa.Text(), nullable=True),
            sa.Column('models_json', sa.Text(), nullable=True),
        )

    if 'llm_benchmark_result' not in tables:
        op.create_table(
            'llm_benchmark_result',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('run_id', sa.Integer(), sa.ForeignKey('llm_benchmark_run.id', ondelete='CASCADE'), nullable=False),
            sa.Column('task_id', sa.String(length=80), nullable=False),
            sa.Column('category', sa.String(length=40), nullable=False),
            sa.Column('model_name', sa.String(length=160), nullable=False),
            sa.Column('provider', sa.String(length=40), nullable=False),
            sa.Column('context_key', sa.String(length=160), nullable=False),
            sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('latency_s', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('schema_valid', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('deterministic_score', sa.Float(), nullable=True),
            sa.Column('judge_scores_json', sa.Text(), nullable=True),
            sa.Column('judge_overall', sa.Float(), nullable=True),
            sa.Column('overall_score', sa.Float(), nullable=True),
            sa.Column('raw_output', sa.Text(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            'idx_llm_bench_res_run_id',
            'llm_benchmark_result',
            ['run_id'],
            unique=False
        )
        op.create_index(
            'idx_llm_bench_res_task_id',
            'llm_benchmark_result',
            ['task_id'],
            unique=False
        )
        op.create_index(
            'idx_llm_bench_res_model_name',
            'llm_benchmark_result',
            ['model_name'],
            unique=False
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'llm_benchmark_result' in tables:
        op.drop_index('idx_llm_bench_res_model_name', table_name='llm_benchmark_result')
        op.drop_index('idx_llm_bench_res_task_id', table_name='llm_benchmark_result')
        op.drop_index('idx_llm_bench_res_run_id', table_name='llm_benchmark_result')
        op.drop_table('llm_benchmark_result')

    if 'llm_benchmark_run' in tables:
        op.drop_table('llm_benchmark_run')
