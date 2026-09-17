"""add_ssvp_context_fields_to_asset_analysis

Revision ID: c060f97f0f25
Revises: 6b415f7529f6
Create Date: 2026-08-16 19:10:12.284154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c060f97f0f25'
down_revision: Union[str, Sequence[str], None] = '6b415f7529f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if columns exist first to avoid errors if they were already added (e.g., by testing framework)
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [col['name'] for col in insp.get_columns('asset_analysis')]
    
    if 'context_snapshot_id' not in columns:
        op.add_column('asset_analysis', sa.Column('context_snapshot_id', sa.String(length=64), nullable=True))
    if 'brief_age_at_analysis_hours' not in columns:
        op.add_column('asset_analysis', sa.Column('brief_age_at_analysis_hours', sa.Float(), nullable=True))
    if 'ssvp_cds_score_at_analysis' not in columns:
        op.add_column('asset_analysis', sa.Column('ssvp_cds_score_at_analysis', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('asset_analysis', 'ssvp_cds_score_at_analysis')
    op.drop_column('asset_analysis', 'brief_age_at_analysis_hours')
    op.drop_column('asset_analysis', 'context_snapshot_id')
