# ==============================================================================
# File: interfaces/cli/tui_app/mixins/data_sync.py
# Description: Data ingestion, DB query fallback, and UI state sync mixin
# ==============================================================================

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

import aiohttp
from textual.widgets import DataTable, RichLog, Static

from monika.core.config.settings import load_settings
from monika.interfaces.cli.sparklines import braille_sparkline
from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BRASS,
    BULL_PROFIT,
    MUTED,
    PAPER,
    PHOSPHOR_AMBER,
)
from monika.interfaces.cli.tui_app.base import _TuiMixinBase
from monika.interfaces.cli.tui_app.constants import DETERMINISTIC_RISK_CHECKS
from monika.interfaces.cli.tui_app.widgets import LiveTickerBanner, StatusBar

logger = logging.getLogger("TradingAgent.TUI")


class DataSyncMixin(_TuiMixinBase):
    """Mixin handling background polling, DB fallback queries, and UI widgets state sync."""

    def _scheduled_refresh(self) -> None:
        if self.is_running:
            try:
                loop = asyncio.get_running_loop()
                if not loop.is_closed():
                    task = asyncio.create_task(self.refresh_data())
                    if hasattr(self, "_background_tasks"):
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)
            except RuntimeError:
                pass

    async def refresh_data(self) -> None:
        """Fetch system data, positions, activity, and update all dashboard panels."""
        if self._refresh_lock.locked():
            return
        async with self._refresh_lock:
            try:
                data = await self._fetch_overview_data()
                self._update_ui_state(data)
            except Exception as e:
                logger.debug(f"[TUI] Error refreshing data: {e}")

    async def _fetch_overview_data(self) -> Dict[str, Any]:
        """Try fetching data via Dashboard API; fallback to direct DB if API unavailable."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Try API first
        if not self.standalone:
            try:
                timeout = aiohttp.ClientTimeout(total=2.0)
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                    overview_res = await session.get(f"{self.api_url}/api/overview")
                    positions_res = await session.get(f"{self.api_url}/api/positions?status=open")
                    activity_res = await session.get(f"{self.api_url}/api/activity?limit=30")
                    tokens_res = await session.get(f"{self.api_url}/api/v1/tokens/summary")
                    perf_res = await session.get(f"{self.api_url}/api/paper-trading")
                    signals_res = await session.get(f"{self.api_url}/api/signals/mt5?limit=20")
                    scorecard_res = await session.get(f"{self.api_url}/api/risk/scorecard")
                    yields_res = await session.get(f"{self.api_url}/api/market/yields")
                    fg_res = await session.get(f"{self.api_url}/api/market/fear-greed")
                    calendar_res = await session.get(f"{self.api_url}/api/calendar/events?days_ahead=3&limit=25")

                    if overview_res.status == 200 and positions_res.status == 200:
                        ov = await overview_res.json()
                        pos = await positions_res.json()
                        act = await activity_res.json() if activity_res.status == 200 else []
                        tok = await tokens_res.json() if tokens_res.status == 200 else {}
                        perf = await perf_res.json() if perf_res.status == 200 else {}
                        sig = await signals_res.json() if signals_res.status == 200 else []
                        sc = await scorecard_res.json() if scorecard_res.status == 200 else []
                        yd = await yields_res.json() if yields_res.status == 200 else {}
                        fg = await fg_res.json() if fg_res.status == 200 else {}
                        cal = await calendar_res.json() if calendar_res.status == 200 else []
                        return {
                            "source": "api",
                            "overview": ov,
                            "positions": pos,
                            "activity": act,
                            "tokens": tok,
                            "performance": perf,
                            "signals": sig,
                            "scorecard": sc,
                            "yields": yd,
                            "fear_greed": fg,
                            "calendar": cal,
                        }
            except Exception:
                pass

        # Fallback to direct DB query
        return await self._fetch_data_from_db()

    async def _fetch_data_from_db(self) -> Dict[str, Any]:
        """Query PostgreSQL directly for positions, configs, activity logs, and tokens."""
        from sqlalchemy import desc, func, select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import (
            ActivityLog,
            AssetAnalysis,
            PaperTradeRecord,
            Position,
            RiskState,
            SystemConfig,
            TokenUsageLog,
            VIXData,
        )

        res_data: Dict[str, Any] = {
            "source": "db",
            "overview": {},
            "positions": [],
            "activity": [],
            "tokens": {},
            "signals": [],
        }

        try:
            async with get_session() as session:
                # 1. Configs
                cfgs = (await session.execute(select(SystemConfig))).scalars().all()
                cfg_map = {c.key: c.value for c in cfgs}

                # 2. Positions
                real_pos = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                paper_pos = (
                    (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open")))
                    .scalars()
                    .all()
                )

                all_positions = []
                for p in real_pos:
                    all_positions.append(
                        {
                            "id": p.id,
                            "type": "REAL",
                            "symbol": p.symbol,
                            "direction": p.direction,
                            "volume": p.volume,
                            "entry_price": p.entry_price,
                            "sl": p.sl,
                            "tp": p.tp,
                            "pnl": round(p.pnl, 2) if p.pnl is not None else 0.0,
                        }
                    )
                for p in paper_pos:
                    all_positions.append(
                        {
                            "id": p.id,
                            "type": "PAPER",
                            "symbol": p.symbol,
                            "direction": p.direction,
                            "volume": getattr(p, "lots", 0.01),
                            "entry_price": p.entry_price,
                            "sl": p.stop_loss,
                            "tp": p.take_profit,
                            "pnl": round(getattr(p, "pnl", 0.0), 2),
                        }
                    )
                res_data["positions"] = all_positions

                # 3. Risk & PnL
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                risk = (
                    await session.execute(
                        select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
                    )
                ).scalar_one_or_none()
                daily_pnl = round(risk.daily_pnl, 2) if risk else 0.0

                # 4. VIX
                vix_row = (
                    await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))
                ).scalar_one_or_none()
                vix_val = vix_row.close if vix_row else 14.5

                # 5. Activity logs
                logs = (
                    (await session.execute(select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(30)))
                    .scalars()
                    .all()
                )
                res_data["activity"] = [
                    {
                        "id": l.id,
                        "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                        "category": l.category,
                        "description": l.description,
                        "actor": l.actor,
                    }
                    for l in reversed(logs)
                ]

                # 6. Tokens
                tok_row = (
                    await session.execute(
                        select(
                            func.sum(TokenUsageLog.cached_tokens).label("cached"),
                            func.sum(TokenUsageLog.input_tokens).label("inp"),
                            func.sum(TokenUsageLog.output_tokens).label("out"),
                            func.sum(TokenUsageLog.cost_estimate).label("cost"),
                        )
                    )
                ).first()

                res_data["overview"] = {
                    "kill_switch": str(cfg_map.get("kill_switch", "false")).lower() == "true",
                    "system_paused": str(cfg_map.get("system_paused", "false")).lower() == "true",
                    "auto_execute": str(cfg_map.get("auto_execute", "false")).lower() == "true",
                    "open_real_positions": len(real_pos),
                    "open_paper_positions": len(paper_pos),
                    "daily_pnl": daily_pnl,
                    "daily_pnl_pct": 0.0,
                    "vix": vix_val,
                }
                res_data["tokens"] = {
                    "total_cached_tokens": (tok_row.cached or 0) if tok_row else 0,
                    "total_input_tokens": (tok_row.inp or 0) if tok_row else 0,
                    "total_output_tokens": (tok_row.out or 0) if tok_row else 0,
                    "total_cost_usd": float((tok_row.cost or 0.0)) if tok_row else 0.0,
                }

                # 7. Performance metrics from closed trades
                closed_trades = (
                    (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")))
                    .scalars()
                    .all()
                )
                total_trades = len(closed_trades)
                wins = sum(1 for t in closed_trades if (t.pnl_pct or 0.0) > 0 or t.exit_reason == "tp_hit")
                win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
                gross_profit = sum((t.pnl_pct or 0.0) for t in closed_trades if (t.pnl_pct or 0.0) > 0)
                gross_loss = abs(sum((t.pnl_pct or 0.0) for t in closed_trades if (t.pnl_pct or 0.0) < 0))
                profit_factor = (
                    (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
                )

                recent_closed_desc = sorted(
                    closed_trades,
                    key=lambda x: x.closed_at or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
                consec_losses = 0
                for t in recent_closed_desc:
                    if (t.pnl_pct or 0.0) < 0 or t.exit_reason == "sl_hit":
                        consec_losses += 1
                    else:
                        break

                res_data["performance"] = {
                    "total_trades": total_trades,
                    "win_rate": round(win_rate, 1),
                    "profit_factor": round(profit_factor, 2),
                    "consecutive_losses": consec_losses,
                }

                # 8. Signals from recent analyses
                analyses = (
                    (await session.execute(select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(20)))
                    .scalars()
                    .all()
                )
                res_data["signals"] = [
                    {
                        "id": a.id,
                        "symbol": a.symbol,
                        "direction": getattr(a, "direction", "HOLD") or "HOLD",
                        "confidence": getattr(a, "confidence", 0.0) or 0.0,
                        "entry": getattr(a, "entry_price", None),
                        "sl": getattr(a, "stop_loss", None),
                        "tp": getattr(a, "take_profit", None),
                        "status": getattr(a, "status", "analyzed") or "analyzed",
                        "timestamp": a.generated_at.strftime("%H:%M:%S") if getattr(a, "generated_at", None) else "—",
                    }
                    for a in analyses
                ]

                # 9. Deterministic Risk Gate Scorecard
                try:
                    from monika.domain.risk.risk_gate import RiskGate

                    cfg = load_settings()
                    gate = RiskGate(cfg)
                    res_data["scorecard"] = await gate.get_current_scorecard(session)
                except Exception as sc_err:
                    logger.debug(f"[TUI] Scorecard DB fetch note: {sc_err}")
                    res_data["scorecard"] = []

                # 10. Economic Calendar
                try:
                    from datetime import timedelta

                    from monika.infrastructure.database.models import EconomicCalendar

                    now_utc = datetime.now(timezone.utc)
                    cal_q = (
                        select(EconomicCalendar)
                        .where(
                            EconomicCalendar.event_time >= now_utc - timedelta(hours=6),
                            EconomicCalendar.event_time <= now_utc + timedelta(days=3),
                        )
                        .order_by(EconomicCalendar.event_time.asc())
                        .limit(25)
                    )
                    cal_rows = (await session.execute(cal_q)).scalars().all()
                    res_data["calendar"] = [
                        {
                            "event_time": c.event_time.isoformat() if c.event_time else "",
                            "currency": c.currency or "USD",
                            "event_name": c.event_name or "",
                            "impact": (c.impact or "MEDIUM").upper(),
                            "forecast": c.forecast or "—",
                            "actual": c.actual or "—",
                        }
                        for c in cal_rows
                    ]
                except Exception as cal_err:
                    logger.debug(f"[TUI] Calendar DB fetch note: {cal_err}")
                    res_data["calendar"] = []
        except Exception as e:
            logger.debug(f"[TUI] DB fetch error: {e}")

        return res_data

    def _update_ui_state(self, data: Dict[str, Any]) -> None:
        """Distribute fetched data to DataTable, ActivityFeed, Banner, and Footer."""
        ov = data.get("overview", {})
        positions = data.get("positions", [])
        activities = data.get("activity", [])
        tokens = data.get("tokens", {})

        # 1. State properties
        self.kill_switch = bool(ov.get("kill_switch", False))
        self.system_paused = bool(ov.get("system_paused", False))
        self.auto_execute = bool(ov.get("auto_execute", False))
        self.daily_pnl = float(ov.get("daily_pnl", 0.0))
        self.daily_pnl_pct = ov.get("daily_pnl_pct")
        self.vix = ov.get("vix")

        # Track history for sparklines
        if len(self._pnl_history) >= 40:
            self._pnl_history.pop(0)
        self._pnl_history.append(self.daily_pnl)

        if self.vix is not None:
            if len(self._vix_history) >= 40:
                self._vix_history.pop(0)
            self._vix_history.append(float(self.vix))

        real_count = sum(1 for p in positions if p.get("type") == "REAL" or "mt5_ticket" in p)
        paper_count = sum(1 for p in positions if p.get("type") == "PAPER")
        self.real_count = real_count
        self.paper_count = paper_count

        # 2. Update Ticker Banner
        ticker = self.query_one("#ticker", LiveTickerBanner)
        ticker.update_status(
            real_count=real_count,
            paper_count=paper_count,
            daily_pnl=self.daily_pnl,
            pnl_pct=self.daily_pnl_pct,
            vix=self.vix,
            kill_switch=self.kill_switch,
            system_paused=self.system_paused,
            auto_execute=self.auto_execute,
            quotes=self._quotes,
            pnl_history=self._pnl_history,
            vix_history=self._vix_history,
        )

        # 3. Update Positions DataTable (differential to preserve scroll & cursor)
        table = self.query_one("#positions_table", DataTable)
        current_row_map = {(k.value if hasattr(k, "value") else str(k)): k for k in table.rows.keys()}
        new_keys = set(str(p.get("id", "N/A")) for p in positions)

        # Remove positions that have closed
        for old_id, row_key in list(current_row_map.items()):
            if old_id not in new_keys:
                try:
                    table.remove_row(row_key)
                except Exception:
                    pass

        col_keys = list(table.columns.keys())
        for p in positions:
            pos_id = str(p.get("id", "N/A"))
            pos_type = p.get("type", "REAL" if "mt5_ticket" in p else "PAPER")
            sym = str(p.get("symbol", "N/A"))
            direction = str(p.get("direction", "BUY")).upper()
            dir_styled = (
                f"[bold {BULL_PROFIT}]{direction}[/]" if direction == "BUY" else f"[bold {BEAR_LOSS}]{direction}[/]"
            )
            vol = f"{float(p.get('volume') or p.get('lots') or 0.01):.2f}"
            entry = f"{float(p.get('entry_price') or 0.0):.4f}"
            sl = (
                f"{float(p.get('sl') or p.get('stop_loss') or 0.0):.4f}" if (p.get("sl") or p.get("stop_loss")) else "-"
            )
            tp = (
                f"{float(p.get('tp') or p.get('take_profit') or 0.0):.4f}"
                if (p.get("tp") or p.get("take_profit"))
                else "-"
            )
            pnl_val = float(p.get("pnl") or 0.0)
            pnl_color = BULL_PROFIT if pnl_val >= 0 else BEAR_LOSS
            pnl_sign = "+" if pnl_val >= 0 else ""
            pnl_styled = f"[{pnl_color}]{pnl_sign}${pnl_val:,.2f}[/]"

            if getattr(self, "_positions_narrow_mode", False):
                row_vals = [sym, dir_styled, vol, entry, pnl_styled]
            else:
                row_vals = [pos_id, pos_type, sym, dir_styled, vol, entry, sl, tp, pnl_styled]
            if pos_id in current_row_map:
                r_key = current_row_map[pos_id]
                for c_idx, val in enumerate(row_vals):
                    if c_idx < len(col_keys):
                        try:
                            table.update_cell(r_key, col_keys[c_idx], val)
                        except Exception:
                            pass
            else:
                table.add_row(*row_vals, key=pos_id)

        # 4. Update Activity Feed (append only unseen)
        activity_log = self.query_one("#activity_log", RichLog)
        for act in activities:
            act_id = act.get("id") or act.get("timestamp") or str(act)
            if act_id not in self._seen_activity_ids:
                if len(self._seen_activity_ids) >= 2000:
                    self._seen_activity_ids = set(list(self._seen_activity_ids)[-1000:])
                self._seen_activity_ids.add(act_id)
                ts_str = act.get("timestamp", "")
                if ts_str and "T" in ts_str:
                    ts_fmt = ts_str.split("T")[1][:8]
                else:
                    ts_fmt = datetime.now().strftime("%H:%M:%S")

                cat = str(act.get("category", "system")).lower()
                desc = act.get("description") or act.get("message") or ""
                actor = act.get("actor", "agent")

                if cat in ("error", "critical"):
                    prefix = f"[bold {BEAR_LOSS}][ FAILED ][/]"
                elif cat in ("warn", "warning", "risk"):
                    prefix = f"[bold {BRASS}][ RISK ][/]"
                elif cat in ("trade", "trading", "order"):
                    prefix = f"[bold {BULL_PROFIT}][ EXECUTE ][/]"
                elif cat in ("analysis", "debate"):
                    prefix = f"[bold {PHOSPHOR_AMBER}][ ANALYSIS ][/]"
                else:
                    prefix = f"[dim {MUTED}][ SYSTEM ][/]"

                activity_log.write(f"[dim {MUTED}]{ts_fmt}[/] {prefix} [bold {PAPER}]{actor}:[/] {desc}")

        # 5. Update Status Bar
        self._cached_tokens = int(tokens.get("total_cached_tokens", 0) or 0)
        self._input_tokens = int(tokens.get("total_input_tokens", 0) or 0)
        self._output_tokens = int(tokens.get("total_output_tokens", 0) or 0)
        self._cost_usd = float(tokens.get("total_cost_usd", 0.0) or 0.0)

        # Cache efficiency
        self._cache_hit_rate = (
            min(100.0, max(0.0, self._cached_tokens / float(self._input_tokens) * 100.0))
            if self._input_tokens > 0
            else 0.0
        )
        self._context_used = self._input_tokens + self._output_tokens

        # Dynamic context window gauge (from ContextTracker)
        try:
            from monika.infrastructure.llm.context_tracker import get_context_tracker

            ctx_summary = tokens.get("context_tracker") or get_context_tracker().get_summary()
            if ctx_summary and ctx_summary.get("used_tokens", 0) > 0:
                self._context_used = int(ctx_summary["used_tokens"])
                self._context_max = int(ctx_summary["max_context_window"])
                self._cache_hit_rate = float(ctx_summary["cache_hit_rate"])
        except Exception:
            pass

        # 6. Update Performance Tab
        try:
            perf_data = data.get("performance", {})
            total_trades = perf_data.get("total_trades", ov.get("total_trades", 0))
            win_rate = float(perf_data.get("win_rate", ov.get("win_rate", 0.0)) or 0.0)
            pf = float(perf_data.get("profit_factor", ov.get("profit_factor", 0.0)) or 0.0)
            consec_losses = int(perf_data.get("consecutive_losses", 0) or 0)

            perf_table = self.query_one("#perf_table", DataTable)
            perf_table.clear()
            perf_table.add_rows(
                [
                    ("Total Trades", str(total_trades), "≥ 50 (Protocol Minimum)"),
                    ("Win Rate", f"{win_rate:.1f}%", "≥ 55.0%"),
                    ("Profit Factor", f"{pf:.2f}", "≥ 1.50"),
                    ("Max Daily Drawdown", f"{abs(self.daily_pnl_pct or 0.0):.1f}%", "≤ 3.0%"),
                    ("Max Consecutive Losses", f"{consec_losses} / 3", "≤ 3 (Circuit Breaker)"),
                ]
            )

            pnl_chart = (
                braille_sparkline(self._pnl_history, width=30) if self._pnl_history else "No PnL history recorded yet"
            )
            self.query_one("#perf_sparkline", Static).update(
                f"[bold cyan]Intraday PnL Trajectory:[/]\n{pnl_chart}\n\n"
                f"[bold white]Daily Realized PnL:[/] ${self.daily_pnl:,.2f}"
            )
        except Exception as perf_err:
            logger.debug(f"[TUI] Performance update error: {perf_err}")

        # 7. Update Signals DataTable
        try:
            sig_table = self.query_one("#signals_table", DataTable)
            sig_table.clear()
            for s in data.get("signals", []):
                side = str(s.get("direction", "HOLD")).upper()
                side_styled = (
                    f"[bold {BULL_PROFIT}]{side}[/]"
                    if side == "BUY"
                    else f"[bold {BEAR_LOSS}]{side}[/]"
                    if side == "SELL"
                    else f"[dim]{side}[/]"
                )
                conf_val = float(s.get("confidence") or 0.0)
                conf = f"{(conf_val * 100):.0f}%" if conf_val <= 1.0 else f"{conf_val:.0f}%"
                entry = f"{float(s.get('entry') or 0.0):.4f}" if s.get("entry") else "—"
                sl = f"{float(s.get('sl') or 0.0):.4f}" if s.get("sl") else "—"
                tp = f"{float(s.get('tp') or 0.0):.4f}" if s.get("tp") else "—"
                sig_table.add_row(
                    str(s.get("id", "")),
                    str(s.get("symbol", "")),
                    side_styled,
                    conf,
                    entry,
                    sl,
                    tp,
                    str(s.get("status", "")).upper(),
                    str(s.get("timestamp", "")),
                )
        except Exception as sig_err:
            logger.debug(f"[TUI] Signals update error: {sig_err}")

        # 8. Update Risk DataTable
        try:
            r_table = self.query_one("#risk_table", DataTable)
            r_table.clear()
            scorecard_raw = data.get("scorecard", [])
            items = []
            if isinstance(scorecard_raw, dict):
                checks_dict = scorecard_raw.get("checks", {})
                for c_name, c_val in checks_dict.items():
                    if isinstance(c_val, dict):
                        items.append(
                            {
                                "name": c_name,
                                "passed": c_val.get("passed", False),
                                "current_value": c_val.get("current_value", "OK" if c_val.get("passed") else "BREACH"),
                                "limit_value": c_val.get("limit_value", c_val.get("reason", "-")),
                            }
                        )
                    else:
                        items.append(
                            {
                                "name": c_name,
                                "passed": bool(c_val),
                                "current_value": "OK" if c_val else "FAIL",
                                "limit_value": "-",
                            }
                        )
            elif isinstance(scorecard_raw, (list, tuple)):
                items = list(scorecard_raw)

            if items:
                for item in items:
                    pass_val = item.get("passed", False)
                    status_styled = f"[bold {BULL_PROFIT}]PASS[/]" if pass_val else f"[bold {BEAR_LOSS}]FAIL[/]"
                    name = str(item.get("name", "Check")).replace("_", " ").title()
                    curr = str(item.get("current_value", "-"))
                    limit = str(item.get("limit_value", "-"))
                    r_table.add_row(name, curr, limit, status_styled)
            else:
                pnl_pct = abs(float(self.daily_pnl_pct or 0.0))
                dd_pass = pnl_pct < 3.0
                cb_pass = not self.system_paused
                ks_pass = not self.kill_switch
                for name, curr, limit, _ in DETERMINISTIC_RISK_CHECKS:
                    if "Daily Drawdown" in name:
                        curr = f"{pnl_pct:.2f}%"
                        st_styled = f"[bold {BULL_PROFIT}]PASS[/]" if dd_pass else f"[bold {BEAR_LOSS}]FAIL[/]"
                    elif "Trading Not Paused" in name:
                        curr = "Active" if cb_pass else "Paused"
                        st_styled = f"[bold {BULL_PROFIT}]PASS[/]" if cb_pass else f"[bold {BEAR_LOSS}]FAIL[/]"
                    elif "Kill Switch" in name:
                        curr = "Disarmed" if ks_pass else "HALTED"
                        st_styled = f"[bold {BULL_PROFIT}]PASS[/]" if ks_pass else f"[bold {BEAR_LOSS}]FAIL[/]"
                    else:
                        st_styled = f"[bold {BULL_PROFIT}]PASS[/]"
                    r_table.add_row(name, curr, limit, st_styled)
        except Exception as r_err:
            logger.debug(f"[TUI] Risk update error: {r_err}")

        # 9. Update Market Rates Table
        try:
            m_rates = self.query_one("#market_rates_table", DataTable)
            yields_info = data.get("yields", {})
            fg_info = data.get("fear_greed", {})
            if yields_info or fg_info:
                m_rates.clear()
                spread = yields_info.get("spread_2s10s")
                is_inv = yields_info.get("is_inverted", False)
                spread_txt = f"{spread:+.2f}%" if spread is not None else "+0.23%"
                curve_bias = (
                    f"[bold {BEAR_LOSS}]INVERTED (RECESSION)[/]" if is_inv else f"[bold {BULL_PROFIT}]NORMAL CURVE[/]"
                )

                fg_val = fg_info.get("current_value", 50)
                fg_cls = fg_info.get("classification", "Neutral")
                fg_style = (
                    f"[bold {BEAR_LOSS}]{fg_cls.upper()}[/]"
                    if fg_val <= 30
                    else f"[bold {BULL_PROFIT}]{fg_cls.upper()}[/]"
                    if fg_val >= 70
                    else f"[dim]{fg_cls.upper()}[/]"
                )

                m_rates.add_rows(
                    [
                        ("FOMC Target Rate", "5.25% - 5.50%", "Policy Stance", "[dim]HOLD / NEUTRAL[/]"),
                        ("US 2s10s Spread", spread_txt, "Recession Gauge", curve_bias),
                        ("Fear & Greed Index", f"{fg_val} / 100", "Market Sentiment", fg_style),
                    ]
                )
                for y in yields_info.get("treasury_yields", [])[:3]:
                    m_rates.add_row(
                        f"US Treasury {y.get('tenor')}",
                        f"{float(y.get('yield_percent', 0.0)):.2f}%",
                        "Yield Benchmark",
                        "[dim]BENCHMARK[/]",
                    )
        except Exception as m_err:
            logger.debug(f"[TUI] Market rates update error: {m_err}")

        # 10. Update Macro Calendar Table (#market_table)
        try:
            m_cal = self.query_one("#market_table", DataTable)
            cal_events = data.get("calendar", [])
            if cal_events:
                m_cal.clear()
                for ev in cal_events:
                    raw_time = str(ev.get("event_time", ""))
                    if "T" in raw_time:
                        time_display = raw_time.split("T")[1][:5] + " UTC"
                    else:
                        time_display = raw_time[:10] if raw_time else "—"
                    curr = str(ev.get("currency", "USD")).upper()
                    event_name = str(ev.get("event_name", "Macro Event"))
                    imp = str(ev.get("impact", "LOW")).upper()
                    if imp in ("HIGH", "RED"):
                        imp_styled = f"[bold {BEAR_LOSS}]HIGH[/]"
                    elif imp in ("MED", "MEDIUM", "ORANGE"):
                        imp_styled = f"[bold {BRASS}]MED[/]"
                    else:
                        imp_styled = f"[dim]LOW[/]"
                    fcast = str(ev.get("forecast") or "—")
                    act = str(ev.get("actual") or "—")
                    m_cal.add_row(time_display, curr, event_name, imp_styled, fcast, act)
        except Exception as cal_err:
            logger.debug(f"[TUI] Calendar table update error: {cal_err}")

        # Determine token budget degradation tier
        if self._cost_usd > 5.0:
            self._budget_tier = "T3 (CRIT 20%)"
        elif self._cost_usd > 3.0:
            self._budget_tier = "T2 (WARN 50%)"
        else:
            self._budget_tier = "T1 (FULL 100%)"

        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        try:
            uptime_secs = int(time.time() - self._start_time)
            status_bar = self.query_one("#status_bar", StatusBar)
            status_bar.update_metrics(
                cached_tokens=self._cached_tokens,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                cost_usd=self._cost_usd,
                uptime_seconds=uptime_secs,
                ws_status=self._ws_status,
                context_used=self._context_used,
                context_max=self._context_max,
                cache_hit_rate=self._cache_hit_rate,
                busy_status=self.busy_buffer.status_text,
                budget_tier=getattr(self, "_budget_tier", "T1 (100%)"),
                terminal_width=getattr(self, "terminal_width", 100),
            )
        except Exception:
            pass
