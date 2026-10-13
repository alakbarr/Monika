# ==============================================================================
# File: application/analysis/tools/mixins/system_tools.py
# ==============================================================================

"""
System, History, and Specialist Delegation Tools Mixin for ToolExecutor.
Encapsulates delegated calls to execution, history, telemetry, and subagent tools.
"""

from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.mixins.base import _ToolExecutorMixinBase, logger
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    FundamentalBrief,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    RiskState,
    SystemConfig,
    TradeTrigger,
)


class SystemToolsMixin(_ToolExecutorMixinBase):
    """Mixin providing standard diagnostic, history, and system delegator tool methods."""

    async def _tool_get_verified_market_snapshot(self, inp: dict) -> dict:
        """Deterministic ground-truth market snapshot (anti-hallucination anchor)."""
        from monika.application.analysis.tools.handlers.verified_snapshot import VerifiedMarketSnapshotHandler

        handler = VerifiedMarketSnapshotHandler(self.settings)
        res = await handler.execute(inp, self.session, executor=self)
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                return {"raw_snapshot": res}
        return res if isinstance(res, dict) else {"snapshot": res}

    async def _tool_execute_analysis_code(self, inp: dict) -> dict:
        """Execute sandboxed Python code with tool access (PTC)."""
        from monika.application.analysis.tools.handlers.ptc_handler import PTCHandler

        ptc = PTCHandler(tool_executor=self, settings=self.settings)
        code_str = inp.get("code", "") if isinstance(inp, dict) else str(inp)
        return await ptc.execute(code=code_str)

    async def _tool_web_search(self, inp: dict) -> dict:
        """Execute web search directly via news_tools.handle_web_search."""
        from monika.application.analysis.tools.handlers.news_tools import handle_web_search

        return await handle_web_search(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_update_scratchpad(self, inp: dict) -> dict:
        """Updates active working scratchpad with intermediate calculation anchors."""
        symbol = self._resolve_symbol(inp) or self.symbol or "DEFAULT"
        from monika.application.analysis.memory.working_scratchpad import WorkingScratchpad

        updated = WorkingScratchpad.update_scratchpad(symbol, inp)
        summary = WorkingScratchpad.get_summary_text(symbol)
        return {
            "status": "success",
            "message": f"Scratchpad for {symbol} updated successfully.",
            "summary": summary,
            "scratchpad": updated,
        }

    async def _tool_read_scratchpad(self, inp: dict) -> dict:
        """Reads active working scratchpad anchors for the current analysis session."""
        symbol = self._resolve_symbol(inp) or self.symbol or "DEFAULT"
        from monika.application.analysis.memory.working_scratchpad import WorkingScratchpad

        state = WorkingScratchpad.read_scratchpad(symbol)
        summary = WorkingScratchpad.get_summary_text(symbol)
        return {"status": "success", "symbol": symbol, "summary": summary, "scratchpad": state}

    async def _tool_transition_analysis_phase(self, inp: dict) -> dict:
        """Records explicit phase advancement request."""
        target_phase = int(inp.get("target_phase", 2))
        rationale = inp.get("rationale", "")
        return {
            "status": "success",
            "target_phase": target_phase,
            "rationale": rationale,
            "message": f"Phase transition to Phase {target_phase} acknowledged. Unlocking phase tools.",
        }

    async def _tool_get_timesfm_forecast(self, *args, **kwargs) -> dict:
        """Forecast future price distribution using TimesFM foundation model."""
        from monika.application.analysis.tools.handlers.timesfm import handle_get_timesfm_forecast

        inp = {}
        if args:
            if isinstance(args[0], dict):
                inp = dict(args[0])
            else:
                inp["symbol"] = args[0]
                if len(args) > 1:
                    inp["timeframe"] = args[1]
                if len(args) > 2:
                    inp["horizon_steps"] = args[2]
        inp.update(kwargs)
        if "horizon" in inp and "horizon_steps" not in inp:
            inp["horizon_steps"] = inp.pop("horizon")
        return await handle_get_timesfm_forecast(executor=self, session=self.session, settings=self.settings, **inp)

    async def _tool_get_paper_trading_performance(self, inp: dict) -> dict:
        from monika.core.analytics.paper_tracker import PaperTracker

        days_back = int(inp["days_back"]) if inp.get("days_back") is not None else None
        tracker = PaperTracker(self.settings)
        stats = await tracker.get_statistics(self.session, days_back=days_back)
        equity_curve = await tracker.simulate_equity_curve(self.session)
        suspended = await tracker.get_suspended_symbols(self.session)

        return {
            "period": f"Past {days_back} days" if days_back else "All-time",
            "total_trades": stats.get("total_trades", 0),
            "market_trades": stats.get("market_trades", 0),
            "wins": stats.get("wins", 0),
            "losses": stats.get("losses", 0),
            "win_rate_pct": stats.get("win_rate_pct", 0),
            "total_pnl_pct": stats.get("total_pnl_pct", 0),
            "avg_pnl_pct": stats.get("avg_pnl_pct", 0),
            "avg_win_pct": stats.get("avg_win_pct", 0),
            "avg_loss_pct": stats.get("avg_loss_pct", 0),
            "avg_rr_achieved": stats.get("avg_rr_achieved", 0),
            "expectancy_per_trade_R": stats.get("expectancy_per_trade_R", 0),
            "expectancy_per_trade_pct": stats.get("expectancy_per_trade_pct", 0),
            "has_positive_edge": stats.get("has_positive_edge", False),
            "suspended_symbols": suspended,
            "by_symbol": stats.get("by_symbol", {}),
            "simulated_equity": {
                "starting_equity": equity_curve.get("starting_equity", 10000.0),
                "final_equity": equity_curve.get("final_equity", 10000.0),
                "total_return_pct": equity_curve.get("total_return_pct", 0.0),
                "max_drawdown_pct": equity_curve.get("max_drawdown_pct", 0.0),
            }
            if equity_curve
            else None,
            "recent_trades": stats.get("recent_20", [])[-10:],
        }

    async def _tool_get_trade_history(self, inp: dict) -> dict:
        symbol = inp.get("symbol")
        if symbol:
            symbol = symbol.upper().replace("/", "")
        status = inp.get("status", "closed")
        mode = inp.get("mode", "all")
        limit = min(inp.get("limit", 10), 50)
        days_back = inp.get("days_back")

        trades = []

        if mode in ("all", "paper"):
            q_paper = select(PaperTradeRecord)
            if symbol:
                q_paper = q_paper.where(PaperTradeRecord.symbol == symbol)
            if status != "all":
                q_paper = q_paper.where(PaperTradeRecord.status == status)
            if days_back:
                cutoff = clock.now() - timedelta(days=days_back)
                q_paper = q_paper.where(PaperTradeRecord.closed_at >= cutoff)
            q_paper = q_paper.order_by(PaperTradeRecord.opened_at.desc()).limit(limit)

            paper_rows = (await self.session.execute(q_paper)).scalars().all()
            for r in paper_rows:
                trades.append(
                    {
                        "id": r.id,
                        "type": "paper",
                        "symbol": r.symbol,
                        "direction": r.direction,
                        "entry_price": r.entry_price,
                        "exit_price": r.exit_price,
                        "stop_loss": r.stop_loss,
                        "take_profit": r.take_profit,
                        "status": r.status,
                        "exit_reason": r.exit_reason,
                        "pnl_pct": r.pnl_pct,
                        "holding_hours": r.holding_hours,
                        "opened_at": r.opened_at.isoformat() if r.opened_at is not None else "",
                        "closed_at": r.closed_at.isoformat() if r.closed_at is not None else "",
                        "analysis_id": getattr(r, "analysis_id", None),
                    }
                )

        if mode in ("all", "live"):
            q_live = select(Position)
            if symbol:
                q_live = q_live.where(Position.symbol == symbol)
            if status != "all":
                q_live = q_live.where(Position.status == status)
            if days_back:
                cutoff = clock.now() - timedelta(days=days_back)
                q_live = q_live.where(Position.opened_at >= cutoff)
            q_live = q_live.order_by(Position.opened_at.desc()).limit(limit)

            live_rows = (await self.session.execute(q_live)).scalars().all()
            for r in live_rows:
                trades.append(
                    {
                        "id": r.id,
                        "type": "live",
                        "mt5_ticket": r.mt5_ticket,
                        "symbol": r.symbol,
                        "direction": r.direction,
                        "volume": r.volume,
                        "entry_price": r.entry_price,
                        "exit_price": getattr(r, "exit_price", None),
                        "stop_loss": r.sl,
                        "take_profit": r.tp,
                        "status": r.status,
                        "exit_reason": getattr(r, "close_reason", None),
                        "pnl": r.pnl,
                        "opened_at": r.opened_at.isoformat() if r.opened_at is not None else "",
                        "closed_at": r.closed_at.isoformat() if r.closed_at is not None else "",
                    }
                )

        trades.sort(key=lambda x: x.get("opened_at") or "", reverse=True)
        trades = trades[:limit]

        return {
            "count": len(trades),
            "trades": trades,
        }

    async def _tool_get_active_triggers(self, inp: dict) -> dict:
        symbol = inp.get("symbol")
        if symbol:
            symbol = symbol.upper().replace("/", "")
        status = inp.get("status", "pending")
        limit = min(inp.get("limit", 10), 50)

        q = select(TradeTrigger, AssetAnalysis).join(AssetAnalysis, TradeTrigger.asset_analysis_id == AssetAnalysis.id)
        if symbol:
            q = q.where(AssetAnalysis.symbol == symbol)
        if status != "all":
            q = q.where(TradeTrigger.status == status)

        q = q.order_by(TradeTrigger.created_at.desc()).limit(limit)
        results = (await self.session.execute(q)).all()

        triggers = []
        for trigger, analysis in results:
            last_bar = (
                await self.session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == analysis.symbol)
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            current_price = last_bar.close if last_bar else None

            import json as _j

            cond = {}
            try:
                cond = _j.loads(trigger.condition_json) if trigger.condition_json else {}
            except Exception:
                pass

            price_distance = None
            target_level = cond.get("price") or cond.get("price_level") or analysis.invalidation_price
            if current_price and target_level:
                try:
                    price_distance = round(abs(current_price - float(target_level)), 5)
                except Exception:
                    pass

            triggers.append(
                {
                    "trigger_id": trigger.id,
                    "symbol": analysis.symbol,
                    "trigger_type": trigger.trigger_type,
                    "status": trigger.status,
                    "condition": cond,
                    "analysis_id": analysis.id,
                    "decision": analysis.decision,
                    "confidence": analysis.confidence,
                    "current_price": current_price,
                    "target_level": target_level,
                    "price_distance": price_distance,
                    "created_at": trigger.created_at.isoformat()
                    if hasattr(trigger.created_at, "isoformat")
                    else str(trigger.created_at or ""),
                }
            )

        return {
            "count": len(triggers),
            "triggers": triggers,
        }

    async def _tool_get_system_health(self, inp: dict) -> dict:
        today_start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
        risk = (
            await self.session.execute(
                select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
            )
        ).scalar_one_or_none()

        last_brief = (
            await self.session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
        ).scalar_one_or_none()

        cutoff_err = clock.now() - timedelta(hours=2)
        recent_errors = (
            (
                await self.session.execute(
                    select(ActivityLog)
                    .where(ActivityLog.timestamp >= cutoff_err)
                    .where(ActivityLog.category.in_(["error", "system_error", "exception"]))
                    .order_by(ActivityLog.timestamp.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        mode = "live" if not self.settings.get("paper_trading", {}).get("enabled", True) else "paper"
        trading_paused = risk.trading_paused if risk else False

        return {
            "status": "PAUSED" if trading_paused else ("DEGRADED" if recent_errors else "HEALTHY"),
            "trading_paused": trading_paused,
            "mode": mode,
            "daily_pnl": risk.daily_pnl if risk else 0.0,
            "current_drawdown": risk.current_drawdown if risk else 0.0,
            "last_brief_time": last_brief.generated_at.isoformat()
            if last_brief and hasattr(last_brief.generated_at, "isoformat")
            else (str(last_brief.generated_at) if last_brief else None),
            "recent_error_count": len(recent_errors),
        }

    async def _tool_get_open_positions(self, inp: dict) -> dict:
        mode = inp.get("mode", "all")
        symbol = inp.get("symbol")
        if symbol:
            symbol = symbol.upper().replace("/", "")

        positions = []

        if mode in ("all", "live"):
            q_pos = select(Position).where(Position.status == "open")
            if symbol:
                q_pos = q_pos.where(Position.symbol == symbol)
            live_rows = (await self.session.execute(q_pos)).scalars().all()
            for r in live_rows:
                positions.append(
                    {
                        "id": r.id,
                        "type": "live",
                        "mt5_ticket": r.mt5_ticket,
                        "symbol": r.symbol,
                        "direction": r.direction,
                        "volume": r.volume,
                        "entry_price": r.entry_price,
                        "sl": r.sl,
                        "tp": r.tp,
                        "opened_at": r.opened_at.isoformat()
                        if hasattr(r.opened_at, "isoformat")
                        else str(r.opened_at or ""),
                        "pnl": r.pnl,
                    }
                )

        if mode in ("all", "paper"):
            q_paper = select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
            if symbol:
                q_paper = q_paper.where(PaperTradeRecord.symbol == symbol)
            paper_rows = (await self.session.execute(q_paper)).scalars().all()
            for r in paper_rows:
                last_bar = (
                    await self.session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == r.symbol)
                        .where(PriceOHLCV.timestamp <= clock.now())
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                floating_pnl_pct = 0.0
                if last_bar and r.entry_price:
                    if r.direction == "buy":
                        floating_pnl_pct = round((last_bar.close - r.entry_price) / r.entry_price * 100, 3)
                    else:
                        floating_pnl_pct = round((r.entry_price - last_bar.close) / r.entry_price * 100, 3)
                positions.append(
                    {
                        "id": r.id,
                        "type": "paper",
                        "symbol": r.symbol,
                        "direction": r.direction,
                        "entry_price": r.entry_price,
                        "sl": r.stop_loss,
                        "tp": r.take_profit,
                        "opened_at": r.opened_at.isoformat()
                        if hasattr(r.opened_at, "isoformat")
                        else str(r.opened_at or ""),
                        "floating_pnl_pct": floating_pnl_pct,
                    }
                )

        return {
            "count": len(positions),
            "positions": positions,
        }

    async def _tool_get_spread_snapshot(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_spread_snapshot

        return await handle_get_spread_snapshot(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_multi_timeframe_summary(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_multi_timeframe_summary

        return await handle_get_multi_timeframe_summary(
            inp, session=self.session, executor=self, settings=self.settings
        )

    async def _tool_get_chart(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_chart

        return await handle_get_chart(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_fibonacci_levels(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_get_fibonacci_levels

        return await handle_get_fibonacci_levels(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_portfolio_exposure(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_get_portfolio_exposure

        return await handle_get_portfolio_exposure(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_swap_rates(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trading_tools import handle_get_swap_rates

        return await handle_get_swap_rates(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_market_regime(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_market_regime

        return await handle_get_market_regime(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_run_monte_carlo_simulation(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_run_monte_carlo_simulation

        return await handle_run_monte_carlo_simulation(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_weekly_macro_summary(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.macro_tools import handle_get_weekly_macro_summary

        return await handle_get_weekly_macro_summary(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_manage_cron(self, inp: dict) -> dict:
        from monika.application.analysis.tools.domain.cron_tool import CronActionInput, handle_manage_cron

        input_obj = CronActionInput(**inp) if isinstance(inp, dict) else inp
        return await handle_manage_cron(input_obj, context=self)

    async def _tool_query_signal_performance(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_query_signal_performance

        return await handle_query_signal_performance(inp, session=self.session, executor=self)

    async def _tool_get_latest_risk_verdict(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_get_latest_risk_verdict

        return await handle_get_latest_risk_verdict(inp, session=self.session, executor=self)

    async def _tool_export_debate_transcripts(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_export_debate_transcripts

        return await handle_export_debate_transcripts(inp, session=self.session, executor=self)

    async def _tool_trigger_learning_cycle(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_trigger_learning_cycle

        return await handle_trigger_learning_cycle(inp, session=self.session, executor=self)

    async def _tool_run_system_doctor_check(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.system_info import handle_run_system_doctor_check

        return await handle_run_system_doctor_check(inp, session=self.session, executor=self)

    async def _tool_set_trailing_stop(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.position_mgmt import handle_set_trailing_stop

        return await handle_set_trailing_stop(inp, session=self.session, settings=self.settings, executor=self)

    async def _tool_export_historical_data_csv(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.market_data_tools import handle_export_historical_data_csv

        return await handle_export_historical_data_csv(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_trigger_market_scan(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_trigger_market_scan

        return await handle_trigger_market_scan(inp, session=self.session, executor=self)

    async def _tool_run_strategy_backtest(self, inp: dict) -> dict:
        from monika.application.analysis.tools.handlers.trade_intel import handle_run_strategy_backtest

        return await handle_run_strategy_backtest(inp, session=self.session, executor=self)

    async def _tool_get_retail_sentiment(self, inp: dict) -> dict:
        import json as _json

        cfg = (
            await self.session.execute(select(SystemConfig).where(SystemConfig.key == "binance_sentiment_latest"))
        ).scalar_one_or_none()

        if not cfg or not cfg.value:
            return {"error": "Retail sentiment data not available. Ensure cycle scheduler has run."}
        try:
            return _json.loads(cfg.value)
        except Exception as e:
            return {"error": f"Parse error: {e}"}

    async def _tool_get_forex_sentiment(self, inp: dict) -> dict:
        import json as _json

        cfg = (
            await self.session.execute(select(SystemConfig).where(SystemConfig.key == "myfxbook_sentiment_latest"))
        ).scalar_one_or_none()

        if not cfg or not cfg.value:
            # Fallback to FXSSI sentiment if MyFxBook is not available
            fxssi_cfg = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == "fxssi_sentiment_latest"))
            ).scalar_one_or_none()
            if fxssi_cfg and fxssi_cfg.value:
                try:
                    return _json.loads(fxssi_cfg.value)
                except Exception:
                    pass
            return {"error": "Forex sentiment data not available. Ensure cycle scheduler has run."}
        try:
            return _json.loads(cfg.value)
        except Exception as e:
            return {"error": f"Parse error: {e}"}

    async def _tool_get_fxssi_sentiment(self, inp: dict) -> dict:
        import json as _json

        cfg = (
            await self.session.execute(select(SystemConfig).where(SystemConfig.key == "fxssi_sentiment_latest"))
        ).scalar_one_or_none()

        if not cfg or not cfg.value:
            return {"error": "FXSSI sentiment data not available. Ensure cycle scheduler has run."}
        try:
            return _json.loads(cfg.value)
        except Exception as e:
            return {"error": f"Parse error: {e}"}

    async def _tool_get_fundamental_brief(self, inp: dict) -> dict:
        row = (
            await self.session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
        ).scalar_one_or_none()

        if row is None:
            return {"error": "No fundamental brief found. Stage 1 must run first."}

        structured = json.loads(row.structured_json) if row.structured_json else {}

        now = clock.now()
        age_hours = (now - row.generated_at).total_seconds() / 3600
        is_stale = row.valid_until is not None and now > row.valid_until

        max_critical = float(self.settings.get("data_quality", {}).get("max_brief_age_analysis_hours", 12.0))
        max_warning = float(self.settings.get("data_quality", {}).get("max_brief_age_execution_hours", 10.0))
        if max_warning >= max_critical:
            max_warning = min(10.0, max_critical - 1.0)

        staleness_warning = ""
        if age_hours > max_critical:
            staleness_warning = f"\n\n[DARURAT] CRITICAL: Brief is {age_hours:.1f}h old (limit: {max_critical}h). MANDATORY WAIT for all assets. Do not submit BUY/SELL."
        elif age_hours > max_warning:
            staleness_warning = f"\n\n[PERINGATAN] STALE: Brief is {age_hours:.1f}h old (limit: {max_warning}h). High-impact events may have occurred. Be extra cautious and do not enter on macro-dependent setups."
        elif age_hours > 2:
            staleness_warning = (
                f"\n\n[INFO] Brief is {age_hours:.1f}h old. Cross-validate macro assumptions with recent price action."
            )

        return {
            "brief_id": row.id,
            "generated_at": row.generated_at.isoformat(),
            "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            "age_hours": round(age_hours, 1),
            "is_stale": is_stale,
            "staleness_warning": staleness_warning,
            **structured,
        }

    async def _tool_get_price_history(self, inp: dict) -> dict:
        symbol = self._resolve_symbol(inp) or inp.get("symbol")
        if not symbol:
            return {"error": "Missing required parameter 'symbol'"}
        timeframe = inp["timeframe"]
        limit = min(inp.get("limit", 50), 200)

        rows = (
            (
                await self.session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == timeframe)
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        rows = list(reversed(rows))  # chronological order

        # Optimize output tokens by returning CSV string instead of JSON array
        if not rows:
            return {"symbol": symbol, "timeframe": timeframe, "count": 0, "csv_data": ""}

        header = "time,open,high,low,close,volume\n"
        lines = [
            f"{r.timestamp.isoformat() if r.timestamp is not None else ''},{r.open},{r.high},{r.low},{r.close},{r.volume}"
            for r in rows
        ]
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(rows),
            "csv_data": header + "\n".join(lines),
        }

    async def _tool_propose_action(self, inp: dict) -> dict:
        """Propose manual action requiring confirmation."""
        from monika.application.analysis.tools.handlers.position_mgmt import handle_propose_action

        return await handle_propose_action(inp, session=self.session, executor=self)

    async def _tool_delegate_specialist_analysis(self, inp: dict) -> dict:
        """Execute delegated specialist analysis in isolated subagent harness."""
        role = inp.get("specialist_role", "technical_specialist")
        prompt = inp.get("task_prompt", "")
        symbol = inp.get("symbol", "")

        from monika.application.analysis.subagent.isolated_harness import IsolatedSubagentRunner
        from monika.application.analysis.tools.tools_definitions import MACRO_ANALYSIS_TOOLS, ASSET_CORE_TOOLS
        from monika.infrastructure.providers.llm_factory import get_client_for_task

        runner = IsolatedSubagentRunner(settings=self.settings)
        if role == "macro_specialist":
            client = get_client_for_task("stage1_fundamental", self.settings)
            tools = MACRO_ANALYSIS_TOOLS
            sys_prompt = "You are an institutional macro specialist. Deliver concise, evidence-grounded macro analysis."
        elif role == "sentiment_specialist":
            client = get_client_for_task("sentiment_analyst", self.settings)
            tools = MACRO_ANALYSIS_TOOLS
            sys_prompt = "You are a market sentiment specialist. Deliver concise sentiment and positioning analysis."
        elif role == "risk_specialist":
            client = get_client_for_task("risk_gate", self.settings)
            tools = ASSET_CORE_TOOLS
            sys_prompt = "You are a quantitative risk specialist. Evaluate structural levels, invalidation, and R:R."
        else:
            client = get_client_for_task("stage2_per_asset_primary", self.settings)
            tools = ASSET_CORE_TOOLS
            sys_prompt = (
                "You are an SMC technical specialist. Analyze market structure, order blocks, and key liquidity zones."
            )

        user_content = f"Symbol: {symbol}\nTask: {prompt}" if symbol else prompt
        messages = [{"role": "user", "content": user_content}]

        res = await runner.run_isolated(
            role_name=role,
            llm_client=client,
            system_prompt=sys_prompt,
            messages=messages,
            tools=tools,
            stage_name="chat_delegation",
            timeout=180,
            session=self.session,
        )

        return {
            "status": "success" if res.get("success") else "error",
            "specialist_role": role,
            "summary": res.get("final_text") or res.get("error", "No output"),
            "tool_calls_made": res.get("tool_calls_made", 0),
        }
