# ==============================================================================
# File: interfaces/cli/tui_app/mixins/websocket.py
# Description: Live WebSocket client & event handler mixin for Monika TUI
# ==============================================================================

import asyncio
import json
import logging
import time
from typing import Any, Dict

import aiohttp
from textual.widgets import RichLog

from monika.interfaces.cli.analysis_tree import AnalysisCycleTree
from monika.interfaces.cli.theme import BULL_PROFIT, PHOSPHOR_AMBER
from monika.interfaces.cli.tui_app.base import _TuiMixinBase
from monika.interfaces.cli.tui_app.widgets import LiveTickerBanner

logger = logging.getLogger("TradingAgent.TUI")


class WebSocketMixin(_TuiMixinBase):
    """Mixin handling live market WebSocket connection and event dispatching."""

    async def _websocket_worker(self) -> None:
        """Connect to /ws/live-feed and process real-time push events."""
        ws_url = self.api_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live-feed"
        if self.api_key:
            ws_url += f"?token={self.api_key}"

        while True:
            try:
                self._ws_status = "[WARNING] Connecting..."
                self._refresh_status_bar()

                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        self._ws_status = "[ACTIVE] Live (WS)"
                        self._refresh_status_bar()

                        activity_log = self.query_one("#activity_log", RichLog)
                        activity_log.write(f"[bold {BULL_PROFIT}][OK] WebSocket connected to live market stream.[/]")

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    event = json.loads(msg.data)
                                    await self._handle_ws_event(event)
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"[TUI WS] Connection error: {e}")
                self._ws_status = "[ERROR] Offline (Polling)"
                self._refresh_status_bar()
                await asyncio.sleep(3)

    async def _handle_ws_event(self, event: Dict[str, Any]) -> None:
        """Handle inbound live-feed WebSocket events."""
        etype = event.get("type", "")
        payload = event.get("payload", {})
        activity_log = self.query_one("#activity_log", RichLog)

        if etype == "tick":
            sym = payload.get("symbol")
            bid = payload.get("bid")
            if sym and bid is not None:
                self._quotes[sym] = float(bid)
                # Quick ticker update without full reload
                ticker = self.query_one("#ticker", LiveTickerBanner)
                ticker.update_status(
                    real_count=self.real_count,
                    paper_count=self.paper_count,
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

        elif etype in (
            "order_state_change",
            "position_closed",
            "cycle_triggered",
            "risk_override_updated",
            "config_updated",
        ):
            await self.refresh_data()

        elif etype == "trade_approved":
            sym = payload.get("symbol", "ASSET")
            vol = payload.get("volume", 0.0)
            act_id = f"ws_trade_{time.time()}"
            self._seen_activity_ids.add(act_id)
            activity_log.write(f"[bold {BULL_PROFIT}] Trade Approved:[/] {sym} {vol} lots.")
            await self.refresh_data()

        # -----------------------------------------------------------------------
        # Analysis Pipeline Events (Phase 3 Integration)
        # -----------------------------------------------------------------------
        elif etype == "analysis_cycle_start":
            cycle_id = str(payload.get("cycle_id", "active"))
            sym = str(payload.get("symbol", "PORTFOLIO"))
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.start_cycle(cycle_id, sym)
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[bold {PHOSPHOR_AMBER}]◉ ANALYSIS CYCLE #{cycle_id} INITIATED[/] — Symbol: {sym}")
            except Exception:
                pass

        elif etype == "analysis_step_start":
            step = str(payload.get("step", ""))
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.update_step(step, status="running")
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[cyan]▶ Executing Stage:[/] {step}...")
            except Exception:
                pass

            # Mid-stream steer delivery at step boundary (one-at-a-time per Q1)
            if self.busy_buffer.steer_queue:
                next_steer = self.busy_buffer.pop_steer()
                if next_steer:
                    await self._dispatch_steer(next_steer, mode="steer")
                    self._refresh_status_bar()

        elif etype == "analysis_step_complete":
            step = str(payload.get("step", ""))
            dur_s = float(payload.get("duration_s", 0.0))
            if not dur_s and payload.get("duration_ms"):
                dur_s = float(payload.get("duration_ms")) / 1000.0
            inp = int(payload.get("input_tokens", 0) or 0)
            out = int(payload.get("output_tokens", 0) or 0)
            tok_hist = payload.get("token_history")
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.update_step(
                    step,
                    status="completed",
                    duration_s=dur_s,
                    input_tokens=inp,
                    output_tokens=out,
                    token_history=tok_hist,
                )
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[green][OK] Stage Completed:[/] {step} ({dur_s:.1f}s, ↑{inp} ↓{out} tokens)")
            except Exception:
                pass

            # Mid-stream steer delivery at tool/stage boundary
            if self.busy_buffer.steer_queue:
                next_steer = self.busy_buffer.pop_steer()
                if next_steer:
                    await self._dispatch_steer(next_steer, mode="steer")
                    self._refresh_status_bar()

        elif etype == "analysis_cycle_complete":
            decision = str(payload.get("decision", "DONE"))
            details = str(payload.get("outcome_details", ""))
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.complete_cycle(decision=decision, outcome_details=details)
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[bold green] CYCLE COMPLETED:[/] Decision = [bold]{decision}[/] ({details})")
            except Exception:
                pass

            # Deliver queued follow-up messages now that cycle is idle
            if self.busy_buffer.followup_queue:
                while self.busy_buffer.followup_queue:
                    followup = self.busy_buffer.pop_followup()
                    if followup:
                        await self._dispatch_steer(followup, mode="follow_up")
                self._refresh_status_bar()
