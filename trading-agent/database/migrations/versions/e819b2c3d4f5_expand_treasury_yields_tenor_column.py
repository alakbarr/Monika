"""expand_treasury_yields_tenor_column

Revision ID: e819b2c3d4f5
Revises: f28a9b3c4d5e
Create Date: 2026-08-23 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e819b2c3d4f5'
down_revision: Union[str, None] = 'f28a9b3c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expand tenor column length from VARCHAR(10) to VARCHAR(32) to accommodate '10Y_INFLATION', '10Y_REAL', etc.
    op.alter_column(
        'treasury_yields',
        'tenor',
        existing_type=sa.String(length=10),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'treasury_yields',
        'tenor',
        existing_type=sa.String(length=32),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
