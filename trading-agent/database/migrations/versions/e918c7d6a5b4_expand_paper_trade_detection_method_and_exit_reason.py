"""Expand paper trade detection_method and exit_reason to VARCHAR(100)

Revision ID: e918c7d6a5b4
Revises: a8d29c4e1f7b
Create Date: 2026-08-27 19:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e918c7d6a5b4'
down_revision: Union[str, None] = 'a8d29c4e1f7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'paper_trade_records',
        'detection_method',
        existing_type=sa.String(length=20),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        'paper_trade_records',
        'exit_reason',
        existing_type=sa.String(length=20),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'paper_trade_records',
        'detection_method',
        existing_type=sa.String(length=100),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
    op.alter_column(
        'paper_trade_records',
        'exit_reason',
        existing_type=sa.String(length=100),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
