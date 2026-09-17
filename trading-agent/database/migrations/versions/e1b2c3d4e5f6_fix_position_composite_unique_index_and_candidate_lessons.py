"""Fix position composite unique index and candidate lessons condition_tags

Revision ID: e1b2c3d4e5f6
Revises: d2b3c4e5f6a7
Create Date: 2026-08-30 07:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1b2c3d4e5f6'
down_revision: Union[str, None] = 'd2b3c4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_columns(conn, table_name: str) -> set:
    try:
        insp = sa.inspect(conn)
        return {col['name'] for col in insp.get_columns(table_name)}
    except Exception:
        return set()


def _get_existing_indexes(conn, table_name: str) -> set:
    try:
        insp = sa.inspect(conn)
        return {idx['name'] for idx in insp.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    pos_indexes = _get_existing_indexes(conn, 'positions')
    cand_columns = _get_existing_columns(conn, 'candidate_lessons')

    # 1. Drop old single-column unique index if exists, and recreate as composite ('analysis_id', 'mt5_ticket')
    if 'uq_position_analysis_open' in pos_indexes:
        op.drop_index('uq_position_analysis_open', table_name='positions', postgresql_where=sa.text("status = 'open'"))
    
    op.create_index(
        'uq_position_analysis_open',
        'positions',
        ['analysis_id', 'mt5_ticket'],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND analysis_id IS NOT NULL")
    )

    # 2. Add condition_tags column to candidate_lessons if missing
    if 'condition_tags' not in cand_columns:
        op.add_column('candidate_lessons', sa.Column('condition_tags', sa.String(length=255), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    pos_indexes = _get_existing_indexes(conn, 'positions')
    cand_columns = _get_existing_columns(conn, 'candidate_lessons')

    if 'condition_tags' in cand_columns:
        op.drop_column('candidate_lessons', 'condition_tags')

    if 'uq_position_analysis_open' in pos_indexes:
        op.drop_index('uq_position_analysis_open', table_name='positions')
        op.create_index(
            'uq_position_analysis_open',
            'positions',
            ['analysis_id'],
            unique=True,
            postgresql_where=sa.text("status = 'open'")
        )
