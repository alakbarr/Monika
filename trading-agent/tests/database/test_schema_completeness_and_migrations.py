"""
Unit and integration tests for complete database schema synchronization and Alembic migration chain.
Verifies zero gap between SQLAlchemy 2.0 declarative models (42 tables) and database migrations.
"""
import pytest
import os
import glob
import sys
import types
import importlib.util
from datetime import datetime, timezone, timedelta
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from database.models import Base, TradeOutcome, AssetAnalysis, Position, PaperTradeRecord, DecisionReflection, PrescreenLog, CandidateLesson


def _ensure_mock_alembic():
    """Ensure alembic and alembic.op exist in sys.modules to prevent local package shadowing."""
    if 'alembic' not in sys.modules or not hasattr(sys.modules['alembic'], 'op'):
        mock_alembic = types.ModuleType('alembic')
        mock_op = types.ModuleType('alembic.op')
        mock_alembic.op = mock_op
        mock_alembic.context = types.ModuleType('alembic.context')
        sys.modules['alembic'] = mock_alembic
        sys.modules['alembic.op'] = mock_op
        sys.modules['alembic.context'] = mock_alembic.context


def test_alembic_migration_chain_continuity():
    """Verify that all migration files in database/migrations/versions form an unbroken chain."""
    _ensure_mock_alembic()
    migrations_dir = os.path.join(os.path.dirname(__file__), '../../database/migrations/versions')
    migration_files = [f for f in glob.glob(os.path.join(migrations_dir, '*.py')) if not f.endswith('__init__.py')]
    
    assert len(migration_files) >= 33, f"Expected at least 33 migration files, found {len(migration_files)}"
    
    nodes = {}
    for f in migration_files:
        spec = importlib.util.spec_from_file_location('mig_mod_' + os.path.basename(f)[:-3], f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        nodes[mod.revision] = {'file': os.path.basename(f), 'down': mod.down_revision}

    # Trace from root to head
    root_rev = '9c013c8f495b'
    assert root_rev in nodes, f"Root revision {root_rev} not found"
    assert nodes[root_rev]['down'] is None, "Root down_revision must be None"
    
    visited = []
    curr = root_rev
    while curr:
        visited.append(curr)
        next_rev = None
        for rev, data in nodes.items():
            if data['down'] == curr or (isinstance(data['down'], (tuple, list)) and curr in data['down']):
                next_rev = rev
                break
        curr = next_rev

    assert len(visited) == len(nodes), f"Broken chain! Total nodes: {len(nodes)}, Visited in sequence: {len(visited)}"
    assert visited[-1] == 'n1a2b3c4d5e6', f"Expected head revision to be n1a2b3c4d5e6, got {visited[-1]}"


def test_schema_completeness_all_models():
    """Verify that 100% of all 42 tables and columns in Base.metadata are covered across migrations."""
    _ensure_mock_alembic()
    tables = {}

    class MockBatchOp:
        def __init__(self, table_name):
            self.table_name = table_name
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def add_column(self, column):
            tables.setdefault(self.table_name, {})[column.name] = str(column.type)
        def drop_column(self, col_name):
            if self.table_name in tables and col_name in tables[self.table_name]:
                del tables[self.table_name][col_name]
        def create_foreign_key(self, *a, **kw): pass
        def drop_constraint(self, *a, **kw): pass

    class MockOp:
        @staticmethod
        def f(name): return name
        @staticmethod
        def get_bind():
            class MockDialect:
                name = "postgresql"
            class MockConn:
                dialect = MockDialect()
                def execute(self, stmt): pass
            return MockConn()
        @staticmethod
        def create_table(table_name, *columns, **kw):
            cols = {}
            for col in columns:
                if isinstance(col, sa.Column):
                    cols[col.name] = str(col.type)
            tables[table_name] = cols
        @staticmethod
        def drop_table(table_name, **kw):
            tables.pop(table_name, None)
        @staticmethod
        def add_column(table_name, column, **kw):
            tables.setdefault(table_name, {})[column.name] = str(column.type)
        @staticmethod
        def drop_column(table_name, col_name, **kw):
            if table_name in tables and col_name in tables[table_name]:
                del tables[table_name][col_name]
        @staticmethod
        def alter_column(table_name, col_name, new_column_name=None, **kw):
            if table_name in tables and col_name in tables[table_name]:
                val = tables[table_name].pop(col_name)
                target = new_column_name if new_column_name else col_name
                tables[table_name][target] = val
        @staticmethod
        def create_index(*a, **kw): pass
        @staticmethod
        def drop_index(*a, **kw): pass
        @staticmethod
        def create_unique_constraint(*a, **kw): pass
        @staticmethod
        def drop_constraint(*a, **kw): pass
        @staticmethod
        def create_foreign_key(*a, **kw): pass
        @staticmethod
        def batch_alter_table(table_name, **kw):
            return MockBatchOp(table_name)
        @staticmethod
        def execute(sql, **kw):
            if isinstance(sql, str) and 'drop table if exists' in sql.lower():
                for part in sql.split():
                    if part.lower() not in ('drop', 'table', 'if', 'exists', 'cascade', ';') and not part.endswith('CASCADE'):
                        tables.pop(part.replace(';', '').strip(), None)

    migrations_dir = os.path.join(os.path.dirname(__file__), '../../database/migrations/versions')
    migration_files = [f for f in glob.glob(os.path.join(migrations_dir, '*.py')) if not f.endswith('__init__.py')]
    nodes = {}
    for f in migration_files:
        spec = importlib.util.spec_from_file_location('mig_mod_' + os.path.basename(f)[:-3], f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        nodes[mod.revision] = {'down': mod.down_revision, 'mod': mod}

    curr = '9c013c8f495b'
    while curr:
        mod = nodes[curr]['mod']
        mod.op = MockOp
        def mock_insp(conn):
            class MockInsp:
                def get_table_names(self): return list(tables.keys())
                def get_columns(self, t_name): return [{'name': c} for c in tables.get(t_name, {})]
            return MockInsp()
        sa.inspect = mock_insp
        mod.upgrade()
        next_rev = None
        for rev, data in nodes.items():
            if data['down'] == curr:
                next_rev = rev
                break
        curr = next_rev

    model_tables = Base.metadata.tables
    diff1 = set(model_tables.keys()) - set(tables.keys())
    diff2 = set(tables.keys()) - set(model_tables.keys())
    assert len(tables) == len(model_tables), f"Mismatch table counts: {len(tables)} vs {len(model_tables)}. In models not in mig: {diff1}, In mig not in models: {diff2}"

    for t_name, table in model_tables.items():
        assert t_name in tables, f"Table {t_name} is in models.py but missing in migrations!"
        m_cols = set(table.columns.keys())
        db_cols = set(tables[t_name].keys())
        missing = m_cols - db_cols
        assert not missing, f"Table {t_name} has missing columns in migrations: {missing}"


@pytest.mark.asyncio
async def test_trade_outcome_orm_query_execution():
    """Verify that TradeOutcome query with was_debate_modified and decision_source compiles and runs cleanly."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Insert a sample TradeOutcome
        to = TradeOutcome(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.1000,
            exit_price=1.1050,
            pnl_usd=50.0,
            was_profitable=True,
            was_debate_modified=True,
            decision_source="llm_debate",
            opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
            closed_at=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_reason="tp_hit"
        )
        session.add(to)
        await session.commit()

        # Simulate the exact query executed by CycleScheduler._send_daily_report
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        stmt = select(TradeOutcome).where(TradeOutcome.closed_at >= yesterday)
        res = (await session.execute(stmt)).scalars().all()

        assert len(res) == 1
        assert res[0].symbol == "EURUSD"
        assert res[0].was_debate_modified is True
        assert res[0].decision_source == "llm_debate"

    await engine.dispose()
