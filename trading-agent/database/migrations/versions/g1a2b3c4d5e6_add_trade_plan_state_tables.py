"""Add trade_plans and trade_plan_legs tables for multi-phase execution

Revision ID: g1a2b3c4d5e6
Revises: f1a2b3c4d5e6
Create Date: 2026-09-05 18:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
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
    existing_tables = _get_existing_tables(conn)

    # 1. Table: trade_plans
    if 'trade_plans' not in existing_tables:
        op.create_table(
            'trade_plans',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('analysis_id', sa.Integer(), sa.ForeignKey('asset_analysis.id'), nullable=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('direction', sa.String(length=10), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='PENDING_PROBE'),
            sa.Column('entry_price', sa.Float(), nullable=False),
            sa.Column('stop_loss', sa.Float(), nullable=False),
            sa.Column('take_profit', sa.Float(), nullable=True),
            sa.Column('take_profit_1', sa.Float(), nullable=True),
            sa.Column('take_profit_2', sa.Float(), nullable=True),
            sa.Column('total_volume', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('atr_at_creation', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
        )
        try:
            op.create_index('ix_trade_plans_symbol', 'trade_plans', ['symbol'])
            op.create_index('ix_trade_plans_status', 'trade_plans', ['status'])
            op.create_index('ix_trade_plans_analysis_id', 'trade_plans', ['analysis_id'])
            op.create_index('idx_trade_plan_symbol_status', 'trade_plans', ['symbol', 'status'])
        except Exception:
            pass

    # 2. Table: trade_plan_legs
    if 'trade_plan_legs' not in existing_tables:
        op.create_table(
            'trade_plan_legs',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('plan_id', sa.Integer(), sa.ForeignKey('trade_plans.id', ondelete='CASCADE'), nullable=False),
            sa.Column('leg_type', sa.String(length=20), nullable=False),
            sa.Column('volume', sa.Float(), nullable=False),
            sa.Column('target_entry', sa.Float(), nullable=False),
            sa.Column('actual_entry', sa.Float(), nullable=True),
            sa.Column('stop_loss', sa.Float(), nullable=False),
            sa.Column('take_profit', sa.Float(), nullable=True),
            sa.Column('ticket_id', sa.Integer(), nullable=True),
            sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id'), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('exit_price', sa.Float(), nullable=True),
            sa.Column('pnl_usd', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_trade_plan_legs_plan_id', 'trade_plan_legs', ['plan_id'])
            op.create_index('ix_trade_plan_legs_status', 'trade_plan_legs', ['status'])
            op.create_index('idx_trade_plan_leg_plan_status', 'trade_plan_legs', ['plan_id', 'status'])
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = _get_existing_tables(conn)
    if 'trade_plan_legs' in existing_tables:
        op.drop_table('trade_plan_legs')
    if 'trade_plans' in existing_tables:
        op.drop_table('trade_plans')
