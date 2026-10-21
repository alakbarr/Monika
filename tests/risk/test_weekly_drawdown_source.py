"""Phase 0: drawdown limits must read the source that matches the trading mode.

Paper mode reads the verified paper ledger; live mode reads TradeOutcome in
USD. Unverifiable paper rows fail closed instead of being counted as zero.
"""

from datetime import UTC, datetime

import pytest

from monika.domain.risk.evaluators.portfolio_checks import RiskPortfolioChecksMixin
from monika.infrastructure.database.models import PaperTradeRecord, PriceOHLCV, TradeOutcome


class _Gate(RiskPortfolioChecksMixin):
    def __init__(self) -> None:
        self.settings = {
            "trading": {"risk": {"max_weekly_drawdown_percent": 6.0}},
            "paper_trading": {"enabled": True, "initial_balance": 10000.0},
        }
        self.max_daily_drawdown_pct = 3.0
        self._mt5 = None


def _closed_paper(
    symbol: str,
    pnl_pct: float,
    accounting_status: str = "ok",
    exit_reason: str = "sl_hit",
) -> PaperTradeRecord:
    return PaperTradeRecord(
        symbol=symbol,
        direction="buy",
        entry_price=1.10000,
        stop_loss=1.09000,
        take_profit=1.12000,
        initial_stop_loss=1.09000 if accounting_status == "ok" else None,
        initial_risk_pct=1.0,
        risk_pct=1.0,
        pnl_pct=pnl_pct,
        exit_price=1.09000,
        exit_reason=exit_reason,
        opened_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
        status="closed",
        accounting_status=accounting_status,
    )


@pytest.mark.asyncio
async def test_paper_weekly_drawdown_uses_verified_paper_ledger(db_session):
    db_session.add(_closed_paper("EURUSD", -2.0))
    await db_session.commit()

    gate = _Gate()
    ok, message = await gate._check_weekly_drawdown(db_session, equity=10000.0, is_paper=True)

    assert ok is True
    assert "weekly_pnl=-2.00%" in message


@pytest.mark.asyncio
async def test_paper_weekly_drawdown_fails_closed_on_unverified_row(db_session):
    db_session.add(_closed_paper("EURUSD", -1.0, accounting_status="invalid_initial_stop"))
    await db_session.commit()

    ok, message = await _Gate()._check_weekly_drawdown(db_session, equity=10000.0, is_paper=True)

    assert ok is False
    assert "unverifiable" in message
    assert "EURUSD" in message


@pytest.mark.asyncio
async def test_not_filled_limit_does_not_block_weekly_limit(db_session):
    db_session.add(_closed_paper("EURUSD", 0.0, accounting_status="not_filled", exit_reason="expired_limit"))
    await db_session.commit()

    ok, message = await _Gate()._check_weekly_drawdown(db_session, equity=10000.0, is_paper=True)

    assert ok is True
    assert "weekly_pnl=0.00%" in message


@pytest.mark.asyncio
async def test_live_weekly_drawdown_uses_usd_outcomes_not_paper_rows(db_session):
    # A large paper loss must be invisible to live mode.
    db_session.add(_closed_paper("EURUSD", -9.0))
    db_session.add(
        TradeOutcome(
            symbol="XAUUSD",
            direction="buy",
            pnl_usd=-500.0,
            closed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    ok, message = await _Gate()._check_weekly_drawdown(db_session, equity=10000.0, is_paper=False)

    assert ok is True
    assert "weekly_pnl=-5.00%" in message


@pytest.mark.asyncio
async def test_live_weekly_drawdown_breaches_from_usd_outcomes(db_session):
    db_session.add(
        TradeOutcome(
            symbol="XAUUSD",
            direction="buy",
            pnl_usd=-700.0,
            closed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    ok, message = await _Gate()._check_weekly_drawdown(db_session, equity=10000.0, is_paper=False)

    assert ok is False
    assert "Weekly loss" in message


@pytest.mark.asyncio
async def test_paper_daily_drawdown_counts_open_unrealized_from_entry_anchor(db_session):
    db_session.add(
        PaperTradeRecord(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.10000,
            stop_loss=1.09000,
            take_profit=1.12000,
            initial_stop_loss=1.09000,
            initial_risk_pct=1.0,
            risk_pct=1.0,
            opened_at=datetime.now(UTC),
            status="open",
            accounting_status="ok",
        )
    )
    db_session.add(
        PriceOHLCV(
            symbol="EURUSD",
            timeframe="M15",
            timestamp=datetime.now(UTC),
            open=1.09500,
            high=1.09600,
            low=1.09400,
            close=1.09500,
            volume=1000.0,
        )
    )
    await db_session.commit()

    ok, message = await _Gate()._check_daily_drawdown(db_session, equity=10000.0, is_paper=True)

    assert ok is True
    # -0.5R on 1% risk = -0.5% = -$50 -> 0.50% drawdown.
    assert "drawdown=0.50%" in message


@pytest.mark.asyncio
async def test_paper_daily_drawdown_fails_closed_without_open_price(db_session):
    db_session.add(
        PaperTradeRecord(
            symbol="EURUSD",
            direction="buy",
            entry_price=1.10000,
            stop_loss=1.09000,
            take_profit=1.12000,
            initial_stop_loss=1.09000,
            initial_risk_pct=1.0,
            risk_pct=1.0,
            opened_at=datetime.now(UTC),
            status="open",
            accounting_status="ok",
        )
    )
    await db_session.commit()

    ok, message = await _Gate()._check_daily_drawdown(db_session, equity=10000.0, is_paper=True)

    assert ok is False
    assert "no price" in message
