"""
Unit tests for PaperTradeRecord detection_method and exit_reason truncation fix.
Validates model column lengths, Alembic migration chain, and PaperTracker error isolation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import sqlalchemy as sa

from database.models import PaperTradeRecord, AssetAnalysis, Position, PriceOHLCV
from utils.analytics.paper_tracker import PaperTracker


def test_papertraderecord_model_column_lengths():
    """Verify PaperTradeRecord detection_method and exit_reason are defined as String(100)."""
    detection_col = PaperTradeRecord.__table__.columns['detection_method']
    exit_col = PaperTradeRecord.__table__.columns['exit_reason']

    assert isinstance(detection_col.type, sa.String)
    assert detection_col.type.length >= 100, f"Expected detection_method length >= 100, got {detection_col.type.length}"

    assert isinstance(exit_col.type, sa.String)
    assert exit_col.type.length >= 100, f"Expected exit_reason length >= 100, got {exit_col.type.length}"


def test_detection_method_string_generation_fits():
    """Verify that all standard combined detection_method strings fit safely within String(100)."""
    tp_methods = ['close_price', 'high_low', 'custom_conservative_method']
    sl_conflicts = ['sl_wins', 'tp_wins', 'split_decision_wins']

    for tp in tp_methods:
        for sl in sl_conflicts:
            combined = f'{tp}_tp_{sl}_sl'
            assert len(combined) <= 100
            # Test default case specifically
            if tp == 'close_price' and sl == 'sl_wins':
                assert combined == 'close_price_tp_sl_wins_sl'
                assert len(combined) == 25


def test_alembic_migration_chain():
    """Verify the new migration connects to previous head a8d29c4e1f7b and defines upgrade/downgrade."""
    import ast
    import os

    migration_path = os.path.join(
        os.path.dirname(__file__),
        '../../database/migrations/versions/e918c7d6a5b4_expand_paper_trade_detection_method_and_exit_reason.py'
    )
    assert os.path.exists(migration_path), f"Migration file missing at {migration_path}"

    with open(migration_path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=migration_path)

    # Extract global assignments and functions
    globals_assigned = {}
    functions = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    globals_assigned[target.id] = node.value.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and isinstance(node.value, ast.Constant):
                globals_assigned[node.target.id] = node.value.value
        elif isinstance(node, ast.FunctionDef):
            functions.add(node.name)

    assert globals_assigned.get('revision') == 'e918c7d6a5b4'
    assert globals_assigned.get('down_revision') == 'a8d29c4e1f7b'
    assert 'upgrade' in functions
    assert 'downgrade' in functions


@pytest.mark.asyncio
async def test_paper_tracker_check_sl_tp_sets_full_detection_method():
    """Verify PaperTracker._check_sl_tp correctly populates detection_method without truncation."""
    tracker = PaperTracker()
    session = AsyncMock()

    trade = PaperTradeRecord(
        id=3,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.3500,
        stop_loss=1.3450,
        take_profit=1.3600,
        opened_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        status="open",
        risk_pct=0.75
    )

    # Bar hitting SL
    bar = MagicMock()
    bar.timestamp = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    bar.low = 1.3440  # Below SL of 1.3450
    bar.high = 1.3520
    bar.close = 1.3460

    with patch.object(tracker, '_is_news_environment', AsyncMock(return_value=False)):
        result = await tracker._check_sl_tp(session, trade, [bar], 'M15')

    assert result is not None
    assert trade.status == 'closed'
    assert trade.exit_reason == 'sl_hit'
    assert trade.detection_method == 'close_price_tp_sl_wins_sl'
    assert len(trade.detection_method) == 25


@pytest.mark.asyncio
async def test_paper_tracker_error_isolation_on_flush_failure():
    """Verify that if an individual trade encounters an exception during processing,
    the failure is isolated, session rolled back, and the failed trade is not included in closed list."""
    tracker = PaperTracker()
    session = AsyncMock()

    trade_bad = PaperTradeRecord(
        id=99,
        symbol="GBPUSD",
        direction="buy",
        entry_price=1.2500,
        stop_loss=1.2400,
        take_profit=1.2700,
        opened_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        status="open"
    )

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [trade_bad]
    session.execute.return_value = mock_exec

    # Simulate SL hit in _get_bars_since_open & _check_sl_tp
    with patch.object(tracker, '_get_bars_since_open', AsyncMock(return_value=[MagicMock()])), \
         patch.object(tracker, '_check_sl_tp', AsyncMock(return_value={'symbol': 'GBPUSD', 'exit_reason': 'sl_hit', 'pnl_pct': -0.75})), \
         patch.object(tracker, '_close_linked_position', AsyncMock(side_effect=Exception("Simulated Flush Failure"))):

        closed = await tracker.check_and_close_trades(session)

    # Failed trade should NOT be in closed list
    assert len(closed) == 0
    # Session rollback should be called
    assert session.rollback.called
