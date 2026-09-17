"""add_alpha_columns

Revision ID: 0dc17a9c300a
Revises: f660ebe990b0
Create Date: 2026-08-16 09:04:52.828024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0dc17a9c300a'
down_revision: Union[str, Sequence[str], None] = 'f660ebe990b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('decision_reflections', sa.Column('alpha_return', sa.Float(), nullable=True))
    op.add_column('decision_reflections', sa.Column('benchmark_name', sa.String(length=50), nullable=True))
    op.add_column('decision_reflections', sa.Column('benchmark_return', sa.Float(), nullable=True))
    op.add_column('decision_reflections', sa.Column('alpha_lesson', sa.Text(), nullable=True))
    # Note: skipping auto-generated drops of other tables as they belong to legacy systems.


def downgrade() -> None:
    op.drop_column('decision_reflections', 'alpha_lesson')
    op.drop_column('decision_reflections', 'benchmark_return')
    op.drop_column('decision_reflections', 'benchmark_name')
    op.drop_column('decision_reflections', 'alpha_return')
