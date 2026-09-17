"""Add orders, order_events, and positions.order_id for typed order lifecycle

Revision ID: i1a2b3c4d5e6
Revises: h1a2b3c4d5e6
Create Date: 2026-09-05 22:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i1a2b3c4d5e6'
down_revision: Union[str, None] = 'h1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_tables(conn) -> set:
    try:
        insp = sa.inspect(conn)
        return set(insp.get_table_names())
    except Exception:
        return set()


def _get_existing_columns(conn, table_name: str) -> set:
    try:
        insp = sa.inspect(conn)
        return {c['name'] for c in insp.get_columns(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    # 1. Create orders table if not exists
    if 'orders' not in tables:
        op.create_table(
            'orders',
            sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
            sa.Column('client_order_id', sa.String(length=64), nullable=False),
            sa.Column('analysis_id', sa.Integer(), sa.ForeignKey('asset_analysis.id'), nullable=True),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('order_type', sa.String(length=20), nullable=False),
            sa.Column('direction', sa.String(length=10), nullable=False),
            sa.Column('requested_price', sa.Float(), nullable=False),
            sa.Column('executed_price', sa.Float(), nullable=True),
            sa.Column('slippage_pips', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('requested_volume', sa.Float(), nullable=False),
            sa.Column('filled_volume', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('status', sa.String(length=30), nullable=False, server_default='pending_submit'),
            sa.Column('mt5_ticket', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_orders_client_order_id', 'orders', ['client_order_id'], unique=True)
        op.create_index('ix_orders_analysis_id', 'orders', ['analysis_id'])
        op.create_index('ix_orders_symbol', 'orders', ['symbol'])
        op.create_index('ix_orders_status', 'orders', ['status'])
        op.create_index('ix_orders_mt5_ticket', 'orders', ['mt5_ticket'])

    # 2. Create order_events audit trail table if not exists
    if 'order_events' not in tables:
        op.create_table(
            'order_events',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
            sa.Column('order_id', sa.String(length=64), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
            sa.Column('from_status', sa.String(length=30), nullable=False),
            sa.Column('to_status', sa.String(length=30), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_order_events_order_id', 'order_events', ['order_id'])

    # 3. Add order_id to positions table if not exists
    if 'positions' in tables:
        cols = _get_existing_columns(conn, 'positions')
        if 'order_id' not in cols:
            op.add_column('positions', sa.Column('order_id', sa.String(length=64), sa.ForeignKey('orders.id'), nullable=True))
            try:
                op.create_index('ix_positions_order_id', 'positions', ['order_id'])
            except Exception:
                pass


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'positions' in tables:
        cols = _get_existing_columns(conn, 'positions')
        if 'order_id' in cols:
            try:
                op.drop_index('ix_positions_order_id', table_name='positions')
            except Exception:
                pass
            op.drop_column('positions', 'order_id')

    if 'order_events' in tables:
        op.drop_table('order_events')

    if 'orders' in tables:
        op.drop_table('orders')
