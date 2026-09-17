"""add_news_digest_slices_chronicle_and_prefilter

Revision ID: f39b1a2c3d4e
Revises: e819b2c3d4f5
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f39b1a2c3d4e'
down_revision: Union[str, None] = 'e819b2c3d4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add prefilter_flags to news_items
    op.add_column('news_items', sa.Column('prefilter_flags', sa.String(length=50), nullable=True))

    # Migrate existing prefilter sentiments:
    op.execute("""
        UPDATE news_items 
        SET prefilter_flags = 'IRRELEVANT', sentiment = NULL
        WHERE sentiment = 'IRRELEVANT_PREFILTERED'
    """)
    op.execute("""
        UPDATE news_items
        SET prefilter_flags = 'DUPLICATE', sentiment = NULL
        WHERE sentiment = 'DUPLICATE_PREFILTERED'
    """)

    # 2. Create news_digest_slices table
    op.create_table(
        'news_digest_slices',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('trigger', sa.String(length=20), nullable=False, server_default='scheduled'),
        sa.Column('period_hours', sa.Float(), nullable=False, server_default='2.0'),
        sa.Column('items_processed', sa.Integer(), nullable=True),
        sa.Column('breaking_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('high_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency_sections', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
    )
    op.create_index('ix_news_digest_slices_period_start', 'news_digest_slices', ['period_start'])
    op.create_index('ix_news_digest_slices_period', 'news_digest_slices', ['period_start', 'period_end'])

    # 3. Create market_chronicle table
    op.create_table(
        'market_chronicle',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('event_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('headline', sa.String(length=300), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=True),
        sa.Column('currencies_affected', sa.String(length=100), nullable=True),
        sa.Column('severity', sa.String(length=10), nullable=False, server_default='medium'),
        sa.Column('source_news_id', sa.Integer(), nullable=True),
        sa.Column('source_brief_id', sa.Integer(), nullable=True),
        sa.Column('is_ongoing', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
    )
    op.create_index('ix_market_chronicle_event_date', 'market_chronicle', ['event_date'])


def downgrade() -> None:
    op.drop_index('ix_market_chronicle_event_date', table_name='market_chronicle')
    op.drop_table('market_chronicle')

    op.drop_index('ix_news_digest_slices_period', table_name='news_digest_slices')
    op.drop_index('ix_news_digest_slices_period_start', table_name='news_digest_slices')
    op.drop_table('news_digest_slices')

    op.drop_column('news_items', 'prefilter_flags')
