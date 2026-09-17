"""Add declarative partitioning infrastructure for price_ohlcv

Revision ID: j1a2b3c4d5e6
Revises: i1a2b3c4d5e6
Create Date: 2026-09-05 22:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'j1a2b3c4d5e6'
down_revision: Union[str, None] = 'i1a2b3c4d5e6'
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
    dialect_name = conn.dialect.name
    tables = _get_existing_tables(conn)

    # Declarative range partitioning is specific to PostgreSQL
    if dialect_name == "postgresql":
        if "price_ohlcv_partitioned" not in tables:
            # Create master partitioned table
            op.execute("""
                CREATE TABLE IF NOT EXISTS price_ohlcv_partitioned (
                    id BIGSERIAL,
                    symbol VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(10) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (id, timestamp),
                    CONSTRAINT uq_part_price_sym_tf_ts UNIQUE (symbol, timeframe, timestamp)
                ) PARTITION BY RANGE (timestamp);
            """)

            # Create default partition for fail-safe ingestion
            op.execute("""
                CREATE TABLE IF NOT EXISTS price_ohlcv_part_default
                PARTITION OF price_ohlcv_partitioned DEFAULT;
            """)

            # Create current month partition (2026-09)
            op.execute("""
                CREATE TABLE IF NOT EXISTS price_ohlcv_y2026_m09
                PARTITION OF price_ohlcv_partitioned
                FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');
            """)

            # Create indices on partitioned table
            op.execute("""
                CREATE INDEX IF NOT EXISTS idx_part_price_sym_tf_ts
                ON price_ohlcv_partitioned (symbol, timeframe, timestamp);
            """)
    else:
        # Fallback for SQLite / non-PostgreSQL testing environments
        if "price_ohlcv_partitioned" not in tables:
            op.create_table(
                'price_ohlcv_partitioned',
                sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
                sa.Column('symbol', sa.String(length=20), nullable=False),
                sa.Column('timeframe', sa.String(length=10), nullable=False),
                sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
                sa.Column('open', sa.Float(), nullable=False),
                sa.Column('high', sa.Float(), nullable=False),
                sa.Column('low', sa.Float(), nullable=False),
                sa.Column('close', sa.Float(), nullable=False),
                sa.Column('volume', sa.Float(), nullable=False),
            )
            op.create_index('idx_part_price_sym_tf_ts', 'price_ohlcv_partitioned', ['symbol', 'timeframe', 'timestamp'])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _get_existing_tables(conn)

    if "price_ohlcv_part_default" in tables:
        op.execute("DROP TABLE IF EXISTS price_ohlcv_part_default CASCADE;")
    if "price_ohlcv_y2026_m09" in tables:
        op.execute("DROP TABLE IF EXISTS price_ohlcv_y2026_m09 CASCADE;")
    if "price_ohlcv_partitioned" in tables:
        op.execute("DROP TABLE IF EXISTS price_ohlcv_partitioned CASCADE;")
