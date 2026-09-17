"""Add central_bank_rate_expectations table

Revision ID: m1a2b3c4d5e6
Revises: l1a2b3c4d5e6
Create Date: 2026-09-17 06:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm1a2b3c4d5e6'
down_revision: Union[str, None] = 'l1a2b3c4d5e6'
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

    if 'central_bank_rate_expectations' not in tables:
        op.create_table(
            'central_bank_rate_expectations',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('bank', sa.String(length=20), nullable=False),
            sa.Column('meeting_date', sa.String(length=30), nullable=False),
            sa.Column('current_rate', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('prob_hike', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('prob_hold', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('prob_cut', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('source', sa.String(length=50), nullable=False, server_default='centralbank.watch'),
            sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_central_bank_rate_expectations_bank', 'central_bank_rate_expectations', ['bank'])
        op.create_index('idx_cb_rate_exp_bank_date', 'central_bank_rate_expectations', ['bank', 'meeting_date'])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)
    if 'central_bank_rate_expectations' in tables:
        op.drop_index('idx_cb_rate_exp_bank_date', table_name='central_bank_rate_expectations')
        op.drop_index('ix_central_bank_rate_expectations_bank', table_name='central_bank_rate_expectations')
        op.drop_table('central_bank_rate_expectations')
