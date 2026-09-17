"""Add bond_yield_data table

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-08-29 15:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2b3c4e5f6a7'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
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

    if 'bond_yield_data' not in existing_tables:
        op.create_table(
            'bond_yield_data',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('country_tenor', sa.String(length=20), nullable=False),
            sa.Column('yield_percent', sa.Float(), nullable=False),
            sa.Column('date', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('country_tenor', 'date', name='uq_bond_yield_country_date'),
        )
        op.create_index('idx_bond_yield_ct_date', 'bond_yield_data', ['country_tenor', 'date'])


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = _get_existing_tables(conn)
    if 'bond_yield_data' in existing_tables:
        op.drop_table('bond_yield_data')
