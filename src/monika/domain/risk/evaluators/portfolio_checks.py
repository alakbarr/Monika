# ==============================================================================
# File: domain/risk/evaluators/portfolio_checks.py
# ==============================================================================

"""
Drawdown, portfolio heat, correlation exposure, and copula tail risk checks for RiskGate.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone, UTC
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.domain.market.currency_utils import get_symbol_currencies
from monika.domain.risk.evaluators.base import _RiskGateMixinBase, get_trading_day_start, resolve_model
from monika.domain.risk.position_sizing import PositionSizer, SizingResult

if TYPE_CHECKING:
    from monika.infrastructure.database.models import (
        AssetAnalysis,
        PaperTradeRecord,
        Position,
        PriceOHLCV,
        RiskState,
        TradeOutcome,
    )
else:
    Position = resolve_model("Position")
    RiskState = resolve_model("RiskState")
    TradeOutcome = resolve_model("TradeOutcome")
    PaperTradeRecord = resolve_model("PaperTradeRecord")
    AssetAnalysis = resolve_model("AssetAnalysis")
    PriceOHLCV = resolve_model("PriceOHLCV")

logger = logging.getLogger("TradingAgent.RiskGate")


class RiskPortfolioChecksMixin(_RiskGateMixinBase):
    """Drawdown limits, portfolio correlation, and portfolio heat validation mixin."""

    async def _check_strategy_factor_exposure(
        self,
        session: AsyncSession,
        analysis: AssetAnalysis,
        simulated_positions: list | None = None,
    ) -> tuple[bool, str]:
        """Limits portfolio concentration across strategy factor families (trend, mean_reversion, stat_arb, breakout)."""
        strat_id = getattr(analysis, "source_strategy_id", None)
        factor_family = getattr(analysis, "strategy_factor_family", None)
        if isinstance(analysis, dict):
            strat_id = strat_id or analysis.get("source_strategy_id") or analysis.get("strategy_id")
            factor_family = factor_family or analysis.get("strategy_factor_family") or analysis.get("factor_family")

        if not strat_id and not factor_family:
            return True, "factor_exposure_na"

        from monika.application.analysis.strategies.registry import StrategyRegistry

        if not factor_family:
            strat_cls = StrategyRegistry.get_strategy(strat_id) if strat_id else None
            factor_family = getattr(strat_cls, "factor_family", "trend") if strat_cls else "trend"

        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        limit_val = risk_cfg.get("max_positions_per_factor_family", 3)
        if isinstance(limit_val, dict):
            max_family_limit = int(limit_val.get(factor_family, limit_val.get("default", 3)))
        else:
            max_family_limit = int(limit_val)

        current_count = 0
        if simulated_positions is not None:
            for p in simulated_positions:
                p_fam = None
                p_strat = getattr(p, "source_strategy_id", None)
                if p_strat:
                    p_cls = StrategyRegistry.get_strategy(str(p_strat))
                    p_fam = getattr(p_cls, "factor_family", None) if p_cls else None
                elif getattr(p, "analysis_id", None):
                    p_ana = await session.get(AssetAnalysis, p.analysis_id)
                    ana_strat = getattr(p_ana, "source_strategy_id", None) if p_ana else None
                    if p_ana and ana_strat:
                        p_cls = StrategyRegistry.get_strategy(str(ana_strat))
                        p_fam = getattr(p_cls, "factor_family", None) if p_cls else None
                if p_fam == factor_family:
                    current_count += 1
        else:
            open_positions = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
            for pos in open_positions:
                pos_fam = None
                pos_strat = getattr(pos, "source_strategy_id", None)
                if pos_strat:
                    pos_cls = StrategyRegistry.get_strategy(str(pos_strat))
                    pos_fam = getattr(pos_cls, "factor_family", None) if pos_cls else None
                elif getattr(pos, "analysis_id", None):
                    pos_ana = await session.get(AssetAnalysis, pos.analysis_id)
                    ana_strat = getattr(pos_ana, "source_strategy_id", None) if pos_ana else None
                    if pos_ana and ana_strat:
                        pos_cls = StrategyRegistry.get_strategy(str(ana_strat))
                        pos_fam = getattr(pos_cls, "factor_family", None) if pos_cls else None
                if pos_fam == factor_family:
                    current_count += 1

        if current_count >= max_family_limit:
            return (
                False,
                f"strategy_factor_exposure_limit: {factor_family} capacity reached ({current_count}/{max_family_limit})",
            )

        return True, f"factor_exposure_ok ({factor_family}: {current_count}/{max_family_limit})"

    async def _check_weekly_drawdown(
        self,
        session: AsyncSession,
        equity: float | None = None,
        is_backtest: bool = False,
        is_paper: bool | None = None,
    ) -> tuple[bool, str]:
        if is_backtest:
            return True, "weekly_drawdown_backtest_ok"
        from datetime import timedelta

        now = clock.now()
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

        # Paper trades closed this week
        paper_trades = (
            (
                await session.execute(
                    select(PaperTradeRecord).where(
                        PaperTradeRecord.closed_at >= week_start,
                        PaperTradeRecord.closed_at <= now,
                        PaperTradeRecord.status == "closed",
                    )
                )
            )
            .scalars()
            .all()
        )
        paper_weekly_pnl = sum(t.pnl_pct or 0 for t in paper_trades)

        # Live trades closed this week
        live_outcomes = (
            (
                await session.execute(
                    select(TradeOutcome).where(TradeOutcome.closed_at >= week_start, TradeOutcome.closed_at <= now)
                )
            )
            .scalars()
            .all()
        )
        live_weekly_pnl = 0.0
        eff_equity = (
            equity
            if (equity is not None and equity > 0)
            else float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        )
        if live_outcomes and eff_equity > 0:
            total_live_profit = sum(o.pnl_usd or 0.0 for o in live_outcomes)
            live_weekly_pnl = (total_live_profit / eff_equity) * 100.0

        # Decouple: Live trading is governed by live PnL; paper trading by paper PnL.
        is_paper_mode = (
            is_paper if is_paper is not None else self.settings.get("paper_trading", {}).get("enabled", True)
        )
        if not is_paper_mode and live_outcomes:
            weekly_pnl = live_weekly_pnl
        elif live_outcomes and not is_paper_mode:
            weekly_pnl = live_weekly_pnl
        else:
            weekly_pnl = paper_weekly_pnl
        max_weekly = self.settings.get("trading", {}).get("risk", {}).get("max_weekly_drawdown_percent", 6.0)
        if weekly_pnl <= -max_weekly:
            return False, f"Weekly loss {weekly_pnl:.2f}% >= limit {max_weekly}%"
        return True, f"weekly_pnl={weekly_pnl:.2f}%/{-max_weekly}%"

    async def _check_daily_drawdown(
        self,
        session: AsyncSession,
        equity: float | None = None,
        simulated_daily_pnl: float | None = None,
        is_backtest: bool = False,
    ) -> tuple[bool, str]:
        """Periksa apakah drawdown hari ini (realized + unrealized loss) belum melampaui batas."""
        if is_backtest:
            if simulated_daily_pnl is not None and equity and equity > 0:
                drawdown_pct = (abs(simulated_daily_pnl) / equity * 100) if simulated_daily_pnl < 0 else 0.0
                if simulated_daily_pnl < 0 and drawdown_pct >= self.max_daily_drawdown_pct:
                    return (
                        False,
                        f"Simulated daily drawdown {drawdown_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%",
                    )
                return True, f"simulated_drawdown={drawdown_pct:.2f}%"
            return True, "backtest_mode_dd_ok"

        today_start = get_trading_day_start(self.settings)
        state = (
            await session.execute(
                select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
            )
        ).scalar_one_or_none()

        realized_pnl = 0.0
        if state is None:
            # First trade of the day: initialize baseline state record from account equity
            try:
                state = RiskState(
                    date=clock.now(),
                    daily_pnl=0.0,
                    current_drawdown=0.0,
                    trading_paused=False,
                )
                session.add(state)
                await session.flush()
            except Exception as init_err:
                logger.debug(f"Failed to initialize baseline RiskState: {init_err}")
        else:
            realized_pnl = state.daily_pnl

        # Calculate unrealized PnL from MT5
        unrealized_pnl = 0.0
        is_dry = getattr(self, "dry_run", getattr(self, "_dry_run", False))
        if self._mt5 and not is_dry:
            try:
                positions = await self._mt5.get_open_positions()
                unrealized_pnl = sum(p.get("profit", 0.0) for p in positions)
            except Exception as e:
                logger.debug(f"Failed to fetch MT5 positions for unrealized PnL: {e}")
        elif is_dry:
            try:
                open_papers = (
                    (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open")))
                    .scalars()
                    .all()
                )
                unrealized_pnl = 0.0
                for paper in open_papers:
                    last_bar = (
                        await session.execute(
                            select(PriceOHLCV.close)
                            .where(PriceOHLCV.symbol == paper.symbol)
                            .order_by(PriceOHLCV.timestamp.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if last_bar and paper.entry_price and paper.stop_loss:
                        sl_dist = abs(paper.entry_price - paper.stop_loss)
                        if sl_dist > 0:
                            diff = (
                                (last_bar - paper.entry_price)
                                if paper.direction == "buy"
                                else (paper.entry_price - last_bar)
                            )
                            risk_pct = paper.risk_pct or 0.75
                            trade_pnl_pct = risk_pct * (diff / sl_dist)
                            unrealized_pnl += (equity or 10000.0) * (trade_pnl_pct / 100.0)
            except Exception as e:
                logger.debug(f"Failed to calc paper unrealized PnL: {e}")

        # We track Daily Drawdown as the net daily PnL (realized + unrealized).
        # A true daily loss limit is based on the starting equity of the day.
        eff_equity = (
            equity
            if (equity is not None and equity > 0)
            else float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        )
        total_daily_pnl = (state.daily_pnl if state else realized_pnl) + unrealized_pnl
        drawdown_pct = (abs(total_daily_pnl) / eff_equity * 100) if (eff_equity > 0 and total_daily_pnl < 0) else 0.0

        # We also enforce that unrealized loss on its own cannot exceed the limit.
        if unrealized_pnl < 0:
            unrealized_dd_pct = (abs(unrealized_pnl) / eff_equity * 100) if eff_equity > 0 else 0.0
            if unrealized_dd_pct >= self.max_daily_drawdown_pct:
                return False, (
                    f"Unrealized drawdown {unrealized_dd_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%. "
                    f"Unrealized: ${unrealized_pnl:.2f}"
                )

        # Also check if daily PnL is already at max loss
        if total_daily_pnl < 0:
            if drawdown_pct >= self.max_daily_drawdown_pct:
                return False, (
                    f"Daily PnL loss {drawdown_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%. "
                    f"Total Daily PnL: ${total_daily_pnl:.2f}"
                )

        return True, f"drawdown={drawdown_pct:.2f}% (limit={self.max_daily_drawdown_pct}%)"

    async def check_correlation_exposure(
        self,
        session: AsyncSession,
        symbol: str,
        direction: str,
        simulated_positions: list | None = None,
        as_of: datetime | None = None,
        open_positions: list | None = None,
        volume: float | None = None,
    ) -> tuple[bool, str]:
        """Pastikan trade ini tidak melewati batas korelasi paparan mata uang / heat limit menggunakan DynamicCorrelationMatrix."""
        if open_positions is None:
            if simulated_positions is not None:
                open_positions = simulated_positions
            else:
                open_positions = list(
                    (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                )

        if not open_positions:
            return True, "no existing positions"

        # Evaluate portfolio heat using DynamicCorrelationMatrix if open positions present
        pos_list = []
        for pos in open_positions:
            p_sym = getattr(pos, "symbol", None) or (pos.get("symbol") if isinstance(pos, dict) else None)
            p_vol = (
                getattr(pos, "volume", None)
                or getattr(pos, "executed_lots", None)
                or (pos.get("volume", 0.1) if isinstance(pos, dict) else 0.1)
                or 0.1
            )
            p_dir = getattr(pos, "direction", None) or (pos.get("direction") if isinstance(pos, dict) else "buy")
            if p_sym:
                pos_list.append({"symbol": str(p_sym), "volume": float(p_vol), "direction": str(p_dir)})

        cand_vol = float(volume) if volume is not None and float(volume) > 0 else 0.1
        if pos_list and hasattr(self, "dynamic_correlation_matrix"):
            try:
                candidate_pos = {"symbol": symbol, "direction": direction, "volume": cand_vol}
                all_positions = pos_list + [candidate_pos]
                symbols = list(set([p["symbol"] for p in all_positions]))
                corr_matrix = await self.dynamic_correlation_matrix.get_matrix(session, symbols, as_of=as_of)
                if corr_matrix:
                    heat = self.dynamic_correlation_matrix.calculate_portfolio_heat(all_positions, corr_matrix)
                    if heat.get("portfolio_heat", 0.0) > float(self.correlation_limit):
                        return False, (
                            f"Correlated exposure limit exceeded: calculated portfolio heat {heat['portfolio_heat']:.2f} "
                            f"> limit {self.correlation_limit}"
                        )
            except Exception as exc:
                logger.debug(f"DynamicCorrelationMatrix evaluation fallback: {exc}")

        max_lot = self.settings.get("trading", {}).get("risk", {}).get("max_lot_per_symbol", 1.0)
        correlated_exposure = max(cand_vol / max(max_lot, 0.01), 0.1)  # Normalized base exposure for the new trade

        for pos in open_positions:
            pos_sym = getattr(pos, "symbol", None) or (pos.get("symbol") if isinstance(pos, dict) else None)
            pos_vol = (
                getattr(pos, "volume", None)
                or getattr(pos, "executed_lots", None)
                or (pos.get("volume", 0.1) if isinstance(pos, dict) else 0.1)
                or 0.1
            )
            pos_dir = getattr(pos, "direction", None) or (pos.get("direction") if isinstance(pos, dict) else "buy")

            if not pos_sym:
                continue

            # Dynamic correlation calculation and std_dev
            corr, std_dev = await self._get_dynamic_correlation(session, symbol, pos_sym, as_of=as_of)

            if corr != 0.0 and abs(corr) > 0.7:
                # Volatility-adjusted exposure: Aset dengan volatilitas rendah memiliki penalty lebih kecil
                volatility_multiplier = max(std_dev * 100, 0.1)

                normalized_exposure = (pos_vol / max(max_lot, 0.01)) * volatility_multiplier

                same_dir = direction == pos_dir
                actual_direction_factor = 1 if (corr > 0 and same_dir) or (corr < 0 and not same_dir) else -0.5
                correlated_exposure += abs(corr) * normalized_exposure * max(0, actual_direction_factor)

        if correlated_exposure > self.correlation_limit:
            return False, (
                f"Correlated exposure limit exceeded: calculated exposure {correlated_exposure:.2f} "
                f"> limit {self.correlation_limit}"
            )

        return True, f"correlation_ok (exposure={correlated_exposure:.2f}/{self.correlation_limit})"

    async def _check_correlation(
        self,
        session: AsyncSession,
        symbol: str,
        direction: str,
        simulated_positions: list | None = None,
        as_of: datetime | None = None,
        volume: float | None = None,
    ) -> tuple[bool, str]:
        """Pastikan trade ini tidak melewati batas korelasi paparan mata uang."""
        return await self.check_correlation_exposure(
            session=session,
            symbol=symbol,
            direction=direction,
            simulated_positions=simulated_positions,
            as_of=as_of,
            volume=volume,
        )

    async def _get_dynamic_correlation(
        self, session: AsyncSession, symbol1: str, symbol2: str, as_of: datetime | None = None
    ) -> tuple[float, float]:
        """Hitung korelasi harian secara dinamis berdasar PriceOHLCV, return (corr, std_dev2)."""
        import pandas as pd
        from sqlalchemy import select

        from monika.domain.market.dynamic_correlation import get_rolling_correlation

        sim_time = as_of or clock.now()
        corr, source = await get_rolling_correlation(session, symbol1, symbol2, as_of=sim_time)
        fallback_std = 0.01

        try:
            s2_stmt = select(PriceOHLCV.timestamp, PriceOHLCV.close).where(
                PriceOHLCV.symbol == symbol2, PriceOHLCV.timeframe == "D1"
            )
            if sim_time is not None:
                s2_stmt = s2_stmt.where(PriceOHLCV.timestamp <= sim_time)

            s2_rows = (await session.execute(s2_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(60))).all()

            if len(s2_rows) >= 30:
                df2 = pd.DataFrame(s2_rows, columns=["timestamp", "close2"]).set_index("timestamp").sort_index()
                try:
                    raw_val: Any = df2["close2"].pct_change().std()
                    std2_raw = float(raw_val)
                    std2 = fallback_std if math.isnan(std2_raw) else std2_raw
                except TypeError, ValueError:
                    std2 = fallback_std
            else:
                std2 = fallback_std
        except Exception:
            std2 = fallback_std

        return float(corr), float(std2)

    async def _check_total_portfolio_heat(
        self,
        session: AsyncSession,
        proposed_sizing: SizingResult,
        equity: float | None = None,
        simulated_positions: list | None = None,
    ) -> tuple[bool, str]:
        heat_cfg = self.settings.get("trading", {}).get("risk", {})
        max_heat_pct = float(heat_cfg.get("max_portfolio_heat_pct", 4.0))
        eff_equity = (
            equity
            if (equity is not None and equity > 0)
            else float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        )

        if simulated_positions is not None:
            open_positions = simulated_positions
        else:
            open_positions = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()

        current_heat_usd = 0.0
        position_details = []

        for pos in open_positions:
            pos_sym = getattr(pos, "symbol", None) or (pos.get("symbol") if isinstance(pos, dict) else None)
            pos_entry = getattr(pos, "entry_price", None) or (pos.get("entry_price") if isinstance(pos, dict) else None)
            pos_sl = (
                getattr(pos, "sl", None)
                or getattr(pos, "stop_loss", None)
                or (pos.get("sl") or pos.get("stop_loss") if isinstance(pos, dict) else None)
            )
            pos_vol = (
                getattr(pos, "volume", None)
                or getattr(pos, "executed_lots", None)
                or (pos.get("volume") or pos.get("executed_lots") if isinstance(pos, dict) else None)
            )
            pos_dir = getattr(pos, "direction", None) or (pos.get("direction") if isinstance(pos, dict) else "buy")

            if not pos_entry or not pos_vol or not pos_sym:
                continue

            pos_sym_str = str(pos_sym)

            # Hitung risiko aktual posisi terbuka
            if pos_sl and pos_sl > 0:
                d_entry = Decimal(str(pos_entry))
                d_sl = Decimal(str(pos_sl))
                d_sl_distance = abs(d_entry - d_sl)
                sl_distance = float(d_sl_distance)

                # Check breakeven (SL past/at entry)
                if pos_dir == "buy" and pos_sl >= pos_entry:
                    heat_this_position = 0.0
                    position_details.append(f"{pos_sym_str}: $0 (breakeven)")
                elif pos_dir == "sell" and pos_sl <= pos_entry:
                    heat_this_position = 0.0
                    position_details.append(f"{pos_sym_str}: $0 (breakeven)")
                else:
                    from monika.domain.risk.position_sizing import PositionSizer

                    sizer = PositionSizer(self.settings, mt5_client=self._mt5)
                    try:
                        spec = await sizer._get_instrument_spec_dynamic(session, pos_sym_str)
                    except Exception:
                        spec = sizer._get_instrument_spec(pos_sym_str)

                    if spec and spec.pip_size > 0 and spec.pip_value_per_lot > 0:
                        d_pip_size = Decimal(str(spec.pip_size))
                        d_pip_val = Decimal(str(spec.pip_value_per_lot))
                        d_pos_vol = Decimal(str(pos_vol))
                        d_sl_distance_pips = d_sl_distance / d_pip_size
                        # Actual risk = SL_pips * pip_value * lots using Decimal
                        d_heat = d_sl_distance_pips * d_pip_val * d_pos_vol
                        heat_this_position = float(d_heat)
                        # Cap at 3x default risk (sanity check)
                        max_reasonable = eff_equity * (float(heat_cfg.get("risk_percent_per_trade", 1.5)) / 100.0) * 3
                        heat_this_position = min(heat_this_position, max_reasonable)
                        position_details.append(f"{pos_sym}: ~${heat_this_position:.2f} (actual SL risk)")
                    else:
                        # Fallback to default estimate
                        heat_this_position = eff_equity * (float(heat_cfg.get("risk_percent_per_trade", 1.5)) / 100.0)
                        position_details.append(f"{pos_sym}: ~${heat_this_position:.2f} (estimated)")
            else:
                if simulated_positions is None:
                    fallback_pct = float(heat_cfg.get("risk_percent_per_trade", 2.0))
                    heat_this_position = eff_equity * (fallback_pct / 100.0)
                    position_details.append(
                        f"{pos_sym}: ~${heat_this_position:.2f} (WARN: no SL, estimated at {fallback_pct}%)"
                    )
                    logger.warning(
                        f"Position {pos_sym} has no explicit SL; heat estimated at {fallback_pct}% of equity."
                    )
                else:
                    heat_this_position = eff_equity * (float(heat_cfg.get("risk_percent_per_trade", 1.5)) / 100.0)

            current_heat_usd += heat_this_position

        proposed_heat_usd = proposed_sizing.risk_amount_usd
        total_heat_usd = current_heat_usd + proposed_heat_usd
        total_heat_pct = (total_heat_usd / eff_equity * 100) if eff_equity > 0 else 0.0

        if total_heat_pct > max_heat_pct:
            return False, (
                f"Portfolio heat would reach {total_heat_pct:.1f}% "
                f"(limit={max_heat_pct}%). "
                f"Current positions actual risk: {', '.join(position_details)}. "
                f"Proposed: ${proposed_heat_usd:.2f} ({proposed_sizing.risk_percent:.1f}%)."
            )

        return True, f"portfolio_heat={total_heat_pct:.1f}%/{max_heat_pct}%"

    async def _check_copula_tail_risk(
        self,
        session: AsyncSession,
        symbol: str,
        simulated_positions: list | None = None,
        as_of: datetime | None = None,
        is_backtest: bool = False,
    ) -> tuple[bool, str]:
        """
        Subsystem 5: Copula Tail Risk Haircut & Gate.
        Inspects Clayton (lower tail) dependency against existing open positions.
        If tail risk lambda > 0.40, enforces caution or rejection to protect against market crash contagion.
        """
        try:
            if simulated_positions is not None:
                active_symbols = list(
                    {p.get("symbol") for p in simulated_positions if isinstance(p, dict) and p.get("symbol") != symbol}
                )
            else:
                stmt = (
                    select(Position.symbol).where(Position.symbol != symbol).where(Position.status == "open").distinct()
                )
                active_symbols = (await session.execute(stmt)).scalars().all()

            if not active_symbols:
                return True, "No concurrent portfolio positions for tail dependency"

            import numpy as np

            from monika.application.analysis.calculators.copula_tail_risk import fit_clayton_copula

            now = as_of or clock.now()
            cutoff = now - timedelta(days=60)

            c_stmt = (
                select(PriceOHLCV.close)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == "H1")
                .where(PriceOHLCV.timestamp >= cutoff)
                .order_by(PriceOHLCV.timestamp.asc())
            )
            c_closes = np.array((await session.execute(c_stmt)).scalars().all(), dtype=float)
            if len(c_closes) < 30:
                return True, "Insufficient candle history for copula tail risk"

            c_returns = np.diff(c_closes) / c_closes[:-1]

            for other_sym in active_symbols[:3]:
                o_stmt = (
                    select(PriceOHLCV.close)
                    .where(PriceOHLCV.symbol == other_sym)
                    .where(PriceOHLCV.timeframe == "H1")
                    .where(PriceOHLCV.timestamp >= cutoff)
                    .order_by(PriceOHLCV.timestamp.asc())
                )
                o_closes = np.array((await session.execute(o_stmt)).scalars().all(), dtype=float)
                if len(o_closes) < 30:
                    continue
                o_returns = np.diff(o_closes) / o_closes[:-1]

                min_len = min(len(c_returns), len(o_returns))
                fit_res = fit_clayton_copula(c_returns[-min_len:], o_returns[-min_len:])
                lower_tail = fit_res.get("lower_tail_dependence", 0.0)

                if lower_tail > 0.40:
                    return (
                        False,
                        f"Extreme crash contagion tail risk: Clayton lambda={lower_tail:.2f} > 0.40 with active position in {other_sym}",
                    )

        except Exception as e:
            logger.warning(f"[{symbol}] Copula tail risk check failed: {e}")
            return False, f"copula_tail_risk_check_failed: {e}"

        return True, "Copula tail risk within institutional limits"


__all__ = ["RiskPortfolioChecksMixin"]
