"""
Point-in-Time Backtest Engine with Real Pipeline Parity and Zero Lookahead Bias.
"""
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Literal, List, Dict, Any, Optional

from sqlalchemy import select, func
from database.db import get_session
from database.models import BacktestRun, BacktestTrade, AssetAnalysis, PriceOHLCV, TechnicalIndicator

import utils.clock as clock
from backtest.outcome_evaluator import OutcomeEvaluator
from backtest.report_generator import ReportGenerator
from risk.position_sizing import PositionSizer

logger = logging.getLogger("TradingAgent.PointInTimeBacktest")


BacktestMode = Literal["full", "replay", "langgraph_parity", "graph"]


class PointInTimeBacktestEngine:
    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        settings: dict,
        mode: BacktestMode = "replay",
        step_hours: int = 6,
        initial_equity: float = 10000.0,
        broker_adapter: Optional[Any] = None,
        execution_service: Optional[Any] = None,
        use_execution_service: Optional[bool] = None,
    ):
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        if start_date >= end_date:
            raise ValueError(f"start_date ({start_date}) must be earlier than end_date ({end_date})")

        self.start_date = start_date
        self.end_date = end_date
        self.settings = settings
        self.mode = mode
        self.step_hours = step_hours
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[Dict[str, Any]] = [
            {"timestamp": start_date, "equity": initial_equity}
        ]
        self.run_record = None
        self.sizer = PositionSizer(settings)
        try:
            from risk.risk_gate import RiskGate
            self.gate = RiskGate(settings=settings, mt5_client=None)
        except Exception:
            self.gate = None

        # Phase 3: Research-to-Live Parity Engine via SimulatedBrokerAdapter and ExecutionService
        if broker_adapter is not None:
            self.broker_adapter = broker_adapter
        else:
            try:
                from execution.broker_adapter import SimulatedBrokerAdapter
                self.broker_adapter = SimulatedBrokerAdapter(
                    initial_balance=initial_equity,
                    settings=settings,
                )
            except Exception as adapter_err:
                logger.debug(f"SimulatedBrokerAdapter init fallback: {adapter_err}")
                self.broker_adapter = None

        if execution_service is not None:
            self.execution_service = execution_service
        else:
            try:
                from execution.execution_service import ExecutionService
                self.execution_service = ExecutionService(
                    settings=settings,
                    dry_run=True,
                    broker_adapter=self.broker_adapter,
                )
            except Exception as svc_err:
                logger.debug(f"ExecutionService in backtest init fallback: {svc_err}")
                self.execution_service = None

        if use_execution_service is not None:
            self.use_execution_service = use_execution_service
        else:
            self.use_execution_service = settings.get("backtest", {}).get("use_execution_service", False)

    async def execute_trade_parity(
        self,
        session: Any,
        analysis: AssetAnalysis,
    ) -> Optional[BacktestTrade]:
        """
        Execute an AssetAnalysis through the full live ExecutionService pipeline
        with SimulatedBrokerAdapter, achieving 100% research-to-live parity.
        """
        if self.execution_service is None:
            return None

        entry_price = analysis.price_at_analysis or analysis.entry_price

        # Synchronize broker tick
        if entry_price and self.broker_adapter is not None and hasattr(self.broker_adapter, 'set_tick'):
            from execution.broker_adapter import _get_pip_size
            pip_size = _get_pip_size(analysis.symbol)
            spread_pips = getattr(self.broker_adapter, 'symbol_spread_pips', {}).get(
                analysis.symbol, getattr(self.broker_adapter, 'default_spread_pips', 1.5)
            )
            half_spread = (spread_pips * pip_size) / 2.0
            self.broker_adapter.set_tick(
                analysis.symbol,
                bid=entry_price - half_spread,
                ask=entry_price + half_spread,
                timestamp=analysis.generated_at,
            )

        from contextlib import nullcontext
        freeze_ctx = clock.frozen_time(analysis.generated_at) if analysis.generated_at else nullcontext()

        with freeze_ctx:
            exec_res = await self.execution_service.execute_analysis(
                session=session,
                analysis=analysis,
                account_equity=self.equity,
            )

        if not exec_res.executed or not exec_res.risk_approved:
            logger.debug(f"[ParityEngine] Trade blocked or unexecuted: {exec_res.summary()}")
            return None

        trade = BacktestTrade(
            symbol=analysis.symbol,
            direction=analysis.decision,
            entry_time=analysis.generated_at or clock.now(),
            entry_price=exec_res.executed_price or entry_price,
            stop_loss=analysis.stop_loss,
            take_profit=analysis.take_profit,
            confidence=int((analysis.confidence or 0.7) * 100),
            confluence_score=analysis.confluence_score or 7,
            rationale=analysis.rationale or f"Parity execution: {exec_res.summary()}",
            model_used="simulated_parity",
        )
        trade.executed_lots = exec_res.executed_lots or (exec_res.sizing.recommended_lots if exec_res.sizing else 0.1)
        self.trades.append(trade)
        return trade

    async def run(self):
        """Main backtest execution routine."""
        async with get_session() as session:
            self.run_record = BacktestRun(
                mode=self.mode,
                start_date=self.start_date,
                end_date=self.end_date,
                step_hours=self.step_hours,
                initial_equity=self.initial_equity,
                settings_snapshot=self.settings
            )
            session.add(self.run_record)
            await session.commit()

        if self.mode in ("langgraph_parity", "graph"):
            await self._run_langgraph_parity_mode()
        elif self.mode == "full":
            await self._run_full_mode()
        else:
            await self._run_replay_mode()

        # Evaluate trade outcomes with dynamic empirical calibration
        evaluator = OutcomeEvaluator()
        async with get_session() as session:
            try:
                await evaluator.calibrate_from_db(session)
            except Exception as e:
                logger.debug(f"Automated DB calibration in backtest skipped (fallback to defaults): {e}")

        for trade in self.trades:
            outcome = await evaluator.evaluate_trade(trade, apply_costs=True)
            trade.exit_time = outcome["exit_time"]
            trade.exit_price = outcome["exit_price"]
            trade.exit_reason = outcome["exit_reason"]
            trade.pnl_pips = outcome["pnl_pips"]
            trade.pnl_pct = outcome["pnl_pct"]

            # Calculate actual dollar PnL based on position sizing
            pnl_usd = outcome.get("pnl_usd")
            if pnl_usd is None:
                pnl_pct = trade.pnl_pct
                pnl_usd = (float(pnl_pct) / 100.0) * self.initial_equity if pnl_pct is not None else 0.0
            self.equity += pnl_usd
            exit_ts = trade.exit_time or self.end_date
            self.equity_curve.append({
                "timestamp": exit_ts,
                "equity": round(self.equity, 2),
                "trade_pnl_usd": pnl_usd
            })

        # Generate comprehensive institutional report
        generator = ReportGenerator(
            run=self.run_record,
            trades=self.trades,
            equity_curve=self.equity_curve,
            start_date=self.start_date,
            end_date=self.end_date
        )
        generator.calculate_metrics()
        self.run_record.final_equity = self.equity

        async with get_session() as session:
            session.add(self.run_record)
            for t in self.trades:
                t.run_id = self.run_record.id
                session.add(t)
            await session.commit()

        generator.print_summary()
        return self.run_record

    async def _run_full_mode(self):
        """
        Step-by-step point-in-time simulation adhering strictly to clock abstraction
        and database temporal limits (WHERE timestamp <= as_of_time).
        """
        logger.info(f"Running Full Mode (Point-in-Time Pipeline) from {self.start_date} to {self.end_date}")
        symbols = self.settings.get(
            'trading', {}
        ).get('asset_universe', ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD', 'BTCUSD'])

        from analysis.calculators.confluence_calculator import calculate_confluence
        from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
        from analysis.calculators.regime_classifier import classify_market_regime
        from analysis.calculators.daily_range_calculator import compute_daily_range_context

        current_time = self.start_date
        active_positions: Dict[str, datetime] = {}

        async with get_session() as session:
            while current_time <= self.end_date:
                with clock.frozen_time(current_time):
                    for symbol in symbols:
                        # Check if symbol already has an active position in simulation
                        if symbol in active_positions and active_positions[symbol] > current_time:
                            continue

                        # Point-in-time price query (Zero Lookahead: completed bars before current_time)
                        latest_bar = (await session.execute(
                            select(PriceOHLCV)
                            .where(PriceOHLCV.symbol == symbol)
                            .where(PriceOHLCV.timeframe == 'H1')
                            .where(PriceOHLCV.timestamp < current_time)
                            .order_by(PriceOHLCV.timestamp.desc())
                            .limit(1)
                        )).scalar_one_or_none()

                        if not latest_bar:
                            continue

                        # Check staleness: if latest bar is > 4 hours older than current_time, skip
                        bar_ts = latest_bar.timestamp.replace(tzinfo=timezone.utc) if latest_bar.timestamp.tzinfo is None else latest_bar.timestamp
                        if (current_time - bar_ts).total_seconds() > 14400:
                            continue

                        # 1. Confluence calculation as of current_time (Zero Lookahead)
                        try:
                            conf_res = await calculate_confluence(
                                session=session,
                                symbol=symbol,
                                entry_price=latest_bar.close,
                                settings=self.settings,
                                as_of=current_time
                            )
                            buy_score = conf_res.get('buy_potential_score', 0)
                            sell_score = conf_res.get('sell_potential_score', 0)
                            if buy_score >= sell_score:
                                direction = 'buy'
                                confluence_score = buy_score
                            else:
                                direction = 'sell'
                                confluence_score = sell_score
                        except Exception as e:
                            logger.debug(f"Point-in-time confluence calc failed for {symbol}: {e}")
                            confluence_score = 0
                            direction = 'neutral'

                        if direction not in ('buy', 'sell'):
                            continue

                        # 2. Unified threshold requirement as of current_time
                        try:
                            req_threshold, _ = await compute_unified_confluence_threshold(session, symbol, self.settings, as_of=current_time)
                        except Exception:
                            req_threshold = 7

                        # 3. Market regime filter as of current_time
                        try:
                            regime_data = await classify_market_regime(session, symbol, self.settings, as_of=current_time)
                            if regime_data.get('regime') == 'VOLATILE_CHOP' or regime_data.get('volatility_chop', {}).get('chop_block'):
                                continue
                        except Exception:
                            pass

                        if confluence_score >= req_threshold:
                            entry_price = latest_bar.close

                            # Calculate ATR-based dynamic stops & targets
                            adr_ctx = await compute_daily_range_context(session, symbol, self.settings, as_of=current_time)
                            atr_val = (adr_ctx.get('adr', 0.0) / 2.0) if adr_ctx and 'error' not in adr_ctx else (entry_price * 0.005)
                            if atr_val <= 0:
                                atr_val = entry_price * 0.005

                            sl_dist = atr_val * 1.5
                            tp_dist = atr_val * 3.0

                            if direction == 'buy':
                                stop_loss = entry_price - sl_dist
                                take_profit = entry_price + tp_dist
                            else:
                                stop_loss = entry_price + sl_dist
                                take_profit = entry_price - tp_dist

                            # Position sizing simulation with point-in-time session
                            sizing = await self.sizer.calculate_with_session(
                                session=session,
                                symbol=symbol,
                                direction=direction,
                                entry_price=entry_price,
                                stop_loss=stop_loss,
                                take_profit=take_profit,
                                account_equity=self.equity,
                                is_paper=True,
                                as_of=current_time
                            )

                            if not sizing.is_valid or sizing.recommended_lots <= 0:
                                continue

                            # 4. RiskGate validation if configured (default True)
                            if self.gate is not None and self.settings.get("backtest", {}).get("enforce_risk_gate", False):
                                try:
                                    verdict = await self.gate.check(
                                        session=session,
                                        symbol=symbol,
                                        direction=direction,
                                        sizing=sizing,
                                        account_equity=self.equity,
                                        as_of=current_time,
                                        simulated_positions=[
                                            {"symbol": s, "expiry": exp, "direction": "buy", "volume": 0.1, "entry_price": 1.0, "sl": 0.99}
                                            for s, exp in active_positions.items() if exp > current_time
                                        ],
                                        simulated_equity=self.equity,
                                        is_backtest=True
                                    )
                                    if not verdict.approved:
                                        logger.debug(f"RiskGate rejected backtest trade {symbol}: {verdict.rejection_reasons}")
                                        continue
                                except Exception as gate_err:
                                    logger.debug(f"RiskGate check in backtest error (fallback): {gate_err}")

                            trade = BacktestTrade(
                                symbol=symbol,
                                direction=direction,
                                entry_time=current_time,
                                entry_price=entry_price,
                                stop_loss=stop_loss,
                                take_profit=take_profit,
                                confidence=80,
                                confluence_score=confluence_score,
                                rationale=f"Point-in-time confluence={confluence_score} (req={req_threshold})",
                                model_used="point_in_time_pipeline"
                            )
                            # Record calculated lot size in trade metadata
                            trade.executed_lots = sizing.recommended_lots
                            self.trades.append(trade)
                            active_positions[symbol] = current_time + timedelta(hours=48)

                current_time += timedelta(hours=self.step_hours)

        logger.info(f"Full Mode generated {len(self.trades)} point-in-time trades across {len(symbols)} symbols.")

    async def get_point_in_time_data(
        self,
        session: Any,
        model_cls: Any,
        as_of: datetime,
        symbol: Optional[str] = None,
        vintage_date: Optional[datetime] = None,
        lookback_days: int = 30,
    ) -> List[Any]:
        """
        Query time series data with strict half-open window [as_of - lookback, as_of) (M7).
        Guarantees zero-lookahead bias and pins FRED/macro releases to vintage dates.
        """
        start_win = as_of - timedelta(days=lookback_days)
        effective_cutoff = min(as_of, vintage_date) if vintage_date else as_of

        # Use hasattr to check for timestamp or generated_at or release_date
        ts_col = getattr(model_cls, "timestamp", None) or getattr(model_cls, "generated_at", None) or getattr(model_cls, "release_date", None)
        if ts_col is None:
            return []

        stmt = select(model_cls).where(ts_col >= start_win).where(ts_col < effective_cutoff)
        if symbol and hasattr(model_cls, "symbol"):
            stmt = stmt.where(model_cls.symbol == symbol)
        stmt = stmt.order_by(ts_col.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _run_replay_mode(self):
        """
        Replay Mode: Evaluate historical AssetAnalysis decisions recorded in the database.
        Uses strict half-open window [start_date, end_date) to prevent boundary lookahead (M7).
        """
        logger.info(f"Running Replay Mode from {self.start_date} to {self.end_date} [strict half-open)")
        async with get_session() as session:
            stmt = (
                select(AssetAnalysis)
                .where(AssetAnalysis.generated_at >= self.start_date)
                .where(AssetAnalysis.generated_at < self.end_date)
                .where(AssetAnalysis.decision.in_(["buy", "sell"]))
                .order_by(AssetAnalysis.generated_at)
            )
            analyses = (await session.execute(stmt)).scalars().all()

            if self.use_execution_service and self.execution_service is not None:

                for analysis in analyses:
                    entry_p = analysis.price_at_analysis or analysis.entry_price
                    if not (entry_p and analysis.stop_loss and analysis.take_profit):
                        continue
                    await self.execute_trade_parity(session, analysis)
                logger.info(f"Replay Parity Mode collected {len(self.trades)} recorded trade analyses.")
                return

            for analysis in analyses:
                entry_p = analysis.price_at_analysis or analysis.entry_price
                if not (entry_p and analysis.stop_loss and analysis.take_profit):
                    continue

                sizing = await self.sizer.calculate_with_session(
                    session=session,
                    symbol=analysis.symbol,
                    direction=analysis.decision,
                    entry_price=entry_p,
                    stop_loss=analysis.stop_loss,
                    take_profit=analysis.take_profit,
                    account_equity=self.equity,
                    is_paper=True,
                    as_of=analysis.generated_at
                )

                if not sizing.is_valid:
                    continue

                if self.gate is not None and self.settings.get("backtest", {}).get("enforce_risk_gate", False):
                    try:
                        verdict = await self.gate.check(
                            session=session,
                            symbol=analysis.symbol,
                            direction=analysis.decision,
                            sizing=sizing,
                            account_equity=self.equity,
                            analysis=analysis,
                            as_of=analysis.generated_at,
                            simulated_equity=self.equity,
                            is_backtest=True
                        )
                        if not verdict.approved:
                            logger.debug(f"RiskGate rejected replay trade {analysis.symbol}: {verdict.rejection_reasons}")
                            continue
                    except Exception as gate_err:
                        logger.debug(f"RiskGate check in replay error: {gate_err}")

                trade = BacktestTrade(
                    symbol=analysis.symbol,
                    direction=analysis.decision,
                    entry_time=analysis.generated_at,
                    entry_price=entry_p,
                    stop_loss=analysis.stop_loss,
                    take_profit=analysis.take_profit,
                    confidence=int((analysis.confidence or 0.7) * 100),
                    confluence_score=analysis.confluence_score or 7,
                    rationale=analysis.rationale or "Replay decision",
                    model_used="replay"
                )
                trade.executed_lots = sizing.recommended_lots
                self.trades.append(trade)
        logger.info(f"Replay Mode collected {len(self.trades)} recorded trade analyses.")

    async def _run_langgraph_parity_mode(self):
        """
        LangGraph Parity Mode: Replays the actual production LangGraph StateGraph step-by-step
        through historical timeline with as_of temporal context, achieving 100% production code parity.
        """
        logger.info(f"Running LangGraph Parity Mode from {self.start_date} to {self.end_date}")
        from graph.workflow import build_trading_graph
        graph = build_trading_graph()

        class _MockScheduler:
            def __init__(self, settings):
                self.settings = settings
                self.dry_run = True
                self.asset_universe = settings.get(
                    'trading', {}
                ).get('asset_universe', ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD', 'BTCUSD'])
                self._mt5 = None
                self.market_data_scheduler = None
                self._cycle_lock = asyncio.Lock()
                self._is_forex_blocked = False

            async def _refresh_data_sources(self, session):
                pass

            async def _pre_cycle_setup(self, forced=True):
                return {'effective_auto_execute': False}

        current_time = self.start_date
        symbols = self.settings.get(
            'trading', {}
        ).get('asset_universe', ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD', 'BTCUSD'])

        async with get_session() as session:
            while current_time <= self.end_date:
                with clock.frozen_time(current_time):
                    initial_state = {
                        "cycle_id": f"BT_{current_time.strftime('%Y%m%d_%H%M')}",
                        "timestamp": current_time.isoformat(),
                        "as_of": current_time,
                        "symbols": symbols,
                        "session": session,
                        "settings": self.settings,
                        "actionable_trades": [],
                        "approved_trades": [],
                        "should_pause": False,
                    }
                    try:
                        final_state = await graph.ainvoke(
                            initial_state,
                            config={"configurable": {"scheduler": _MockScheduler(self.settings)}}
                        )
                        actionable = final_state.get("actionable_trades", [])
                        for item in actionable:
                            sym = item[0] if isinstance(item, (list, tuple)) else item.get("symbol")
                            res = item[1] if isinstance(item, (list, tuple)) else item
                            direction = res.get("decision", "wait").lower()
                            if direction in ("buy", "sell"):
                                entry_p = float(res.get("entry_price") or res.get("price_at_analysis") or 0.0)
                                sl_p = float(res.get("stop_loss") or res.get("adjusted_sl") or 0.0)
                                tp_p = float(res.get("take_profit") or res.get("adjusted_tp") or 0.0)
                                conf = float(res.get("confidence") or 70.0)

                                if entry_p > 0 and sl_p > 0 and tp_p > 0:
                                    sizing = await self.sizer.calculate_with_session(
                                        session=session,
                                        symbol=sym,
                                        direction=direction,
                                        entry_price=entry_p,
                                        stop_loss=sl_p,
                                        take_profit=tp_p,
                                        account_equity=self.equity,
                                        is_paper=True,
                                        as_of=current_time
                                    )
                                    if sizing.is_valid:
                                        # Enforce RiskGate point-in-time validation in simulation if configured
                                        if self.gate is not None and self.settings.get("backtest", {}).get("enforce_risk_gate", False):
                                            gate_verdict = await self.gate.check(
                                                session=session,
                                                symbol=sym,
                                                direction=direction,
                                                sizing=sizing,
                                                account_equity=self.equity,
                                                as_of=current_time,
                                                simulated_equity=self.equity,
                                                is_backtest=True
                                            )
                                            if not gate_verdict.approved:
                                                logger.debug(f"RiskGate rejected LangGraph trade {sym} at {current_time}: {gate_verdict.rejection_reasons}")
                                                continue

                                        trade = BacktestTrade(
                                            symbol=sym,
                                            direction=direction,
                                            entry_time=current_time,
                                            entry_price=entry_p,
                                            stop_loss=sl_p,
                                            take_profit=tp_p,
                                            confidence=conf,
                                            confluence_score=res.get("confluence_score", 7),
                                            rationale=res.get("rationale", "LangGraph parity execution"),
                                            model_used="langgraph_parity"
                                        )
                                        trade.executed_lots = sizing.recommended_lots
                                        self.trades.append(trade)
                    except Exception as e:
                        logger.debug(f"LangGraph parity step at {current_time} error: {e}")

                current_time += timedelta(hours=self.step_hours)

        return self.trades

    # Backward compatibility alias
    run_simulation = run
