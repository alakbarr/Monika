"""Phase 0: an open paper trade is an exposure even before Position sync.

The 16 Oct 2026 duplicate BTCUSD entries happened because the duplicate check
only looked at Position rows, which are created after execution.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from monika.domain.risk.evaluators.execution_checks import RiskExecutionChecksMixin
from monika.infrastructure.database.models import PaperTradeRecord


class _Gate(RiskExecutionChecksMixin):
    pass


def _open_trade(symbol: str = "BTCUSD") -> PaperTradeRecord:
    return PaperTradeRecord(
        symbol=symbol,
        direction="buy",
        entry_price=82000.0,
        stop_loss=81000.0,
        take_profit=84000.0,
        initial_stop_loss=81000.0,
        initial_risk_pct=1.1,
        risk_pct=1.1,
        opened_at=datetime.now(UTC),
        status="open",
        accounting_status="ok",
    )


@pytest.mark.asyncio
async def test_open_paper_trade_blocks_a_second_entry(db_session):
    db_session.add(_open_trade("BTCUSD"))
    await db_session.commit()

    ok, reason = await _Gate()._check_no_duplicate(db_session, "BTCUSD", is_paper=True)

    assert ok is False
    assert "open paper trade" in reason


@pytest.mark.asyncio
async def test_other_symbol_is_not_blocked(db_session):
    db_session.add(_open_trade("BTCUSD"))
    await db_session.commit()

    ok, _ = await _Gate()._check_no_duplicate(db_session, "EURUSD", is_paper=True)

    assert ok is True


@pytest.mark.asyncio
async def test_pair_group_tranche_is_allowed(db_session):
    db_session.add(_open_trade("BTCUSD"))
    await db_session.commit()

    ok, _ = await _Gate()._check_no_duplicate(db_session, "BTCUSD", pair_group_id="btc-tranche", is_paper=True)

    assert ok is True


@pytest.mark.asyncio
async def test_closed_paper_trade_does_not_block(db_session):
    db_session.add(_open_trade("BTCUSD"))
    await db_session.commit()

    closed = (
        await db_session.execute(select(PaperTradeRecord).where(PaperTradeRecord.symbol == "BTCUSD"))
    ).scalar_one()
    closed.status = "closed"
    await db_session.commit()

    ok, _ = await _Gate()._check_no_duplicate(db_session, "BTCUSD", is_paper=True)

    assert ok is True
