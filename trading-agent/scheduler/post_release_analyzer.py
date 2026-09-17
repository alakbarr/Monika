"""
PostReleaseAnalyzer: Event-driven re-analysis after economic data releases.

Solves the core design flaw: 19:00 WIB cycle clamps confidence (news within 2h),
19:30 WIB data releases with opportunity, system waits until next cycle = hours wasted.

This component:
1. Polls DB every 2 min for high-impact events with actual != null (last 30 min)
2. Waits 15 min for price settlement
3. Runs Stage 2 ONLY for affected symbols (NOT Stage 1)
4. Injects surprise context so LLM knows event already happened
5. Executes actionable trades immediately
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import utils.clock as clock

logger = logging.getLogger('TradingAgent.PostReleaseAnalyzer')

CURRENCY_TO_SYMBOLS = {
    'USD': ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XTIUSD', 'BTCUSD', 'XBRUSD'],
    'EUR': ['EURUSD'],
    'GBP': ['GBPUSD'],
    'JPY': ['USDJPY'],
    'AUD': ['AUDUSD'],
    'CAD': ['XTIUSD', 'XBRUSD'],
    'XAU': ['XAUUSD'],
    'XTI': ['XTIUSD', 'XBRUSD'],
    'XBR': ['XTIUSD', 'XBRUSD'],
    'BTC': ['BTCUSD'],
}


class PostReleaseAnalyzer:
    """
    Monitors economic calendar for freshly-released high-impact data
    and triggers immediate targeted Stage 2 re-analysis for affected symbols.

    Unlike NewsWatcher (pseudo-news -> classification -> re-analysis),
    this acts directly on calendar events with actual values,
    bypassing the classification pipeline entirely.
    """

    def __init__(
        self,
        settings: dict,
        per_asset_stage: Any = None,
        fundamental_stage: Any = None,
        execution_service: Any = None,
        mt5_client: Any = None,
        dry_run: bool = False,
    ):
        self.settings = settings
        self._per_asset = per_asset_stage
        self._fundamental = fundamental_stage
        self._exec_svc = execution_service
        self._mt5 = mt5_client
        self._dry_run = dry_run
        self._running = False
        self._stop_event = asyncio.Event()
        self._processed_events: set[int] = set()
        self._poll_seconds = 120  # Check every 2 min
        self._settle_seconds = 900  # 15 min settle delay
        self._max_reruns_per_day = 8
        self._today_reruns = 0
        self._today_date: Optional[str] = None

        universe = settings.get('trading', {}).get('asset_universe', [])
        self._universe = universe if universe else [
            'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY',
            'AUDUSD', 'XTIUSD', 'BTCUSD', 'XBRUSD'
        ]

    async def start(self):
        """Main loop — polls for released calendar events."""
        self._running = True
        logger.info(
            "[PostReleaseAnalyzer] Started — polling every %ds, "
            "settle delay %ds, max %d reruns/day",
            self._poll_seconds, self._settle_seconds, self._max_reruns_per_day
        )
        while self._running:
            try:
                await self._check_releases()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PostReleaseAnalyzer] Error in check loop: {e}")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_seconds)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        logger.info("[PostReleaseAnalyzer] Stopped")

    async def _check_releases(self):
        """Check for recently-released high-impact events and trigger re-analysis."""
        from database.db import get_session
        from database.models import EconomicCalendar
        from sqlalchemy import select

        now = clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        today_str = now.strftime('%Y-%m-%d')
        if self._today_date != today_str:
            self._today_date = today_str
            self._today_reruns = 0

        if self._today_reruns >= self._max_reruns_per_day:
            return

        # Find high-impact events released in last 30 minutes with actual data
        window_start = now - timedelta(minutes=30)

        async with get_session() as session:
            events = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact.in_(['high', 'High', 'HIGH']))
                .where(EconomicCalendar.actual.isnot(None))
                .where(EconomicCalendar.event_time >= window_start)
                .where(EconomicCalendar.event_time <= now)
            )).scalars().all()

        new_events = [e for e in events if e.id not in self._processed_events]
        if not new_events:
            return

        # Mark all as processed immediately to prevent re-triggering
        for event in new_events:
            self._processed_events.add(event.id)

        # Determine affected symbols (efficient: only affected currencies)
        affected_currencies = set()
        for event in new_events:
            if event.currency:
                affected_currencies.add(event.currency.upper())

        affected_symbols = []
        for curr in affected_currencies:
            for sym in CURRENCY_TO_SYMBOLS.get(curr, []):
                if sym in self._universe and sym not in affected_symbols:
                    affected_symbols.append(sym)

        if not affected_symbols:
            logger.debug(
                f"[PostReleaseAnalyzer] Events found but no matching symbols "
                f"for currencies: {affected_currencies}"
            )
            return

        event_names = ', '.join(str(e.event_name)[:40] for e in new_events[:3])
        logger.warning(
            f"[PostReleaseAnalyzer] {len(new_events)} high-impact release(s): "
            f"{event_names} | Currencies: {affected_currencies} | "
            f"Symbols: {affected_symbols}"
        )

        # Build surprise context for LLM
        surprise_context = self._build_surprise_context(new_events)

        # Wait for price settlement (15 min from event time)
        valid_times: list[datetime] = []
        for e in new_events:
            ev_time = getattr(e, 'event_time', None)
            if ev_time is not None:
                if ev_time.tzinfo is None:
                    valid_times.append(ev_time.replace(tzinfo=timezone.utc))
                else:
                    valid_times.append(ev_time)
        latest_event_time = max(valid_times) if valid_times else now
        target_analysis_time = latest_event_time + timedelta(seconds=self._settle_seconds)
        remaining_wait = (target_analysis_time - now).total_seconds()

        if remaining_wait > 0:
            logger.info(
                f"[PostReleaseAnalyzer] Waiting {remaining_wait:.0f}s "
                f"for price settlement (target: {target_analysis_time.strftime('%H:%M:%S UTC')})"
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=remaining_wait)
                return
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                return

        # Run targeted Stage 2 re-analysis (NOT Stage 1)
        await self._run_targeted_reanalysis(affected_symbols, surprise_context, new_events)
        self._today_reruns += 1

    def _build_surprise_context(self, events: list) -> str:
        """Build rich context about the data release for LLM injection."""
        lines = [
            "\n[POST-RELEASE ANALYSIS — ECONOMIC DATA JUST RELEASED]",
            "High-impact economic data has been released. Price has had time to settle.",
            "Analyze the ACTUAL data impact on affected pairs:\n",
        ]
        for e in events:
            line = f"• {e.event_name}: Actual = {e.actual}"
            if e.forecast:
                line += f" | Forecast = {e.forecast}"
            if e.previous:
                line += f" | Previous = {e.previous}"
            # Calculate surprise direction
            try:
                actual_str = str(e.actual).replace('%', '').replace(',', '').strip()
                forecast_str = str(e.forecast).replace('%', '').replace(',', '').strip()
                act_val = float(actual_str)
                fc_val = float(forecast_str)
                diff = act_val - fc_val
                direction = "ABOVE" if diff > 0 else "BELOW"
                magnitude = abs(diff)
                line += f" → [{direction} forecast by {magnitude:.2f}]"
            except (ValueError, TypeError, AttributeError):
                pass
            lines.append(line)

        lines.extend([
            "",
            "CRITICAL INSTRUCTIONS FOR POST-RELEASE ANALYSIS:",
            "1. The event has ALREADY occurred. Do NOT apply pre-event confidence penalty.",
            "2. The 15-minute price settlement window has passed. Analyze the ESTABLISHED reaction.",
            "3. Focus on: surprise magnitude, initial market reaction direction, continuation potential.",
            "4. If data clearly supports a directional move with good R:R, recommend BUY/SELL.",
            "5. Only WAIT if the reaction is ambiguous or price has already moved to exhaustion.",
        ])
        return '\n'.join(lines)

    async def _run_targeted_reanalysis(
        self, symbols: list[str], context: str, events: list
    ):
        """Execute Stage 2 analysis for affected symbols only."""
        if not self._per_asset:
            logger.warning("[PostReleaseAnalyzer] No PerAssetStage — cannot re-analyze")
            return

        from database.db import get_session as _gs

        try:
            # Per Option C: Refresh Stage 1 FundamentalBrief first ONLY if release is genuine Tier-1 (Rate decision, NFP, CPI)
            tier1_patterns = (
                "interest rate", "rate decision", "fomc", "federal funds", "ecb", "boe", "bank rate",
                "boj", "rba", "cash rate", "non-farm", "nonfarm", "nfp", "unemployment rate",
                "consumer price", "cpi", "hicp", "core pce"
            )
            is_tier1 = any(
                any(p in (getattr(e, "name", "") or getattr(e, "event", "") or "").lower() for p in tier1_patterns)
                for e in (events or [])
            )
            if is_tier1 and self._fundamental:
                try:
                    logger.info("[PostReleaseAnalyzer] Tier-1 catalyst detected. Refreshing Stage 1 FundamentalBrief before Stage 2...")
                    async with _gs() as f_session:
                        await self._fundamental.run(f_session, forced=True)
                    logger.info("[PostReleaseAnalyzer] Stage 1 refreshed successfully.")
                except Exception as fe:
                    logger.warning(f"[PostReleaseAnalyzer] Stage 1 refresh failed, proceeding with current brief: {fe}")

            pa_results = await self._per_asset.run_all(
                session_factory=_gs,
                symbols=symbols,  # Only affected symbols
                is_secondary=True,
                use_session_trigger_client=True,
                extra_context=context,
                skip_cooldown=True,
            )

            actionable = [
                (sym, r) for sym, r in pa_results.items()
                if r.get('decision') in ('buy', 'sell') and r.get('analysis_id')
            ]

            # Execute actionable trades safely via ReactiveStateGraph or auto_execute check
            if actionable:
                auto_execute = self.settings.get("trading", {}).get("auto_execute", False)
                if not auto_execute:
                    logger.info(
                        f"[PostReleaseAnalyzer] Found {len(actionable)} actionable trade(s) from post-release reanalysis, "
                        f"but auto_execute is disabled. Orders not placed."
                    )
                else:
                    # Route through LangGraph ReactiveStateGraph (CRITICAL-01 architecture mandate)
                    routed_via_graph = False
                    try:
                        from graph.reactive_graph import get_reactive_graph
                        reactive_graph = get_reactive_graph()
                        scheduler_ctx = getattr(self, "_cycle_scheduler", None) or self
                        reactive_state = {
                            "symbols": symbols,
                            "actionable_trades": actionable,
                            "event_type": "post_release_news",
                            "extra_context": f"Post-release analysis for {len(events)} economic events",
                            "event_data": {"source": "post_release_analyzer", "symbols": symbols},
                            "market_regime": "normal",
                            "summary": {},
                            "errors": [],
                            "should_pause": False,
                        }
                        config = {"configurable": {"scheduler": scheduler_ctx}}
                        logger.info("[PostReleaseAnalyzer] Routing actionable trades through LangGraph ReactiveStateGraph...")
                        await reactive_graph.ainvoke(reactive_state, config=config)
                        routed_via_graph = True
                    except Exception as g_err:
                        logger.error(f"[PostReleaseAnalyzer] LangGraph reactive execution failed: {g_err}", exc_info=True)

                    # Fallback to direct execution service only if graph routing failed and exec_svc available
                    if not routed_via_graph and self._exec_svc:
                        equity = None
                        try:
                            if self._mt5:
                                account = await self._mt5.get_account_info()
                                equity = account.get('equity') if account else None
                        except Exception:
                            pass

                        from database.models import AssetAnalysis
                        from sqlalchemy import select
                        for sym, r in actionable:
                            async with _gs() as session:
                                ana = (await session.execute(
                                    select(AssetAnalysis).where(
                                        AssetAnalysis.id == r['analysis_id']
                                    )
                                )).scalar_one_or_none()
                                if ana:
                                    try:
                                        await self._exec_svc.execute_analysis(session, ana, equity)
                                        logger.info(
                                            f"[PostReleaseAnalyzer] Direct execution fallback {sym}: {r['decision']}"
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"[PostReleaseAnalyzer] Execution failed {sym}: {e}"
                                        )

            # Log activity
            ev_names = ', '.join(str(e.event_name)[:30] for e in events[:3])
            logger.info(
                f"[PostReleaseAnalyzer] Complete. Events: {ev_names} | "
                f"Analyzed: {len(pa_results)} symbols | "
                f"Actionable: {len(actionable)} | "
                f"Today reruns: {self._today_reruns + 1}/{self._max_reruns_per_day}"
            )

            # Notify via Telegram if actionable
            if actionable:
                try:
                    from utils.infra.notifier import get_notifier
                    notifier = get_notifier()
                    trade_summary = ', '.join(f"{s}: {r['decision'].upper()}" for s, r in actionable)
                    await notifier.send(
                        f"📊 <b>Post-Release Trade Opportunity</b>\n"
                        f"Events: {ev_names}\n"
                        f"Trades: {trade_summary}"
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[PostReleaseAnalyzer] Re-analysis failed: {e}")

    def is_event_handled(self, event_id: int) -> bool:
        """Check if an event was already processed (for NewsWatcher dedup)."""
        return event_id in self._processed_events
