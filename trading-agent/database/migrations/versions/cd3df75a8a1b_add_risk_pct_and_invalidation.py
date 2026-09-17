"""add_risk_pct_and_invalidation

Revision ID: cd3df75a8a1b
Revises: 4156a1f2790b
Create Date: 2026-08-11 08:40:18.523129

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd3df75a8a1b'
down_revision: Union[str, Sequence[str], None] = '4156a1f2790b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('asset_analysis') as batch_op:
        batch_op.add_column(sa.Column('invalidation_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('invalidation_direction', sa.String(length=10), nullable=True))
        
    with op.batch_alter_table('paper_trade_records') as batch_op:
        batch_op.add_column(sa.Column('risk_pct', sa.Float(), nullable=True))
        
    with op.batch_alter_table('positions') as batch_op:
        batch_op.add_column(sa.Column('analysis_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('is_paper', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_foreign_key('fk_positions_analysis_id', 'asset_analysis', ['analysis_id'], ['id'])

def downgrade() -> None:
    with op.batch_alter_table('positions') as batch_op:
        batch_op.drop_constraint('fk_positions_analysis_id', type_='foreignkey')
        batch_op.drop_column('is_paper')
        batch_op.drop_column('analysis_id')

    with op.batch_alter_table('paper_trade_records') as batch_op:
        batch_op.drop_column('risk_pct')

    with op.batch_alter_table('asset_analysis') as batch_op:
        batch_op.drop_column('invalidation_direction')
        batch_op.drop_column('invalidation_price')
    # ### end Alembic commands ###
