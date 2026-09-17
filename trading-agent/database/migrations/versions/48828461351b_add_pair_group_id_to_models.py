"""add_pair_group_id_to_models

Revision ID: 48828461351b
Revises: c71ec30c5875
Create Date: 2026-08-20 19:54:18.139507

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48828461351b'
down_revision: Union[str, Sequence[str], None] = 'c71ec30c5875'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('asset_analysis', sa.Column('pair_group_id', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_asset_analysis_pair_group_id'), 'asset_analysis', ['pair_group_id'], unique=False)
    op.add_column('positions', sa.Column('pair_group_id', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_positions_pair_group_id'), 'positions', ['pair_group_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_positions_pair_group_id'), table_name='positions')
    op.drop_column('positions', 'pair_group_id')
    op.drop_index(op.f('ix_asset_analysis_pair_group_id'), table_name='asset_analysis')
    op.drop_column('asset_analysis', 'pair_group_id')
