import asyncio
import inspect
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Any

from graph.workflow import build_trading_graph
from graph.state import merge_dicts
from scheduler.cycle_scheduler import CycleScheduler
from database.db import get_session

logger = logging.getLogger("TradingAgent.GraphCycleScheduler")

class GraphCycleScheduler(CycleScheduler):
    """
    Pembungkus graf LangGraph agar kompatibel dengan sistem orchestrator (TradingAgent).
    Mewarisi semua helper methods dari CycleScheduler.
    """
    
    def __init__(
        self,
        settings: dict,
        mt5_client: Optional[Any] = None,
        fundamental_stage: Optional[Any] = None,
        per_asset_stage: Optional[Any] = None,
        dry_run: bool = False,
        recovery_event: Optional[asyncio.Event] = None,
        macro_data_scheduler: Optional[Any] = None,
        execution_service: Optional[Any] = None,
    ):
        super().__init__(
            settings,
            mt5_client,
            fundamental_stage,
            per_asset_stage,
            dry_run=dry_run,
            macro_data_scheduler=macro_data_scheduler,
        )
        self.execution_service = execution_service
        db_url = os.getenv('DATABASE_URL', '').replace('+asyncpg', '')
        self.graph = build_trading_graph(db_url=db_url)
        # IMP-8: Protect against concurrent graph state mutations
        self._cycle_lock = asyncio.Lock()
        self._checkpointer_ready = False
        # Recovery synchronization event received from TradingAgent orchestrator.
        # If omitted (standalone mode), defaults to ready immediately.
        self._recovery_complete_event = recovery_event or asyncio.Event()
        if recovery_event is None:
            self._recovery_complete_event.set()  # Default: ready (standalone/test mode)
        self._first_cycle_done = False  # Track whether initial cycle has completed
        self._session_trigger_running = False
        self.notifier: Optional[Any] = None

    def stop(self) -> None:
        """Stop scheduler and cleanly close checkpointer connection pool."""
        self._session_trigger_running = False
        super().stop()
        try:
            if hasattr(self.graph, 'checkpointer') and self.graph.checkpointer is not None:
                conn = getattr(self.graph.checkpointer, 'conn', None)
                if conn and hasattr(conn, 'close'):
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_running():
                            loop.create_task(conn.close())
                    except RuntimeError:
                        pass
        except Exception as e:
            logger.debug(f"Checkpointer pool close error (non-fatal): {e}")

    async def aclose(self) -> None:
        """Async teardown method to cleanly close checkpointer connection pool."""
        try:
            if hasattr(self.graph, 'checkpointer') and self.graph.checkpointer is not None:
                conn = getattr(self.graph.checkpointer, 'conn', None)
                if conn and hasattr(conn, 'close'):
                    if inspect.iscoroutinefunction(conn.close):
                        await conn.close()
                    else:
                        conn.close()
        except Exception as e:
            logger.debug(f"Checkpointer pool async close: {e}")

    async def _ensure_checkpointer_setup(self):
        """
        Ensure PostgreSQL checkpointer is initialized (must be called in async context).
        
        Applies 3x retry with exponential backoff before fallback to MemorySaver.
        Uses 60s timeout and validates DB connectivity before attempting setup.
        """
        if self._checkpointer_ready:
            return
        
        MAX_RETRIES = 3
        BASE_TIMEOUT = 60.0  # Increased from 30s
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if not (hasattr(self.graph, 'checkpointer') and 
                        self.graph.checkpointer is not None and 
                        getattr(self.graph.checkpointer, '_needs_setup', False)):
                    # Tidak ada checkpointer yang perlu di-setup (sudah MemorySaver atau sudah ready)
                    self._checkpointer_ready = True
                    return
                
                logger.info(f'LangGraph: Setting up PostgreSQL checkpointer (attempt {attempt}/{MAX_RETRIES}, timeout={BASE_TIMEOUT}s)...')
                
                if hasattr(self.graph.checkpointer, 'conn') and hasattr(self.graph.checkpointer.conn, 'open'):
                    await self.graph.checkpointer.conn.open()

                await asyncio.wait_for(
                    self.graph.checkpointer.setup(),
                    timeout=BASE_TIMEOUT
                )
                self.graph.checkpointer._needs_setup = False
                self._checkpointer_ready = True
                logger.info(f'LangGraph: PostgreSQL checkpointer setup complete (attempt {attempt})')
                return  # Success
                
            except asyncio.TimeoutError:
                logger.warning(
                    f'PostgreSQL checkpointer setup timed out on attempt {attempt}/{MAX_RETRIES} '
                    f'(timeout={BASE_TIMEOUT}s).'
                )
                cp = getattr(self.graph, 'checkpointer', None)
                if cp is not None:
                    conn = getattr(cp, 'conn', None)
                    if conn is not None and hasattr(conn, 'close'):
                        try:
                            await conn.close()
                        except Exception:
                            pass
                if attempt < MAX_RETRIES:
                    backoff = 5 * attempt  # 5s, 10s, 15s
                    logger.info(f'Retrying in {backoff}s...')
                    await asyncio.sleep(backoff)
                    
            except Exception as e:
                logger.warning(
                    f'PostgreSQL checkpointer setup error on attempt {attempt}/{MAX_RETRIES}: {e}'
                )
                cp = getattr(self.graph, 'checkpointer', None)
                if cp is not None:
                    conn = getattr(cp, 'conn', None)
                    if conn is not None and hasattr(conn, 'close'):
                        try:
                            await conn.close()
                        except Exception:
                            pass
                if attempt < MAX_RETRIES:
                    backoff = 5 * attempt
                    logger.info(f'Retrying in {backoff}s...')
                    await asyncio.sleep(backoff)
        
        # Semua retry gagal — tutup conn sisa dan fallback ke MemorySaver
        cp = getattr(self.graph, 'checkpointer', None)
        if cp is not None:
            conn = getattr(cp, 'conn', None)
            if conn is not None and hasattr(conn, 'close'):
                try:
                    await conn.close()
                except Exception:
                    pass
        logger.critical(
            f'PostgreSQL checkpointer failed after {MAX_RETRIES} attempts. '
            f'Falling back to MemorySaver (state will NOT persist across restarts). '
            f'Check DB connectivity and verify DATABASE_URL environment variable.'
        )
        if hasattr(self, 'notifier') and self.notifier:
            try:
                await self.notifier.send_alert(
                    f"⚠️ CRITICAL: Graph state persistence unavailable. MemorySaver fallback active. "
                    f"State will be LOST on restart."
                )
            except Exception:
                pass
        try:
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore
            self.graph.checkpointer = MemorySaver()
        except ImportError:
            pass
        self._checkpointer_ready = True
        
        # Kirim alert Telegram agar operator tahu state persistence terdegradasi
        try:
            from utils.infra.notifier import AgentNotifier
            await AgentNotifier().send_warning(
                '⚠️ <b>LangGraph: PostgreSQL Checkpointer Gagal</b>\n\n'
                f'Setup gagal setelah {MAX_RETRIES} percobaan.\n'
                'Fallback ke MemorySaver - state tidak persisten antar restart.\n\n'
                'Periksa koneksi DB dan variabel DATABASE_URL.'
            )
        except Exception:
            pass  # Non-fatal


    async def _update_adaptive_thresholds_realtime(self, session, closed_trades: list) -> None:
        """
        Update adaptive confluence thresholds in real-time after each trade closure.
        This implements the Proof-or-Stop loop: if recent trades fail, immediately
        raise the threshold without waiting for the weekly performance review.
        """
        try:
            from database.models import PaperTradeRecord, SystemConfig
            from sqlalchemy import select
            import json

            now_utc = datetime.now(timezone.utc)
            # 48-hour time-decay reset on existing adaptive thresholds
            existing_threshold_rows = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.like('adaptive_threshold_%'))
            )).scalars().all()

            for row in existing_threshold_rows:
                try:
                    data = json.loads(row.value)
                    set_at_str = data.get("set_at")
                    if set_at_str:
                        set_at = datetime.fromisoformat(set_at_str)
                        if set_at.tzinfo is None:
                            set_at = set_at.replace(tzinfo=timezone.utc)
                        if (now_utc - set_at).total_seconds() > 48 * 3600:
                            if data.get("adjustment", 0) > 0:
                                data["adjustment"] = 0
                                data["decayed_at"] = now_utc.isoformat()
                                data["reason"] = "48h_time_decay_reset"
                                row.value = json.dumps(data)
                                logger.info(f"[RealTimeThreshold] {row.key}: 48h decay expired, reset adjustment to 0")
                except Exception as decay_err:
                    logger.debug(f"Error checking threshold decay for {row.key}: {decay_err}")
            
            # Get last 30 closed trades
            recent_records = (await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.status == 'closed')
                .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
                .order_by(PaperTradeRecord.closed_at.desc())
                .limit(30)
            )).scalars().all()
            
            # Group by symbol
            by_symbol = {}
            for r in recent_records:
                if r.symbol not in by_symbol:
                    by_symbol[r.symbol] = []
                by_symbol[r.symbol].append(r)
            
            for symbol, trades in by_symbol.items():
                if len(trades) < 5:
                    continue
                    
                wins = sum(1 for t in trades if t.exit_reason == 'tp_hit')
                recent_wr = wins / len(trades) * 100
                
                # Determine adjustment
                key = f'adaptive_threshold_{symbol}'
                adjustment = 0
                if recent_wr < 30 and len(trades) >= 8:
                    adjustment = 3  # Severe: raise by 3
                elif recent_wr < 38 and len(trades) >= 5:
                    adjustment = 2  # Poor: raise by 2
                elif recent_wr < 45 and len(trades) >= 5:
                    adjustment = 1  # Below average: raise by 1
                elif recent_wr >= 55 and len(trades) >= 10:
                    adjustment = 0  # Good: reset to standard
                else:
                    # Don't change existing threshold
                    continue
                    
                adj_data = json.dumps({
                    'adjustment': adjustment,
                    'set_at': datetime.now(timezone.utc).isoformat(),
                    'recent_wr': recent_wr,
                    'trades_analyzed': len(trades),
                    'reason': f'realtime_update_wr_{recent_wr:.0f}pct'
                })
                
                existing = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == key)
                )).scalar_one_or_none()
                
                if existing:
                    existing.value = adj_data
                else:
                    session.add(SystemConfig(key=key, value=adj_data))
                    
                if adjustment > 0:
                    logger.warning(
                        f'[RealTimeThreshold] {symbol}: WR={recent_wr:.0f}% → '
                        f'threshold +{adjustment} (effective: {7 + adjustment}/14)'
                    )
            
            await session.commit()
        except Exception as e:
            logger.debug(f'Real-time threshold update failed (non-fatal): {e}')

    @staticmethod
    def _get_session_open_utc(tz_name: str, open_hour: int, open_minute: int = 0) -> datetime:
        """Calculate today's session open in UTC, strictly DST-aware."""
        from utils.scheduling.wall_clock import get_tzinfo
        now_utc = datetime.now(timezone.utc)
        tz = get_tzinfo(tz_name)
        local_now = now_utc.astimezone(tz)
        local_open = local_now.replace(
            hour=open_hour, minute=open_minute, second=0, microsecond=0
        )
        return local_open.astimezone(timezone.utc)

    @staticmethod
    def _is_near_open(now_utc: datetime, open_utc: datetime,
                      before_min: int = 15, after_min: int = 15) -> bool:
        """Check if now_utc is within [open - before_min, open + after_min]."""
        delta_seconds = (now_utc - open_utc).total_seconds()
        return (-before_min * 60) <= delta_seconds <= (after_min * 60)

    async def _should_run_session_trigger(self) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        
        if weekday >= 5:
            return False, 'weekend'
        
        # DST-aware session open window calculation
        tokyo_open = self._get_session_open_utc('Asia/Tokyo', 9, 0)
        london_open = self._get_session_open_utc('Europe/London', 8, 0)
        ny_open = self._get_session_open_utc('America/New_York', 9, 30)

        is_asian_open = self._is_near_open(now, tokyo_open)
        is_london_open = self._is_near_open(now, london_open)
        is_ny_open = self._is_near_open(now, ny_open)
        
        if not (is_asian_open or is_london_open or is_ny_open):
            return False, 'not_session_open'
        
        session_name = ('asian_open' if is_asian_open
                        else 'london_open' if is_london_open
                        else 'ny_open')
        
        from database.db import get_session
        from database.models import SystemConfig, FundamentalBrief
        from sqlalchemy import select
        today = now.strftime('%Y-%m-%d')
        key = f'session_trigger_{session_name}_{today}'
        
        async with get_session() as session:
            existing = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == key)
            )).scalar_one_or_none()
            
            if existing:
                return False, f'{session_name}_already_triggered_today'
            
            brief = (await session.execute(
                select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
            )).scalar_one_or_none()
            
            if not brief:
                return False, 'no_brief_available'
            
            brief_age = (now - brief.generated_at.replace(tzinfo=timezone.utc if brief.generated_at.tzinfo is None else brief.generated_at.tzinfo)).total_seconds() / 3600
            
            # FIX 4.16: Relaxed to 9.0h to provide buffer for 8-hour cycle scheduling jitter
            if brief_age > 9.0:
                return False, f'brief_too_old_{brief_age:.1f}h'
        
        return True, session_name

    async def run_session_trigger(self) -> dict:
        should_run, reason = await self._should_run_session_trigger()
        if not should_run:
            return {'status': 'skipped', 'reason': reason}
        
        async with self._cycle_lock:
            logger.info(f'[SessionTrigger] Running Stage 2-only analysis for {reason}')
            
            from agent.turn_lease_manager import SymbolTurnLeaseManager
            lease_mgr = SymbolTurnLeaseManager.get_instance()
            session_holder_id = f"session_trigger_{reason}_{int(datetime.now(timezone.utc).timestamp())}"
            leased_symbols = []
            for sym in self.asset_universe:
                if await lease_mgr.acquire_lease(sym, holder_id=session_holder_id, ttl_seconds=300.0):
                    leased_symbols.append(sym)

            from database.db import get_session as _gs
            try:
                pa_results = await self._per_asset.run_all(
                    session_factory=_gs,
                    symbols=self.asset_universe,
                    is_secondary=True,
                    use_session_trigger_client=True,
                    extra_context=(
                        f'\n[SESSION TRIGGER: {reason.upper().replace("_", " ")}] '
                        f'This analysis is specifically timed for {reason.replace("_", " ")}. '
                        f'The current session is the PRIMARY execution window. '
                        f'Only submit BUY/SELL if setup is clear and executable NOW.\n'
                    )
                )
                
                actionable = [
                    (sym, r) for sym, r in pa_results.items()
                    if r.get('decision') in ('buy', 'sell') and r.get('analysis_id')
                ]
                
                if actionable:
                    logger.info(f"[SessionTrigger] Found {len(actionable)} actionable trade(s). Routing through LangGraph ReactiveStateGraph...")
                    try:
                        from graph.reactive_graph import get_reactive_graph
                        reactive_graph = get_reactive_graph()
                        reactive_state = {
                            "symbols": list(self.asset_universe),
                            "actionable_trades": actionable,
                            "event_type": "session_trigger",
                            "extra_context": f"Session trigger for {reason}",
                            "event_data": {"session_trigger": reason, "symbols": list(self.asset_universe)},
                            "market_regime": "normal",
                            "summary": {},
                            "errors": [],
                            "should_pause": False,
                        }
                        config = {"configurable": {"scheduler": self}}
                        await reactive_graph.ainvoke(reactive_state, config=config)
                    except Exception as e:
                        logger.error(f"[SessionTrigger] Reactive graph execution failed: {e}", exc_info=True)
                
                # Persist marker after successful execution
                now = datetime.now(timezone.utc)
                today = now.strftime('%Y-%m-%d')
                key = f'session_trigger_{reason}_{today}'
                async with _gs() as session:
                    from database.models import SystemConfig
                    await SystemConfig.upsert(session, key=key, value=now.isoformat())
                    await session.commit()
                
                return {'status': 'executed', 'session': reason, 'assets_analyzed': len(pa_results), 'actionable': len(actionable)}
            except Exception as e:
                logger.error(f'[SessionTrigger] Failed: {e}')
                return {'status': 'error', 'reason': str(e)}
            finally:
                for sym in leased_symbols:
                    await lease_mgr.release_lease(sym, holder_id=session_holder_id)

    async def run_session_trigger_loop(self) -> None:
        self._session_trigger_running = True
        logger.info("[SessionTrigger] Loop started.")
        while self._session_trigger_running:
            try:
                trigger_result = await self.run_session_trigger()
                if trigger_result.get('status') == 'executed':
                    logger.info(f"Session trigger completed: {trigger_result}")
            except Exception as e:
                logger.error(f"Error in session trigger loop: {e}")
            for _ in range(60):
                if not self._session_trigger_running:
                    break
                await asyncio.sleep(1)

    async def run_once(self, forced: bool = False) -> dict:
        await self._ensure_checkpointer_setup()
        
        # Await post-restart recovery completion before initiating initial non-forced cycle.
        # Verified prior to checking locked() to prevent reentrancy race conditions.
        if not self._first_cycle_done and not forced:
            if not self._recovery_complete_event.is_set():
                logger.info('[GraphCycleScheduler] Waiting for post-restart recovery to complete before first cycle...')
                try:
                    await asyncio.wait_for(
                        self._recovery_complete_event.wait(),
                        timeout=180.0  # Max 3 menit tunggu recovery
                    )
                    logger.info('[GraphCycleScheduler] Recovery complete. Proceeding with first cycle.')
                except asyncio.TimeoutError:
                    logger.warning('[GraphCycleScheduler] Recovery wait timed out (180s). Proceeding anyway.')
            self._first_cycle_done = True

        # IMP-8: Ensure only one cycle runs at a time
        if self._cycle_lock.locked():
            logger.warning("Graph cycle already running — skipping concurrent invocation")
            return {"status": "skipped", "reason": "cycle_already_running"}
        
        async with self._cycle_lock:
            start = datetime.now(timezone.utc)
            
            # Shared pre-cycle setup dari parent class
            setup = await self._pre_cycle_setup(forced)
            if setup['should_skip']:
                logger.warning(f"[GraphCycleScheduler] Analysis cycle SKIPPED. Reason: {setup.get('skip_reason', 'unknown')}")
                return {'status': 'skipped', 'reason': setup['skip_reason'], 
                        'started_at': start.isoformat()}
            
            weekend_symbols_override = setup['weekend_symbols_override']
            
            # Update effective auto_execute ke settings
            if setup['effective_auto_execute'] != self.settings.get('trading', {}).get('auto_execute', False):
                self.settings = dict(self.settings)
                self.settings['trading'] = dict(self.settings.get('trading', {}))
                self.settings['trading']['auto_execute'] = setup['effective_auto_execute']
            
            # Weekend position handling (existing)
            if not forced:
                await self._handle_weekend_positions()
                

            # TAMBAHKAN: Ground truth update
            try:
                await self._update_analysis_ground_truth()
            except Exception as e:
                logger.debug(f'Ground truth update failed (non-fatal): {e}')
            
            # TAMBAHKAN: Edge tracking
            try:
                from utils.analytics.edge_tracker import compute_edge_status
                async with get_session() as session:
                    edge_data = await compute_edge_status(session)
                    if edge_data.get('status') == 'no_edge' and edge_data.get('total_trades', 0) >= 50:
                        logger.critical(f"EDGE DETECTION: System shows NO statistical edge after {edge_data['total_trades']} trades. Win rate: {edge_data['win_rate']}%")
                        try:
                            from utils.infra.notifier import AgentNotifier
                            await AgentNotifier().send_critical(
                                f"🚨 <b>EDGE DETECTION ALERT</b>\nNo statistical edge after {edge_data['total_trades']} trades\n"
                                f"Win Rate: {edge_data['win_rate']}% (need >{edge_data['breakeven_win_rate_pct']}%)\n"
                                f"95% CI: [{edge_data['ci_lower']}% - {edge_data['ci_upper']}%]\n\n{edge_data['action']}"
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f'Edge tracking failed (non-fatal): {e}')
                
            # Quick pattern summary setiap 12 jam
            if not hasattr(self, '_last_pattern_check'):
                self._last_pattern_check = datetime.now(timezone.utc)
            
            hours_since_pattern_check = (
                datetime.now(timezone.utc) - self._last_pattern_check
            ).total_seconds() / 3600
            
            if hours_since_pattern_check >= 12:
                self._last_pattern_check = datetime.now(timezone.utc)
                try:
                    from utils.analytics.trade_autopsy import summarize_recent_patterns
                    async with get_session() as session:
                        pattern_summary = await summarize_recent_patterns(session, hours_back=24)
                        if pattern_summary.get('has_critical_patterns'):
                            logger.warning(f'Critical patterns detected in last 24h: {pattern_summary}')
                            from utils.infra.notifier import AgentNotifier
                            await AgentNotifier().send_warning(
                                f'📊 <b>Pattern Alert (24h)</b>\n{pattern_summary.get("summary", "")}'
                            )
                except Exception as e:
                    logger.debug(f'Pattern summary check failed: {e}')
                    
            # ============================================================
                    
            logger.info(f"=== Graph Analysis Cycle Started at {start.strftime('%Y-%m-%d %H:%M UTC')} ===")
            
            summary = {
                "started_at": start.isoformat(),
                "scraping": {}, "price_fetch": {}, "indicators": {}, "structure": {}, 
                "data_refresh": {}, "fundamental": {}, "per_asset": {},
            }
            
            # --- GRAPH EXECUTION ---
            cycle_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
            from agent.turn_lease_manager import SymbolTurnLeaseManager
            lease_mgr = SymbolTurnLeaseManager.get_instance()
            cycle_holder_id = f"cycle_{cycle_id}"
            leased_symbols = []
            for sym in self.asset_universe:
                if await lease_mgr.acquire_lease(sym, holder_id=cycle_holder_id, ttl_seconds=1800.0):
                    leased_symbols.append(sym)

            config = {
                "configurable": {
                    "scheduler": self,
                    "forced": forced,
                    "thread_id": cycle_id  # Unique per cycle untuk checkpointing
                }
            }
            try:
                from analysis.event_broadcaster import emit_analysis_event
                emit_analysis_event("analysis_cycle_start", {
                    "cycle_id": cycle_id,
                    "symbol": "PORTFOLIO",
                    "symbols": self.asset_universe,
                    "forced": forced,
                })
                from utils.llm.context_tracker import get_context_tracker
                get_context_tracker().reset(cycle_id=cycle_id)
            except Exception as e:
                logger.debug(f"Failed emitting analysis_cycle_start: {e}")

            try:
                from database.event_store import TradingEventStore
                async with get_session() as start_session:
                    await TradingEventStore.emit(
                        session=start_session,
                        event_type="cycle.started",
                        payload={"cycle_id": cycle_id, "forced": forced, "symbols": self.asset_universe},
                        correlation_id=cycle_id,
                        actor="graph_cycle_scheduler",
                    )
            except Exception:
                pass
            
            # Load prior cycle insights dari DB
            prior_insights = {}
            try:
                async with get_session() as session:
                    from database.models import SystemConfig
                    from sqlalchemy import select
                    import json
                    cfg = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == 'prior_cycle_state')
                    )).scalar_one_or_none()
                    if cfg and cfg.value:
                        prior_insights = json.loads(cfg.value)
                        logger.info(
                            f'Loaded prior cycle state: consecutive_wait={prior_insights.get("consecutive_wait_count", 0)}'
                        )
            except Exception as e:
                logger.warning(f'Failed to load prior cycle state: {e}')

            from utils.validation.data_validator import is_forex_market_closed, is_crypto_symbol
            weekend_symbols_override = None
            if is_forex_market_closed(start):
                weekend_symbols_override = [s for s in self.asset_universe if is_crypto_symbol(s)]
                logger.info(f"[Graph] Forex market closed for weekend. Restricting symbols to crypto 24/7: {weekend_symbols_override}")
                
            state = {
                "symbols": self.asset_universe,
                "market_regime": "unknown",
                "vix_level": None,
                "brief_confidence": None,
                "asset_analyses": {},
                "debate_states": {},
                "risk_debate_states": {},
                "investment_verdicts": {},
                "portfolio_decisions": {},
                "approved_trades": [],
                "errors": [],
                "node_errors": {},
                "data_quality_scores": {},
                "cycle_id": cycle_id,
                "fundamental_retry_count": 0,
                "should_pause": False,
                "weekend_symbols_override": weekend_symbols_override,
                "stale_assets": [],
                "summary": summary,
                "actionable_trades": [],
                "reflection_applied": False,
                'prior_cycle_insights': prior_insights,
                'consecutive_wait_count': prior_insights.get('consecutive_wait_count', 0),
                'last_buy_sell_cycle': prior_insights.get('last_buy_sell_cycle'),
                "ssvp_per_symbol_contexts": {},
                "ssvp_cds_score": None,
                "ssvp_blocked": False,
                "ssvp_reconciliation_context": None,
                "context_snapshot_id": None,
                "ssvp_retry_count": 0,
                "user_market_intel": [],
                "refinement_count": 0,
                "rejection_feedback": None,
                "is_negotiable_rejection": False,
            }
            
            # Stream the graph execution with distributed cycle_span
            final_state = dict(state)
            try:
                from logging_observability.tracing.spans import cycle_span
                with cycle_span(cycle_id, symbols=self.asset_universe):
                    async for event in self.graph.astream(state, config=config):
                        if not isinstance(event, dict):
                            continue
                        for node_name, node_output in event.items():
                            logger.info(f"[Graph] Node '{node_name}' completed")
                            if not isinstance(node_output, dict):
                                continue
                            # Merge node output ke final_state via deep recursive merge
                            for k, v in node_output.items():
                                if isinstance(v, dict) and isinstance(final_state.get(k), dict):
                                    final_state[k] = merge_dicts(final_state[k], v)
                                elif k == 'errors' and isinstance(v, list):
                                    existing = final_state.get('errors', [])
                                    final_state[k] = list(dict.fromkeys(existing + v))
                                elif isinstance(v, list) and k in ('stale_assets', 'user_market_intel'):
                                    existing = final_state.get(k, [])
                                    final_state[k] = existing + [x for x in v if x not in existing]
                                else:
                                    final_state[k] = v
                                    
                            if node_output.get('should_pause'):
                                logger.warning(f"Graph paused at '{node_name}'")
            except Exception as e:
                logger.error(f"Graph execution failed: {e}")
                final_state['errors'] = final_state.get('errors', []) + [str(e)]
                
            # FIX-INF-01: Tambah SSVP CDS monitoring alert jika konsisten tinggi
            try:
                pa_results = final_state.get('asset_analyses', {})
                if pa_results:
                    high_cds_symbols = [
                        sym for sym, r in pa_results.items() 
                        if r.get('decision') == 'wait' and 'SSVP' in (r.get('rationale', '') or '')
                    ]
                    if len(high_cds_symbols) >= 3:
                        logger.warning(
                            f'[SSVP] {len(high_cds_symbols)} symbols WAIT due to SSVP this cycle: {high_cds_symbols}. '
                            f'Consider running Stage 1 re-analysis if this persists.'
                        )
            except Exception:
                pass
                
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            final_state['summary']['elapsed_total_s'] = elapsed

            try:
                from analysis.event_broadcaster import emit_analysis_event
                appr = final_state.get('approved_trades', [])
                if appr:
                    dec_list = [f"{t.get('symbol')} {t.get('direction')}" for t in appr if isinstance(t, dict)]
                    dec_str = ", ".join(dec_list) if dec_list else "APPROVED"
                else:
                    dec_str = "WAIT" if not final_state.get('errors') else "ERROR"
                emit_analysis_event("analysis_cycle_complete", {
                    "cycle_id": cycle_id,
                    "decision": dec_str,
                    "outcome_details": f"{len(appr)} trade(s) approved, {len(final_state.get('errors', []))} error(s)",
                    "elapsed_s": elapsed,
                })
            except Exception as e:
                logger.debug(f"Failed emitting analysis_cycle_complete: {e}")
            
            # Ensure API Cost and token logs are persisted even if execution_node was bypassed (e.g. non-actionable cycle)
            summary_data = final_state.get('summary', {})
            if summary_data.get('api_cost_usd') is None:
                try:
                    from utils.analytics.cost_tracker import CostTracker
                    stage1_in = summary_data.get("fundamental", {}).get("input_tokens", 0)
                    stage1_out = summary_data.get("fundamental", {}).get("output_tokens", 0)
                    stage2_in = sum(r.get("input_tokens", 0) for r in summary_data.get("per_asset", {}).values() if isinstance(r, dict))
                    stage2_out = sum(r.get("output_tokens", 0) for r in summary_data.get("per_asset", {}).values() if isinstance(r, dict))
                    cycle_id_val = final_state.get("cycle_id") or summary_data.get("cycle_id")
                    async with get_session() as cost_session:
                        cost_usd = await CostTracker.log_cycle_cost(
                            cost_session, stage1_in, stage1_out, stage2_in, stage2_out, settings=self.settings, cycle_id=cycle_id_val
                        )
                        summary_data["api_cost_usd"] = cost_usd
                except Exception as cost_err:
                    logger.debug(f"Post-cycle cost tracking fallback failed: {cost_err}")

            await self._log_summary(final_state.get('summary', {}))
            
            try:
                async with get_session() as session:
                    await self._check_system_health_trend(session)
                    
                    # Task 1.3: Confidence Calibration Check
                    from utils.calibration.confidence_calibrator import compute_confidence_calibration
                    calibration = await compute_confidence_calibration(session)
                    if not calibration.get('confidence_is_calibrated') and calibration.get('total_analyzed', 0) >= 30:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_warning(
                            f'⚠️ <b>Confidence Calibration Issue</b>\n'
                            f'Higher confidence scores do NOT reliably predict higher win rates.\n'
                            f'{calibration.get("recommendation", "")}'
                        )
            except Exception as e:
                logger.debug(f'Health trend check failed (non-fatal): {e}')
            
            # Track cost & cleanup
            # DB Cleanup (using correct import)
            try:
                from database.cleanup import cleanup_old_data
                async with get_session() as session:
                    await cleanup_old_data(session, settings=self.settings)
                logger.debug('Post-cycle DB cleanup completed')
            except Exception as e:
                logger.error(f'Post-cycle DB cleanup failed: {e}')
            
            # Cost projection check (cost tracking itself sudah dilakukan di execution_node.py)
            try:
                from utils.analytics.cost_tracker import CostTracker
                async with get_session() as session:
                    rolling = await CostTracker.get_rolling_7day_cost(session)
                    from config.settings import DEFAULT_MONTHLY_BUDGET_USD
                    monthly_budget = self.settings.get('cost_tracking', {}).get('monthly_budget_usd', DEFAULT_MONTHLY_BUDGET_USD)
                    if rolling['projected_monthly'] > monthly_budget * 0.9:
                        logger.warning(
                            f"Cost projection: ${rolling['projected_monthly']:.2f}/month "
                            f"(budget: ${monthly_budget:.2f})"
                        )
            except Exception as e:
                logger.debug(f'Cost projection check failed (non-fatal): {e}')
                
            # Simpan cycle performance metrics
            try:
                from database.models import CyclePerformance
                async with get_session() as perf_session:
                    summary_data = final_state.get('summary', {})
                    pa_results = summary_data.get('per_asset', {})
                    
                    decisions = {'buy': 0, 'sell': 0, 'wait': 0, 'avoid': 0}
                    skipped_symbols_info = []
                    error_symbols_info = []
                    
                    for sym, r in pa_results.items():
                        if isinstance(r, dict):
                            d = r.get('decision', 'wait')
                            if d in decisions:
                                decisions[d] += 1
                            elif d == 'skip':
                                reason = (
                                    'cooldown' if r.get('skipped_by_cooldown')
                                    else 'prescreen' if r.get('skipped_by_prescreen')
                                    else 'data_quality' if r.get('skipped_by_data_quality')
                                    else 'weekend_guard' if r.get('skipped_by_weekend_guard')
                                    else 'brief_staleness' if r.get('skipped_by_brief_staleness')
                                    else 'no_brief' if r.get('skipped_no_brief')
                                    else 'unknown'
                                )
                                skipped_symbols_info.append(f"{sym}({reason})")
                            elif d == 'error':
                                error_symbols_info.append(f"{sym}({r.get('error', 'unknown')[:20]})")
                    
                    stage1_data = summary_data.get('fundamental', {})
                    
                    # Calculate total stage2 tokens
                    stage2_in = sum(r.get('input_tokens', 0) 
                                   for r in pa_results.values() if isinstance(r, dict))
                    stage2_out = sum(r.get('output_tokens', 0) 
                                    for r in pa_results.values() if isinstance(r, dict))
                    
                    actionable = final_state.get('actionable_trades', [])
                    
                    api_cost_val = summary_data.get('api_cost_usd')
                    if api_cost_val is None:
                        api_cost_val = 0.0
                    
                    def _is_skipped(res: dict) -> bool:
                        return bool(
                            res.get('skipped_by_cooldown')
                            or res.get('skipped_by_prescreen')
                            or res.get('skipped_by_data_quality')
                            or res.get('skipped_by_weekend_guard')
                            or res.get('skipped_by_brief_staleness')
                            or res.get('skipped_no_brief')
                            or res.get('decision') == 'skip'
                        )
                        
                    cycle_record = CyclePerformance(
                        cycle_at=start,
                        elapsed_seconds=elapsed,
                        stage1_success=stage1_data.get('success', False),
                        stage1_tokens_in=stage1_data.get('input_tokens', 0),
                        stage1_tokens_out=stage1_data.get('output_tokens', 0),
                        assets_analyzed=sum(1 for r in pa_results.values() 
                                          if isinstance(r, dict) and not _is_skipped(r)),
                        assets_skipped=sum(1 for r in pa_results.values() 
                                         if isinstance(r, dict) and _is_skipped(r)),
                        decisions_buy=decisions['buy'],
                        decisions_sell=decisions['sell'],
                        decisions_wait=decisions['wait'],
                        decisions_avoid=decisions['avoid'],
                        stage2_tokens_in=stage2_in,
                        stage2_tokens_out=stage2_out,
                        trades_proposed=len(actionable),
                        api_cost_usd=api_cost_val,
                    )
                    
                    # Count context drift events this cycle
                    try:
                        from database.models import SystemConfig
                        from sqlalchemy import select as _sel2
                        today_str = datetime.now(timezone.utc).strftime('%Y%m%d')
                        drift_keys = (await perf_session.execute(
                            _sel2(SystemConfig.key)
                            .where(SystemConfig.key.like(f'context_drift_%_{today_str}%'))
                        )).scalars().all()
                        if drift_keys:
                            logger.info(
                                f'Context drift events today: {len(drift_keys)} '
                                f'({[k.split("_")[2] for k in drift_keys[:5]]})'
                            )
                            # Add to summary for monitoring dashboard
                            summary['context_drift_events_today'] = len(drift_keys)
                    except Exception:
                        pass
                        
                    perf_session.add(cycle_record)
                    try:
                        from database.event_store import TradingEventStore
                        await TradingEventStore.emit(
                            session=perf_session,
                            event_type="cycle.completed",
                            payload={
                                "cycle_id": cycle_id,
                                "elapsed_seconds": elapsed,
                                "decisions": decisions,
                                "trades_proposed": len(actionable),
                                "api_cost_usd": api_cost_val,
                            },
                            correlation_id=cycle_id,
                            actor="graph_cycle_scheduler",
                        )
                    except Exception:
                        pass
                    await perf_session.commit()
                    
                    skip_log = f", skipped={len(skipped_symbols_info)} ({', '.join(skipped_symbols_info)})" if skipped_symbols_info else ""
                    err_log = f", errors={len(error_symbols_info)} ({', '.join(error_symbols_info)})" if error_symbols_info else ""
                    logger.info(f'Cycle performance recorded: {decisions}{skip_log}{err_log}, cost=${api_cost_val:.4f}')
            except Exception as e:
                logger.error(f'Failed to record cycle performance (non-fatal): {e}')
                
            # Task 2.4: Cross-Cycle State Persistence
            try:
                decisions = final_state.get('summary', {}).get('per_asset', {})
                has_buy_sell = any(
                    r.get('decision') in ('buy', 'sell') 
                    for r in decisions.values() 
                    if isinstance(r, dict)
                )
                
                # P3-4 TODO: This consecutive_wait_count is currently unused by the rest of the system.
                # Future expansion: Expose this to FundamentalStage to allow it to widen its search
                # parameters if the system has been waiting too long without any trades.
                consecutive_wait = 0 if has_buy_sell else (
                    prior_insights.get('consecutive_wait_count', 0) + 1
                )
                
                cycle_state_to_save = {
                    'consecutive_wait_count': consecutive_wait,
                    'last_buy_sell_cycle': datetime.now(timezone.utc).isoformat() if has_buy_sell else prior_insights.get('last_buy_sell_cycle'),
                    'last_cycle_vix': summary.get('data_validation', {}).get('vix_latest', None),
                    'last_cycle_decisions': {
                        sym: r.get('decision') 
                        for sym, r in decisions.items() 
                        if isinstance(r, dict)
                    }
                }
                
                if consecutive_wait >= 5:
                    logger.warning(f'5+ consecutive WAIT-only cycles. Possible threshold too high or market regime issue.')
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_warning(
                        f'⚠️ <b>No Trades for {consecutive_wait} Cycles</b>\n'
                        f'All assets returning WAIT/AVOID for {consecutive_wait} consecutive cycles.\n'
                        f'Consider reviewing: (1) VIX threshold, (2) confluence threshold, '
                        f'(3) market regime, (4) data quality.'
                    )
                
                async with get_session() as state_session:
                    from database.models import SystemConfig
                    from sqlalchemy import select
                    import json
                    cfg = (await state_session.execute(
                        select(SystemConfig).where(SystemConfig.key == 'prior_cycle_state')
                    )).scalar_one_or_none()
                    state_json = json.dumps(cycle_state_to_save)
                    if cfg:
                        cfg.value = state_json
                    else:
                        state_session.add(SystemConfig(key='prior_cycle_state', value=state_json))
                    await state_session.commit()
            except Exception as e:
                logger.debug(f'Prior cycle state save failed (non-fatal): {e}')

            # Lesson Consolidation Check (weekly or when overdue)
            try:
                from analysis.memory.lesson_consolidator import consolidate_lessons_to_playbook
                from database.models import SystemConfig
                from sqlalchemy import select
                async with get_session() as session:
                    key = 'lesson_consolidation_last_run'
                    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                    should_run = True
                    if cfg and cfg.value:
                        last_run = datetime.fromisoformat(cfg.value)
                        if last_run.tzinfo is None:
                            last_run = last_run.replace(tzinfo=timezone.utc)
                        should_run = (datetime.now(timezone.utc) - last_run).total_seconds() > 7 * 86400
                    if should_run:
                        content = await consolidate_lessons_to_playbook(session, self.settings)
                        if content:
                            logger.info('Lessons Learned playbook consolidated and updated.')
                            now_iso = datetime.now(timezone.utc).isoformat()
                            if cfg:
                                cfg.value = now_iso
                            else:
                                session.add(SystemConfig(key=key, value=now_iso))
                            await session.commit()
            except Exception as e:
                logger.error(f'Lesson consolidation failed: {e}')

            # Post-cycle cleanup for UserMarketIntel (Lifecycle Management)
            try:
                await self.cleanup_user_market_intel(cycle_id)
            except Exception as e:
                logger.warning(f"UserMarketIntel lifecycle cleanup failed (non-fatal): {e}")

            # Generate and save Markdown Report
            try:
                from logging_observability.report_writer import ReportWriter
                writer = ReportWriter()
                await writer.write_cycle_report_async(cycle_id, final_state)
                logger.info(f'Cycle report saved for cycle {cycle_id}')
            except Exception as e:
                logger.debug(f'Report generation failed (non-fatal): {e}')
                
            # Emit POST_CYCLE plugin hook
            try:
                from utils.plugins.manager import get_plugin_manager, PluginHook
                await get_plugin_manager().emit(
                    PluginHook.POST_CYCLE,
                    cycle_id=cycle_id,
                    final_state=final_state,
                    summary=final_state.get("summary", summary),
                )
            except Exception as e:
                logger.debug(f"POST_CYCLE hook execution failed (non-fatal): {e}")

            logger.info(f"=== Graph Analysis Cycle Finished in {elapsed:.1f}s ===")
            for sym in leased_symbols:
                await lease_mgr.release_lease(sym, holder_id=cycle_holder_id)
            return final_state.get("summary", summary)

    async def _check_system_health_trend(self, session) -> None:
        """Detect if system health is degrading over recent cycles."""
        from database.models import CyclePerformance
        from sqlalchemy import select
        from datetime import timedelta
        
        try:
            from utils.analytics.paper_tracker import PaperTracker
            await PaperTracker(self.settings).check_and_alert_winrate(session, self.settings, min_trades=10)
        except Exception as e:
            logger.warning(f"Winrate check alert failed: {e}")

        
        recent_cycles = (await session.execute(
            select(CyclePerformance)
            .where(CyclePerformance.cycle_at >= datetime.now(timezone.utc) - timedelta(days=2))
            .order_by(CyclePerformance.cycle_at.desc())
            .limit(10)
        )).scalars().all()
        
        if len(recent_cycles) < 5:
            return
        
        # Check: are skip rates increasing?
        recent_skip_rates = []
        for c in recent_cycles[:5]:
            total = (c.assets_analyzed or 0) + (c.assets_skipped or 0)
            if total > 0:
                recent_skip_rates.append(c.assets_skipped / total)
        
        if len(recent_skip_rates) > 0:
            avg_skip_rate = sum(recent_skip_rates) / len(recent_skip_rates)
            if avg_skip_rate > 0.7:
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_warning(
                        f"⚠️ HIGH SKIP RATE DETECTED\n"
                        f"Average skip rate last 5 cycles: {avg_skip_rate:.0%}\n"
                        "This suggests: (1) Haiku prescreen too aggressive, "
                        "(2) Market in ranging regime, or (3) Data quality issues."
                    )
                except Exception: pass

    async def cleanup_user_market_intel(self, cycle_id: str) -> dict:
        """
        Post-cycle lifecycle cleanup for UserMarketIntel.
        1. Mark 'next_cycle_only' intel as consumed and deactivated.
        2. Mark expired intel as deactivated.
        3. Record audit entry in ActivityLog.
        """
        from database.models import UserMarketIntel, ActivityLog
        from sqlalchemy import select
        import utils.clock as clock

        consumed_count = 0
        expired_count = 0
        now_cleanup = clock.now()

        async with get_session() as intel_session:
            # 1. Mark next_cycle_only intel as consumed and inactive
            next_cycle_stmt = (
                select(UserMarketIntel)
                .where(
                    UserMarketIntel.is_active == True,
                    UserMarketIntel.target_cycle == "next_cycle_only",
                )
            )
            next_cycle_rows = (await intel_session.execute(next_cycle_stmt)).scalars().all()
            for row in next_cycle_rows:
                row.is_active = False
                row.consumed_at = now_cleanup
                row.consumed_by_cycle_id = cycle_id
                consumed_count += 1

            # 2. Mark expired intel as inactive
            expired_stmt = (
                select(UserMarketIntel)
                .where(
                    UserMarketIntel.is_active == True,
                    UserMarketIntel.expires_at.is_not(None),
                    UserMarketIntel.expires_at <= now_cleanup,
                )
            )
            expired_rows = (await intel_session.execute(expired_stmt)).scalars().all()
            for row in expired_rows:
                row.is_active = False
                expired_count += 1

            if consumed_count > 0 or expired_count > 0:
                intel_session.add(ActivityLog(
                    category="intel",
                    description=f"Cycle {cycle_id}: Cleaned up market intel (consumed {consumed_count} next_cycle_only, deactivated {expired_count} expired)",
                    actor="graph_cycle_scheduler",
                ))
                await intel_session.commit()
                logger.info(f"UserMarketIntel lifecycle cleanup: {consumed_count} consumed, {expired_count} expired")

        return {"consumed": consumed_count, "expired": expired_count}
