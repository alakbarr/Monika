"""rename_news_items_gemini_columns_to_universal

Revision ID: f28a9b3c4d5e
Revises: c7ea30d48aee
Create Date: 2026-08-23 13:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f28a9b3c4d5e'
down_revision: Union[str, Sequence[str], None] = 'c7ea30d48aee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: rename news_items gemini columns to universal impact and sentiment."""
    # 1. Rename columns in news_items
    op.alter_column('news_items', 'gemini_impact', new_column_name='impact')
    op.alter_column('news_items', 'gemini_sentiment', new_column_name='sentiment')

    # 2. Sync system_config keys if present
    conn = op.get_bind()
    try:
        conn.execute(sa.text("""
            INSERT INTO system_config (key, value, description)
            SELECT 'llm_preprocessed_latest', value, description FROM system_config WHERE key = 'gemini_preprocessed_latest'
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """))
    except Exception:
        pass


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('news_items', 'impact', new_column_name='gemini_impact')
    op.alter_column('news_items', 'sentiment', new_column_name='gemini_sentiment')
