"""Make decision_reflections.analysis_id nullable

Revision ID: n1a2b3c4d5e6
Revises: m1a2b3c4d5e6
Create Date: 2026-09-17 08:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n1a2b3c4d5e6'
down_revision: Union[str, None] = 'm1a2b3c4d5e6'
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

    if 'decision_reflections' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('decision_reflections')}
        if 'analysis_id' in cols and not cols['analysis_id'].get('nullable', False):
            op.alter_column(
                'decision_reflections',
                'analysis_id',
                existing_type=sa.Integer(),
                nullable=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if 'decision_reflections' in tables:
        insp = sa.inspect(conn)
        cols = {c['name']: c for c in insp.get_columns('decision_reflections')}
        if 'analysis_id' in cols and cols['analysis_id'].get('nullable', True):
            op.alter_column(
                'decision_reflections',
                'analysis_id',
                existing_type=sa.Integer(),
                nullable=False,
            )
