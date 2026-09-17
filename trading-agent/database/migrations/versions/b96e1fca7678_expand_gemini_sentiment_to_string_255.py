"""Expand gemini_sentiment to String(255)

Revision ID: b96e1fca7678
Revises: 88b6f559ecd1
Create Date: 2026-08-14 07:42:03.822829

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b96e1fca7678'
down_revision: Union[str, Sequence[str], None] = '88b6f559ecd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('news_items', 'gemini_sentiment',
               existing_type=sa.VARCHAR(length=30),
               type_=sa.String(length=255),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('news_items', 'gemini_sentiment',
               existing_type=sa.String(length=255),
               type_=sa.VARCHAR(length=30),
               existing_nullable=True)
