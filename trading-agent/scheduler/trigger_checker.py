# ==============================================================================
# File: scheduler/trigger_checker.py
# ==============================================================================

"""
Trigger Checker: Pemantauan presisi tinggi (interval pendek).

Fungsi:
Mengecek kondisi 'pending' triggers (price level, indikator, time) dengan
pencocokan angka murni, TANPA memanggil model AI. Jika terpenuhi, trigger 'fired'
dan barulah re-analisis (Stage 2) dipicu untuk aset tersebut.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_session
from database.safe_ops import safe_commit
from database.models import TradeTrigger, AssetAnalysis, TechnicalIndicator, ActivityLog

import utils.clock as clock

logger = logging.getLogger("TradingAgent.TriggerChecker")


class TriggerChecker:
    """
    Mengevaluasi triggers. Jika terpenuhi -> fired -> re-analisis aset.
    """

    def __init__(self, settings: dict, per_asset_stage=None, execution_service=None, cycle_scheduler=None, recovery_event=None):
        """
        Args:
            settings:         Dictionary konfigurasi lengkap.
            per_asset_stage:  Instance PerAssetStage. Jika diberikan, trigger yang 'fired'
                              akan memicu ulang analisis AI untuk simbol tersebut.
            execution_service: Instance ExecutionService untuk mengeksekusi keputusan trading.
            cycle_scheduler:   Instance GraphCycleScheduler opsional untuk delegasi eksekusi graf.
            recovery_event:    Optional[asyncio.Event] untuk sinkronisasi post-restart recovery.
        """
        sched_cfg = settings.get("trading", {}).get("schedule", {})
        trigger_cfg = settings.get("trading", {}).get("trigger_checker", {})
        self.interval_minutes: float = sched_cfg.get("trigger_check_minutes", 2)
        self.max_age_hours: float = float(trigger_cfg.get("max_trigger_age_hours", 18.0))
        self.settings = settings
        self._per_asset = per_asset_stage
        self._execution_service = execution_service
        self._cycle_scheduler = cycle_scheduler
        self._recovery_event = recovery_event
        self._running = False
        self._background_tasks: set[asyncio.Task] = set()
        self._reanalyzing_symbols: set[str] = set()
        self._stop_event = asyncio.Event()

    @property
    def _mt5(self):
        if self._cycle_scheduler and hasattr(self._cycle_scheduler, "_mt5") and self._cycle_scheduler._mt5:
            return self._cycle_scheduler._mt5
        if self._execution_service:
            return getattr(self._execution_service, "mt5_client", None) or getattr(self._execution_service, "mt5", None)
        return None

    @property
    def execution_service(self):
        return self._execution_service

    @property
    def dry_run(self) -> bool:
        if self._cycle_scheduler and hasattr(self._cycle_scheduler, "dry_run"):
            return self._cycle_scheduler.dry_run
        if self._execution_service and hasattr(self._execution_service, "dry_run"):
            return self._execution_service.dry_run
        return False

    @property
    def asset_universe(self) -> list:
        if self._cycle_scheduler and hasattr(self._cycle_scheduler, "asset_universe"):
            return self._cycle_scheduler.asset_universe
        return (
            self.settings.get("trading", {}).get("asset_universe")
            or self.settings.get("trading", {}).get("symbols", [])
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_once(self) -> dict:
        """
        Satu iterasi: cek semua pending trigger & evaluasi.
        
        Returns:
            Dict hasil cek (jumlah fired, aset direanalisis, dll).
        """
        async with get_session() as session:
            await self._expire_stale_triggers(session)
            pending = await self._get_pending_triggers(session)

        if not pending:
            logger.debug("No pending triggers found")
            return {"checked": 0, "fired": 0, "symbols_reanalyzed": []}

        logger.info(f"Checking {len(pending)} pending triggers...")
        fired_count = 0
        reanalyzed = []

        for trigger in pending:
            try:
                eval_result = await self._evaluate_trigger(trigger)
                if eval_result == "invalid":
                    async with get_session() as session:
                        await session.execute(update(TradeTrigger).where(TradeTrigger.id == trigger.id).values(status="invalid"))
                        await safe_commit(session, label="trigger_invalid")
                    continue
                elif eval_result == "expired":
                    async with get_session() as session:
                        await session.execute(update(TradeTrigger).where(TradeTrigger.id == trigger.id).values(status="expired"))
                        await safe_commit(session, label="trigger_expired")
                    continue
                elif eval_result is True:
                    # Kondisi terpenuhi! Fire trigger
                    async with get_session() as session:
                        symbol = await self._fire_trigger(session, trigger)
                    fired_count += 1

                    # FIX: If trigger_type is 'force_close', execute the position close directly
                    if trigger.trigger_type == "force_close" and self._execution_service:
                        await self._handle_force_close(trigger)

                    # SUB-SECOND DETERMINISTIC EXECUTION (Zero-LLM latency path)
                    trigger_cond = trigger.condition_json if isinstance(trigger.condition_json, dict) else {}
                    if isinstance(trigger.condition_json, str):
                        try:
                            trigger_cond = json.loads(trigger.condition_json)
                        except Exception:
                            trigger_cond = {}
                    preplanned_order = trigger_cond.get("preplanned_order") if isinstance(trigger_cond, dict) else None

                    if preplanned_order and self._execution_service:
                        logger.info(f"Trigger {trigger.id} fired -> Executing preplanned order deterministically for {symbol}")
                        try:
                            async with get_session() as session:
                                exec_res = await self._execution_service.execute_preplanned_order(
                                    session=session,
                                    symbol=symbol,
                                    order_plan=preplanned_order,
                                    trigger_id=trigger.id,
                                    analysis_id=trigger.asset_analysis_id,
                                )
                                logger.info(f"Preplanned order result for {symbol}: {exec_res.summary() if hasattr(exec_res, 'summary') else exec_res}")
                                try:
                                    from database.event_store import TradingEventStore
                                    await TradingEventStore.emit(
                                        session=session,
                                        event_type="trigger.price_level",
                                        payload={"symbol": symbol, "trigger_id": trigger.id, "preplanned": True},
                                        correlation_id=f"trigger_{trigger.id}",
                                        actor="trigger_checker",
                                    )
                                except Exception:
                                    pass
                        except Exception as exec_err:
                            logger.error(f"Execution of preplanned order failed for {symbol}: {exec_err}")
                        reanalyzed.append(symbol)
                        # Decouple full LLM re-analysis from critical price execution path with deduplication
                        if symbol and self._per_asset:
                            self._spawn_background_reanalysis(symbol)
                    # Picu re-analisis Stage 2 jika per_asset_stage tersedia (fallback tanpa preplanned order)
                    elif symbol and self._per_asset:
                        per_asset = self._per_asset
                        logger.info(f"Trigger {trigger.id} fired -> triggering re-analysis for {symbol}")
                        cycle_lock = getattr(self._cycle_scheduler, "_cycle_lock", None) if self._cycle_scheduler else None

                        async def _execute_trigger_reanalysis():
                            async with get_session() as session:
                                analysis_res = await per_asset.run_one(
                                    session, symbol, bypass_prescreen=True, skip_cooldown=True
                                )
                                reanalyzed.append(symbol)
                                
                                dec = analysis_res.get("decision", "").lower() if isinstance(analysis_res, dict) else ""
                                if dec in ("buy", "sell") and analysis_res.get("analysis_id"):
                                    try:
                                        from graph.reactive_graph import get_reactive_graph
                                        reactive_graph = get_reactive_graph()
                                        curr_price = analysis_res.get("current_price") or analysis_res.get("entry_price")
                                        reactive_state = {
                                            "symbols": [symbol],
                                            "event_type": "price_trigger",
                                            "event_data": {
                                                "trigger_id": trigger.id,
                                                "analysis_id": analysis_res.get("analysis_id"),
                                                "symbol": symbol,
                                                "current_price": curr_price,
                                            },
                                            "actionable_trades": [(symbol, analysis_res)],
                                            "market_regime": "normal",
                                            "summary": {},
                                            "errors": [],
                                            "should_pause": False,
                                        }
                                        config = {"configurable": {"scheduler": self._cycle_scheduler or self}}
                                        logger.info(f"Routing trigger re-analysis for {symbol} through LangGraph ReactiveStateGraph...")
                                        await reactive_graph.ainvoke(reactive_state, config=config)
                                    except Exception as e:
                                        logger.error(f"LangGraph reactive trigger execution failed for {symbol}: {e}", exc_info=True)
                                    logger.info(f"auto_execute=false — sending trade proposal for {symbol} (analysis #{analysis_res.get('analysis_id')}) from trigger re-analysis")
                                    try:
                                        from utils.infra.notifier import AgentNotifier
                                        notifier = AgentNotifier()
                                        ana_id = analysis_res.get("analysis_id")
                                        dec = analysis_res.get("decision", "").upper()
                                        conf = analysis_res.get("confidence", 0.0)
                                        sl = analysis_res.get("stop_loss", "N/A")
                                        tp = analysis_res.get("take_profit", "N/A")
                                        await notifier.send_info(
                                            f"🎯 <b>Trade Proposal from Trigger</b>\n\n"
                                            f"<b>Symbol:</b> {symbol}\n"
                                            f"<b>Action:</b> {dec}\n"
                                            f"<b>Confidence:</b> {conf:.2f}\n"
                                            f"<b>SL:</b> {sl} | <b>TP:</b> {tp}\n\n"
                                            f"Kirim <code>/approve {ana_id}</code> untuk eksekusi."
                                        )
                                    except Exception as notify_err:
                                        logger.error(f"Failed to send trade proposal notification for trigger {symbol}: {notify_err}")

                        if cycle_lock:
                            async with cycle_lock:
                                await _execute_trigger_reanalysis()
                        else:
                            await _execute_trigger_reanalysis()

            except Exception as e:
                logger.error(f"Error evaluating trigger id={trigger.id}: {e}")

        if fired_count:
            logger.info(f"Trigger check complete: {fired_count}/{len(pending)} fired | re-analyzed: {reanalyzed}")

        invalidation_alerts = await self.check_invalidation_conditions()

        return {
            "checked": len(pending),
            "fired": fired_count,
            "symbols_reanalyzed": reanalyzed,
            "invalidation_alerts": invalidation_alerts,
        }

    async def check_invalidation_conditions(self) -> list[dict]:
        from database.models import Position, AssetAnalysis, PriceOHLCV, SystemConfig
        from sqlalchemy import select as _select
        alerts = []
        
        async with get_session() as session:
            open_positions = (await session.execute(
                _select(Position).where(Position.status == 'open')
            )).scalars().all()
            
            for pos in open_positions:
                analysis = (await session.execute(
                    _select(AssetAnalysis)
                    .where(AssetAnalysis.symbol == pos.symbol)
                    .where(AssetAnalysis.generated_at <= pos.opened_at)
                    .where(AssetAnalysis.decision.in_(['buy', 'sell']))
                    .order_by(AssetAnalysis.generated_at.desc())
                    .limit(1)
                )).scalar_one_or_none()
                
                if not analysis:
                    continue
                
                # Get current price (prefer live MT5 tick for freshest price, fallback to DB with freshness validation)
                current_price = None
                mt5_inst = getattr(self._execution_service, 'mt5', getattr(self._execution_service, '_mt5', None))
                if mt5_inst:
                    try:
                        tick = await mt5_inst.get_tick(pos.symbol)
                        if tick and tick.get("bid"):
                            current_price = float(tick["bid"])
                    except Exception as tick_err:
                        logger.debug(f"Failed to fetch live tick for {pos.symbol}: {tick_err}")
                
                if current_price is None:
                    last_bar = (await session.execute(
                        _select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == pos.symbol)
                        .where(PriceOHLCV.timeframe.in_(['H1', 'H4', 'M15']))
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    
                    if not last_bar:
                        continue
                    
                    bar_time = last_bar.timestamp.replace(tzinfo=timezone.utc) if last_bar.timestamp.tzinfo is None else last_bar.timestamp
                    if (clock.now() - bar_time).total_seconds() > 86400:
                        logger.warning(f"[TriggerChecker] Stale price data for {pos.symbol} ({last_bar.timestamp}). Skipping invalidation check.")
                        continue
                    current_price = last_bar.close
                
                invalidation_triggered = False
                trigger_desc = ''
                
                # Priority 1: Use structured invalidation fields (reliable)
                if analysis.invalidation_price and analysis.invalidation_direction:
                    inv_price = analysis.invalidation_price
                    inv_dir = analysis.invalidation_direction
                    
                    if inv_dir == 'above' and current_price > inv_price:
                        invalidation_triggered = True
                        trigger_desc = (
                            f'Price ({current_price:.5f}) is ABOVE invalidation level {inv_price:.5f} '
                            f'[structured field detection]'
                        )
                    elif inv_dir == 'below' and current_price < inv_price:
                        invalidation_triggered = True
                        trigger_desc = (
                            f'Price ({current_price:.5f}) is BELOW invalidation level {inv_price:.5f} '
                            f'[structured field detection]'
                        )
                
                # Priority 2: Fallback to text parsing if no structured fields
                elif analysis.invalidation and not analysis.invalidation_price:
                    invalidation_text = analysis.invalidation.lower()
                    import re
                    above_match = re.search(r'(?:close[s]?\s+)?above\s+([\d,]+(?:\.\d+)?)', invalidation_text)
                    below_match = re.search(r'(?:close[s]?\s+)?below\s+([\d,]+(?:\.\d+)?)', invalidation_text)
                    
                    matched_price = None
                    matched_dir = None
                    
                    # For BUY positions, invalidation is a drop BELOW a support level
                    if pos.direction == 'buy' and below_match:
                        try:
                            level = float(below_match.group(1).replace(',', ''))
                            if abs(level - current_price) / current_price < 0.20:
                                matched_price = level
                                matched_dir = 'below'
                        except ValueError:
                            pass
                    # For SELL positions, invalidation is a rise ABOVE a resistance level
                    elif pos.direction == 'sell' and above_match:
                        try:
                            level = float(above_match.group(1).replace(',', ''))
                            if abs(level - current_price) / current_price < 0.20:
                                matched_price = level
                                matched_dir = 'above'
                        except ValueError:
                            pass
                    
                    if matched_price and matched_dir:
                        if matched_dir == 'above' and current_price > matched_price:
                            invalidation_triggered = True
                            trigger_desc = f'Price ({current_price:.5f}) above text-parsed level {matched_price} [text fallback]'
                        elif matched_dir == 'below' and current_price < matched_price:
                            invalidation_triggered = True
                            trigger_desc = f'Price ({current_price:.5f}) below text-parsed level {matched_price} [text fallback]'
                    else:
                        logger.debug(
                            f'[InvalidationMonitor] Cannot parse invalidation for {pos.symbol}: '
                            f'no structured fields or direction mismatch in text parsing.'
                        )
                
                if not invalidation_triggered:
                    continue
                
                # Dedup alert (max once per 4h)
                alert_key = f'invalidation_alerted_{pos.id}'
                last_alert = (await session.execute(
                    _select(SystemConfig).where(SystemConfig.key == alert_key)
                )).scalar_one_or_none()
                now_str = datetime.now(timezone.utc).isoformat()
                
                should_alert = True
                if last_alert and last_alert.value:
                    try:
                        last_time = datetime.fromisoformat(last_alert.value)
                        if last_time.tzinfo is None:
                            last_time = last_time.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - last_time).total_seconds() < 14400:  # 4h
                            should_alert = False
                    except Exception as dt_err:
                        logger.debug(f"Failed to parse last_alert timestamp: {dt_err}")
                
                if should_alert:
                    alert_msg = (
                        f'⚠️ <b>Invalidation Alert — {pos.symbol}</b>\n\n'
                        f'Position: {pos.direction.upper()} {pos.volume}L @ {pos.entry_price} | ticket={pos.mt5_ticket}\n\n'
                        f'Condition Triggered: {trigger_desc}\n'
                        f'Original invalidation: <i>{(analysis.invalidation or "N/A")[:150]}</i>\n\n'
                        f'Consider closing position manually.'
                    )
                    # Persist alert timestamp FIRST to prevent spam loop
                    if last_alert:
                        last_alert.value = now_str
                    else:
                        session.add(SystemConfig(key=alert_key, value=now_str))
                    await session.commit()

                    # Send notification (non-blocking, failure won't cause resend)
                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_warning(alert_msg)
                        logger.warning(f'Invalidation alert sent for {pos.symbol} position {pos.id}')
                    except Exception as e:
                        logger.error(f'Failed to send invalidation alert (state saved, no resend): {e}')
                        
                # Auto-close only if explicitly enabled in configuration
                auto_close_enabled = self.settings.get('trading', {}).get('position_review', {}).get('auto_close_on_invalidation', False) or \
                                     self.settings.get('trading', {}).get('trigger_checker', {}).get('auto_close_on_invalidation', False)
                if self._execution_service and auto_close_enabled:
                    logger.warning(f'Auto-closing position {pos.mt5_ticket} due to invalidation (auto_close_on_invalidation=True).')
                    try:
                        await self._execution_service.close_position_by_ticket(
                            ticket=pos.mt5_ticket, 
                            requested_by="TriggerChecker", 
                            reason=f"Invalidation hit: {trigger_desc}"
                        )
                    except Exception as close_err:
                        logger.error(f'Failed to auto-close {pos.symbol} ticket {pos.mt5_ticket}: {close_err}')
                elif not auto_close_enabled:
                    logger.info(f'Position {pos.mt5_ticket} invalidation triggered but auto-close is disabled in settings. Notification sent.')
                
                alerts.append({
                    'symbol': pos.symbol,
                    'ticket': pos.mt5_ticket,
                    'trigger_desc': trigger_desc,
                    'invalidation_text': analysis.invalidation,
                })
                
        return alerts

    async def start(self) -> None:
        """Looping trigger check (continuous)."""
        self._running = True
        logger.info(f"Trigger checker starting (interval: {self.interval_minutes}m)")

        if self._recovery_event:
            logger.info("[TriggerChecker] Waiting for recovery event before first check pass...")
            try:
                await asyncio.wait_for(self._recovery_event.wait(), timeout=180.0)
                logger.info("[TriggerChecker] Recovery complete, starting trigger check loop.")
            except asyncio.TimeoutError:
                logger.warning("[TriggerChecker] Recovery event wait timed out (180s). Proceeding anyway.")

        while self._running:
            try:
                result = await self.run_once()
                if result["fired"] > 0:
                    logger.info(f"Fired {result['fired']} triggers this pass")
            except Exception as e:
                logger.error(f"Trigger check loop error: {e}")

            sleep_duration = self.interval_minutes * 60
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_duration)
                break
            except asyncio.TimeoutError:
                pass

    # Backwards compatibility alias
    check_once = run_once

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        logger.info("Trigger checker stop requested.")

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _handle_force_close(self, trigger: TradeTrigger) -> None:
        if not self._execution_service:
            return
        from database.models import Position
        async with get_session() as session:
            pos = (await session.execute(
                select(Position).where(Position.analysis_id == trigger.asset_analysis_id)
                .where(Position.status == 'open')
            )).scalar_one_or_none()
        if not pos or not pos.mt5_ticket:
            return
        try:
            await self._execution_service.close_position_by_ticket(
                pos.mt5_ticket, requested_by='edge_time_exit', reason='max_hold_minutes reached',
            )
            logger.info(f'[TriggerChecker] Force-closed {pos.symbol} ticket={pos.mt5_ticket} (edge max-hold)')
        except Exception as e:
            logger.error(f'[TriggerChecker] force_close failed for ticket {pos.mt5_ticket}: {e}')

    def _spawn_background_reanalysis(self, symbol: str) -> None:
        """Spawn background reanalysis task with reference retention and deduplication."""
        if symbol in self._reanalyzing_symbols:
            logger.info(f"Background re-analysis for {symbol} already running, skipping duplicate.")
            return
        self._reanalyzing_symbols.add(symbol)
        task = asyncio.create_task(self._background_reanalysis(symbol))
        self._background_tasks.add(task)
        task.add_done_callback(lambda t: (self._background_tasks.discard(t), self._reanalyzing_symbols.discard(symbol)))

    async def _background_reanalysis(self, symbol: str) -> None:
        """Run Stage 2 re-analysis in background without blocking execution path."""
        if not self._per_asset:
            return
        try:
            cycle_lock = getattr(self._cycle_scheduler, "_cycle_lock", None) if self._cycle_scheduler else None
            if cycle_lock:
                async with cycle_lock:
                    async with get_session() as session:
                        await self._per_asset.run_one(
                            session, symbol, bypass_prescreen=True, skip_cooldown=True
                        )
            else:
                async with get_session() as session:
                    await self._per_asset.run_one(
                        session, symbol, bypass_prescreen=True, skip_cooldown=True
                    )
        except Exception as e:
            logger.error(f"Background re-analysis failed for {symbol}: {e}")
        finally:
            self._reanalyzing_symbols.discard(symbol)

    async def _expire_stale_triggers(self, session: AsyncSession) -> int:
        """Batch auto-expire stale triggers that exceeded max_age_hours."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
        result = await session.execute(
            update(TradeTrigger)
            .where(TradeTrigger.status == "pending")
            .where(TradeTrigger.trigger_type.in_(["price_level", "indicator", "news"]))
            .where(TradeTrigger.created_at < cutoff_time)
            .values(status="expired")
        )
        expired_count = int(getattr(result, "rowcount", 0) or 0)
        if expired_count > 0:
            await session.commit()
            logger.info(f"Auto-expired {expired_count} stale pending triggers (age > {self.max_age_hours}h)")
        return expired_count

    async def _get_pending_triggers(self, session: AsyncSession) -> list[TradeTrigger]:
        """Ambil pending triggers."""
        result = await session.execute(
            select(TradeTrigger)
            .where(TradeTrigger.status == "pending")
        )
        return list(result.scalars().all())

    async def _fire_trigger(self, session: AsyncSession, trigger: TradeTrigger) -> Optional[str]:
        """Update status menjadi 'fired' & log ke activity_log."""
        now = datetime.now(timezone.utc)

        # Mark fired
        await session.execute(
            update(TradeTrigger)
            .where(TradeTrigger.id == trigger.id)
            .values(status="fired", fired_at=now)
        )

        # Get the symbol from the linked AssetAnalysis
        analysis = await session.get(AssetAnalysis, trigger.asset_analysis_id)
        symbol = analysis.symbol if analysis else None

        # Log activity
        condition = {}
        try:
            condition = json.loads(trigger.condition_json) if trigger.condition_json else {}
        except Exception as json_err:
            logger.debug(f"Failed to parse trigger {trigger.id} condition_json for activity log: {json_err}")

        session.add(ActivityLog(
            category="trading",
            description=(
                f"Trigger FIRED: id={trigger.id} type={trigger.trigger_type} "
                f"symbol={symbol} condition={json.dumps(condition)[:200]}"
            ),
            related_id=trigger.id,
            actor="trigger_checker",
        ))
        await safe_commit(session, label="fire_trigger")
        logger.info(f"Trigger {trigger.id} fired: {trigger.trigger_type} for {symbol}")
        return symbol

    # ------------------------------------------------------------------
    # Condition evaluators (pure logic, no LLM call)
    # ------------------------------------------------------------------

    async def _evaluate_trigger(self, trigger: TradeTrigger) -> 'bool | str':
        """Evaluasi apakah kondisi terpenuhi (True), belum (False), kedaluwarsa ('expired'), atau cacat ('invalid')."""
        trigger_type = trigger.trigger_type
        try:
            condition = json.loads(trigger.condition_json) if trigger.condition_json else {}
        except Exception:
            logger.warning(f"Trigger {trigger.id} has invalid condition_json")
            return "invalid"

        # Check TTL expiration for non-time triggers
        if trigger_type in ("price_level", "price", "indicator", "news"):
            if self._trigger_age_exceeded(trigger, max_hours=self.max_age_hours):
                return "expired"

        if trigger_type in ("price_level", "price"):
            return await self._check_price_level(trigger, condition)
        elif trigger_type == "indicator":
            return await self._check_indicator(trigger, condition)
        elif trigger_type == "time" or trigger_type == "force_close":
            return self._check_time(trigger, condition)
        elif trigger_type == "news":
            # News triggers are processed via NewsWatcher or expired by TTL
            return False
        else:
            logger.debug(f"Unknown trigger type: {trigger_type}")
            return "invalid"

    async def _check_price_level(self, trigger: TradeTrigger, condition: dict) -> 'bool | str':
        """Evaluasi harga crossing level (above/below)."""
        raw_price = condition.get("price")
        direction = condition.get("direction")  # "above" or "below"
        symbol = condition.get("symbol")

        if (raw_price is None or not direction) and condition.get("detail"):
            import re
            text = condition.get("detail", "").lower()
            above_m = re.search(r'(?:above|break[s]?\s+above|over|reache[s]?|hit[s]?)\s+([\d,]+(?:\.\d+)?)', text)
            below_m = re.search(r'(?:below|break[s]?\s+below|under|drop[s]?\s+to)\s+([\d,]+(?:\.\d+)?)', text)
            if above_m and raw_price is None:
                try:
                    raw_price = float(above_m.group(1).replace(',', ''))
                    direction = 'above'
                except ValueError:
                    pass
            elif below_m and raw_price is None:
                try:
                    raw_price = float(below_m.group(1).replace(',', ''))
                    direction = 'below'
                except ValueError:
                    pass

        if raw_price is None or not direction or not symbol:
            # Pastikan trigger tidak menyebabkan infinite loop jika malformed
            return "invalid"

        try:
            price = float(raw_price)
        except (ValueError, TypeError):
            logger.warning(f"Invalid price value '{raw_price}' in trigger {trigger.id}")
            return "invalid"

        async with get_session() as session:
            from database.models import PriceOHLCV
            last_bar = (await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()

            if last_bar is None:
                return False

            bar_ts = getattr(last_bar, "timestamp", None)
            if isinstance(bar_ts, datetime):
                now = datetime.now(timezone.utc)
                if bar_ts.tzinfo is None:
                    bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                if (now - bar_ts).total_seconds() > 7200:
                    logger.debug(f"TriggerChecker: bar data for {symbol} is older than 2h ({last_bar.timestamp}), skipping price level trigger.")
                    return False

            try:
                current_price = float(last_bar.close)
            except (ValueError, TypeError):
                return False

            if direction == "above":
                return current_price >= price
            elif direction == "below":
                return current_price <= price

        return False

    async def _check_indicator(self, trigger: TradeTrigger, condition: dict) -> 'bool | str':
        """Evaluasi nilai indikator crossing threshold."""
        indicator_name = condition.get("indicator")
        symbol = condition.get("symbol")
        timeframe = condition.get("timeframe", "H4")
        raw_threshold = condition.get("threshold")
        direction = condition.get("direction")  # "above" or "below"

        if not all([indicator_name, symbol, direction]) or raw_threshold is None:
            return "invalid"

        try:
            threshold = float(raw_threshold)
        except (ValueError, TypeError):
            logger.warning(f"Invalid threshold value '{raw_threshold}' in trigger {trigger.id}")
            return "invalid"

        async with get_session() as session:
            row = (await session.execute(
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == timeframe)
                .where(TechnicalIndicator.indicator_name == indicator_name)
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()

            if row is None:
                return False

            try:
                value = json.loads(row.value_json)
                # Untuk nilai numerik sederhana (RSI, SMA, dll.)
                if isinstance(value, (int, float)):
                    numeric = float(value)
                # Untuk struktur dict (MACD, BBANDS, STOCH) — ambil nilai numerik pertama
                elif isinstance(value, dict):
                    numeric = float(next(v for v in value.values() if v is not None))
                else:
                    return False

                if direction == "above":
                    return numeric >= float(threshold)
                elif direction == "below":
                    return numeric <= float(threshold)
            except (TypeError, ValueError, StopIteration):
                pass

        return False

    @staticmethod
    def _check_time(trigger: TradeTrigger, condition: dict) -> 'bool | str':
        """Evaluasi waktu tercapai (time-based)."""
        fire_at_str = condition.get("fire_at")
        if fire_at_str:
            try:
                fire_at = datetime.fromisoformat(fire_at_str)
                if fire_at.tzinfo is None:
                    fire_at = fire_at.replace(tzinfo=timezone.utc)
                return datetime.now(timezone.utc) >= fire_at
            except ValueError:
                return "invalid"
                
        return TriggerChecker._trigger_age_exceeded(trigger, max_hours=6)

    @staticmethod
    def _trigger_age_exceeded(trigger: TradeTrigger, max_hours: float) -> bool:
        """Safety net: True jika usia trigger melebihi `max_hours`."""
        if trigger.created_at is None:
            return False
        created = trigger.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created
        return age > timedelta(hours=max_hours)
