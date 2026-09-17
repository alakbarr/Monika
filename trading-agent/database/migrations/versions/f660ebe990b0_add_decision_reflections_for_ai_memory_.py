"""Add decision_reflections for AI Memory and What-Ifs

Revision ID: f660ebe990b0
Revises: b96e1fca7678
Create Date: 2026-08-15 10:17:19.270148

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f660ebe990b0'
down_revision: Union[str, Sequence[str], None] = 'b96e1fca7678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('decision_reflections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('analysis_id', sa.Integer(), nullable=False),
    sa.Column('position_id', sa.Integer(), nullable=True),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('decision', sa.String(length=10), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('confluence_score', sa.Integer(), nullable=True),
    sa.Column('rationale_summary', sa.Text(), nullable=True),
    sa.Column('outcome_pnl_usd', sa.Float(), nullable=True),
    sa.Column('holding_hours', sa.Float(), nullable=True),
    sa.Column('exit_reason', sa.String(length=50), nullable=True),
    sa.Column('was_profitable', sa.Boolean(), nullable=True),
    sa.Column('reflection_text', sa.Text(), nullable=True),
    sa.Column('lesson_tags', sa.String(length=500), nullable=True),
    sa.Column('debate_summary', sa.Text(), nullable=True),
    sa.Column('debate_verdict', sa.String(length=20), nullable=True),
    sa.Column('pre_debate_confidence', sa.Float(), nullable=True),
    sa.Column('is_paper_whatif', sa.Boolean(), nullable=False),
    sa.Column('whatif_reason', sa.String(length=50), nullable=True),
    sa.Column('whatif_entry_price', sa.Float(), nullable=True),
    sa.Column('whatif_price_24h', sa.Float(), nullable=True),
    sa.Column('whatif_hypothetical_pnl_pips', sa.Float(), nullable=True),
    sa.Column('whatif_sl_would_hit', sa.Boolean(), nullable=True),
    sa.Column('whatif_tp_would_hit', sa.Boolean(), nullable=True),
    sa.Column('whatif_direction_correct', sa.Boolean(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['analysis_id'], ['asset_analysis.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_drefl_created', 'decision_reflections', ['created_at'], unique=False)
    op.create_index('idx_drefl_paper', 'decision_reflections', ['is_paper_whatif', 'status'], unique=False)
    op.create_index('idx_drefl_symbol_status', 'decision_reflections', ['symbol', 'status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_drefl_symbol_status', table_name='decision_reflections')
    op.drop_index('idx_drefl_paper', table_name='decision_reflections')
    op.drop_index('idx_drefl_created', table_name='decision_reflections')
    op.drop_table('decision_reflections')
