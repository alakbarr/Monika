# ==============================================================================
# File: application/orchestrator/recovery.py
# ==============================================================================

"""
Post-restart recovery, tick dispatch, and fallback consent mixin for TradingAgent.
"""

from __future__ import annotations

import asyncio
import datetime as _dt_module
from datetime import datetime, timedelta, timezone
import logging
import sys
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from monika.application.execution.execution_service import ExecutionService
    from monika.application.scheduler.graph_cycle_scheduler import GraphCycleScheduler
    from monika.application.scheduler.market_data_scheduler import MarketDataScheduler
    from monika.application.scheduler.position_guardian import PositionGuardian
    from monika.infrastructure.brokers.mt5_client import MT5Client

logger = logging.getLogger("TradingAgent.Main")


class AgentRecoveryMixin:
    """Mixin responsible for post-restart state reconstruction and approval flows."""

    settings: dict[str, Any]
    shutdown_event: asyncio.Event
    _recovery_complete: asyncio.Event
    _fallback_always_approved: bool
    _mt5_degraded: bool
    event_bus: Optional[Any]
    execution_service: Optional[ExecutionService]
    mt5_client: Optional[MT5Client]
    position_guardian: Optional[PositionGuardian]
    market_data_scheduler: Optional[MarketDataScheduler]
    cycle_scheduler: Optional[GraphCycleScheduler]
    telegram_bot: Optional[Any]
    _create_background_task: Callable[..., asyncio.Task[Any]]

    async def publish_tick(self, symbol: str, bid: float, ask: float, last: float = 0.0, spread: float = 0.0) -> None:
        """Publish a live TickPriceEvent to the centralized EventBus."""
        if not self.event_bus:
            return
        from monika.application.protocol.event_bus import TickPriceEvent

        event = TickPriceEvent(
            symbol=symbol.upper(),
            bid=bid,
            ask=ask,
            last=last or ((bid + ask) / 2.0 if bid and ask else bid or ask),
            spread=spread or (round(ask - bid, 5) if ask > bid else 0.0),
            timestamp=datetime.now(timezone.utc),
        )
        await self.event_bus.publish(event)

    async def request_fallback_consent(self, prompt_text: str) -> bool:
        """
        Coordinate fallback consent request across CLI and Telegram channels.
        Returns True if approved (single cycle or persistent), False if rejected.
        """
        logger.warning(f"Fallback consent requested: {prompt_text}")

        # Event for CLI prompt synchronization
        cli_event = asyncio.Event()
        cli_result = {"approved": False, "always": False}

        def cli_prompt():
            import time

            if not sys.stdin.isatty():
                # If non-interactive terminal, block thread to prevent premature completion
                # from canceling concurrent Telegram prompt task
                while not cli_event.is_set():
                    time.sleep(1)
                return

            print(f"\n[FALLBACK REQUIRED] {prompt_text}")
            print("1. Approve (Single Cycle)")
            print("2. Approve (Always / Persistent)")
            print("3. Reject")
            sys.stdout.flush()
            if sys.platform == "win32":
                try:
                    import msvcrt

                    chars: list[str] = []
                    while not cli_event.is_set():
                        if msvcrt.kbhit():
                            ch = msvcrt.getwche()
                            if ch in ("\r", "\n"):
                                ans = "".join(chars).strip()
                                chars = []
                                if ans == "1":
                                    cli_result["approved"] = True
                                    cli_result["always"] = False
                                    return
                                elif ans == "2":
                                    cli_result["approved"] = True
                                    cli_result["always"] = True
                                    return
                                elif ans == "3":
                                    cli_result["approved"] = False
                                    return
                                else:
                                    print("\nPlease select 1, 2, or 3: ", end="")
                                    sys.stdout.flush()
                            else:
                                chars.append(ch)
                        else:
                            time.sleep(0.1)
                    return
                except Exception:
                    pass

            while not cli_event.is_set():
                try:
                    ans = sys.stdin.readline()
                    if not ans:  # EOF
                        while not cli_event.is_set():
                            time.sleep(1)
                        return
                    ans = ans.strip()
                    if ans == "1":
                        cli_result["approved"] = True
                        cli_result["always"] = False
                        return
                    elif ans == "2":
                        cli_result["approved"] = True
                        cli_result["always"] = True
                        return
                    elif ans == "3":
                        cli_result["approved"] = False
                        return
                    else:
                        print("Please select 1, 2, or 3: ", end="")
                        sys.stdout.flush()
                except Exception:
                    # Hold thread if stdin read fails
                    while not cli_event.is_set():
                        time.sleep(1)
                    return

        # Execute CLI prompt in separate thread to avoid blocking event loop
        cli_task = asyncio.create_task(asyncio.to_thread(cli_prompt))

        # Execute Telegram prompt
        tg_event = asyncio.Event()
        tg_result = {"approved": False, "always": False}
        if self.telegram_bot:
            bot = self.telegram_bot

            async def wait_for_tg():
                await bot.request_fallback_consent(prompt_text, tg_event, tg_result)
                await tg_event.wait()

            tg_task = asyncio.create_task(wait_for_tg())
        else:
            # Dummy task when Telegram bot is unavailable
            async def dummy_tg():
                await asyncio.sleep(86400)

            tg_task = asyncio.create_task(dummy_tg())

        # Wait for first respondent with 5 minute timeout (300s)
        done, pending = await asyncio.wait(
            [cli_task, tg_task, asyncio.create_task(self.shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=300.0,
        )

        # Cancel remaining pending tasks
        for task in pending:
            task.cancel()

        if self.shutdown_event.is_set():
            return False

        # Set event to complete cli_prompt if still active
        cli_event.set()

        if not done:
            # Timeout reached
            approved = False
            always = False
            source = "Timeout (5 minutes)"
            print("\n[FALLBACK] Approval timeout reached (5 minutes). Default: Rejected.")
            if self.telegram_bot:
                asyncio.create_task(
                    self.telegram_bot.send_notification(
                        "[PROSES] Fallback approval timed out (5 minutes). Automated decision: *Rejected*."
                    )
                )
        elif tg_event.is_set():
            approved = tg_result["approved"]
            always = tg_result["always"]
            source = "Telegram"
            print(f"\n[FALLBACK] Decision received from Telegram: {'Approved' if approved else 'Rejected'}")
        else:
            approved = cli_result["approved"]
            always = cli_result["always"]
            source = "CLI"
            if self.telegram_bot:
                asyncio.create_task(
                    self.telegram_bot.send_notification(
                        f"[INFO] Fallback decision received from CLI: {'Approved' if approved else 'Rejected'}"
                    )
                )

        if approved and always:
            self._fallback_always_approved = True
            logger.info(f"Fallback APPROVED (Persistent) via {source}.")
        elif approved:
            logger.info(f"Fallback APPROVED (Single Cycle) via {source}.")
        else:
            logger.info(f"Fallback REJECTED via {source}.")

        return approved

    async def _post_restart_recovery(self):
        """
        Tasks to run after restart to ensure consistency:
        1. Sync positions dari MT5 (detect posisi yang ditutup saat kita offline)
        2. Check apakah ada analysis yang sudah expired yang perlu di-refresh
        3. Reset Gemini rate limiter counters jika hari baru
        """
        from monika.infrastructure.database.db import get_session

        logger.info("[Recovery] Starting post-restart recovery tasks...")

        try:
            if self.execution_service:
                try:
                    await self.execution_service._restore_executed_ids_from_db()
                except Exception as e:
                    logger.error(f"[Recovery] Failed to restore executed IDs: {e}")

            max_wait = 120
            wait_interval = 10
            elapsed = 0

            async def _check_broker_connected() -> bool:
                if (
                    self.execution_service
                    and hasattr(self.execution_service, "broker_adapter")
                    and self.execution_service.broker_adapter
                ):
                    adapter = self.execution_service.broker_adapter
                    if hasattr(adapter, "ensure_connected"):
                        return await adapter.ensure_connected()
                    if hasattr(adapter, "is_connected"):
                        return await adapter.is_connected()
                if self.mt5_client:
                    return await self.mt5_client.is_connected()
                return True

            while elapsed < max_wait:
                if await _check_broker_connected():
                    logger.info(f"[Recovery] Broker/MT5 connected after {elapsed}s")
                    break
                logger.info(f"[Recovery] Waiting for Broker/MT5... ({elapsed}s/{max_wait}s)")
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval

            if not await _check_broker_connected():
                logger.error("[Recovery] Broker/MT5 failed to connect within timeout — entering degraded mode")
                self._mt5_degraded = True
                try:
                    if self.telegram_bot:
                        await self.telegram_bot.send_notification(
                            "[PERINGATAN] MT5 tidak terhubung setelah restart!\n"
                            "Agent berjalan dalam mode degraded.\n"
                            "Position monitoring tetap berjalan; eksekusi baru ditunda."
                        )
                except Exception:
                    pass
                # Unblock position monitors to operate in degraded mode immediately
                self._recovery_complete.set()
                logger.warning("[Recovery] Degraded mode active: _recovery_complete event set.")
            else:
                self._mt5_degraded = False
                # 1. Sync positions
                if self.execution_service:
                    for attempt in range(3):
                        try:
                            await self.execution_service.sync_positions()
                            logger.info("[Recovery] Position sync successful")
                            break
                        except Exception as e:
                            logger.warning(f"[Recovery] Sync attempt {attempt + 1} failed: {e}")
                            await asyncio.sleep(15)

                    # 1a. Reconcile in-flight orders stuck during crash/restart (C-4)
                    try:
                        inflight_res = await self.execution_service.reconcile_inflight_orders()
                        if inflight_res.get("total", 0) > 0:
                            logger.info(f"[Recovery] In-flight orders processed: {inflight_res}")
                    except Exception as inflight_err:
                        logger.error(f"[Recovery] In-flight order reconciliation failed (non-fatal): {inflight_err}")

                # 1b. Check Friday close protection if it's Friday and past 20:00 UTC
                now = datetime.now(timezone.utc)
                if now.weekday() == 4 and now.hour >= 20:
                    logger.info("[Recovery] Friday past 20:00 UTC detected. Running gap protection check...")
                    try:
                        if self.position_guardian:
                            res = await self.position_guardian.check_friday_close_protection()
                            alerted = res.get("positions_alerted", 0)
                            if alerted > 0:
                                logger.info(f"[Recovery] Friday protection alerted on {alerted} positions.")
                        else:
                            logger.warning("[Recovery] position_guardian not initialized, skipping Friday check.")
                    except Exception as e:
                        logger.error(f"[Recovery] Friday protection check failed: {e}")

                # Signal to position guards (TriggerChecker, PositionExitReviewer,
                # TrailingStopManager, OrderReconciler, PositionGuardian) that positions are reconciled.
                self._recovery_complete.set()
                logger.info("[Recovery] Position sync and order reconciliation complete: _recovery_complete event set.")

                # 1c & 1d. Market Data Synchronization, Indicator Warmup, and Strategy Decay loading
                try:
                    # 1c. Initial Market Data Synchronization & Indicator Warmup
                    if self.market_data_scheduler:
                        warmup_timeout = float(
                            self.settings.get("trading", {}).get("schedule", {}).get("warmup_timeout_seconds", 360.0)
                        )
                        try:
                            logger.info(
                                "[Recovery] Running initial market data synchronization and indicator warmup..."
                            )
                            await asyncio.wait_for(
                                asyncio.shield(self.market_data_scheduler.sync_now()),
                                timeout=warmup_timeout,
                            )
                            logger.info("[Recovery] Initial market data warmup complete.")
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"[Recovery] Initial market data warmup timed out ({int(warmup_timeout)}s, non-fatal) — proceeding in background."
                            )
                        except Exception as e:
                            logger.warning(f"[Recovery] Initial market data sync failed (non-fatal): {e}")

                    # 1d. Restore Strategy Decay Monitor state from DB
                    try:
                        from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

                        async with get_session() as rec_session:
                            await get_strategy_decay_monitor().load_from_db(rec_session)
                        logger.info("[Recovery] StrategyDecayMonitor health state restored from DB")
                    except Exception as decay_err:
                        logger.debug(f"[Recovery] Failed to restore StrategyDecayMonitor state: {decay_err}")
                finally:
                    warmup_evt = getattr(self, "_warmup_complete", None)
                    if warmup_evt is not None:
                        warmup_evt.set()
                    logger.info(
                        "[Recovery] Market data warmup and decay state restoration complete: _warmup_complete event set."
                    )

            # Ensure recovery and warmup complete flags are set (idempotent)
            self._recovery_complete.set()
            warmup_evt = getattr(self, "_warmup_complete", None)
            if warmup_evt is not None:
                warmup_evt.set()
            logger.info("[Recovery] Startup data warmup done: _recovery_complete and _warmup_complete events verified.")

            _recovery_cycle_dispatched = False
            from sqlalchemy import select

            from monika.application.analysis.prefetch.news_digest import NewsDigestProcessor
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import CyclePerformance, FundamentalBrief, NewsDigest

            # Harmonized Catch-up & Brief Expiry Check
            try:
                sched_cfg = self.settings.get("trading", {}).get("schedule", {})
                catch_up_enabled = sched_cfg.get("catch_up_missed_cycles", True)
                overdue_multiplier = float(sched_cfg.get("catch_up_overdue_multiplier", 1.5))
                cycle_hours = float(sched_cfg.get("analysis_cycle_hours", 8.0))
                data_quality_cfg = self.settings.get("data_quality", {})
                max_brief_age = float(data_quality_cfg.get("max_brief_age_analysis_hours", 12.0))
                effective_threshold = min(cycle_hours * overdue_multiplier, max_brief_age)
                tz_name = sched_cfg.get("timezone", "Asia/Jakarta")
                cycle_times_raw = sched_cfg.get("cycle_times_local") or ["07:00", "15:00", "20:00"]

                if not catch_up_enabled:
                    logger.info(
                        "[Recovery] catch_up_missed_cycles=false — melewati pengecekan catch-up. "
                        "Siklus berikutnya akan jalan sesuai jadwal jam tetap (cycle_times_local)."
                    )
                else:
                    async with get_session() as session:
                        last_cycle = (
                            await session.execute(
                                select(CyclePerformance).order_by(CyclePerformance.cycle_at.desc()).limit(1)
                            )
                        ).scalar_one_or_none()

                        brief = (
                            await session.execute(
                                select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                            )
                        ).scalar_one_or_none()

                        dt_now = datetime.now(timezone.utc)
                        hours_since_last = None
                        cycle_at = None
                        if last_cycle and last_cycle.cycle_at:
                            cycle_at = last_cycle.cycle_at
                            if cycle_at.tzinfo is None:
                                cycle_at = cycle_at.replace(tzinfo=timezone.utc)
                            hours_since_last = (dt_now - cycle_at).total_seconds() / 3600

                        brief_age = None
                        brief_expired = False
                        if brief and brief.generated_at:
                            gen_at = brief.generated_at
                            if gen_at.tzinfo is None:
                                gen_at = gen_at.replace(tzinfo=timezone.utc)
                            brief_age = (dt_now - gen_at).total_seconds() / 3600
                            brief_expired = brief_age > max_brief_age
                        else:
                            brief_expired = True

                        from monika.application.scheduler.wall_clock import (
                            get_tzinfo,
                            parse_time_list,
                            previous_occurrence,
                        )

                        most_recent_target_utc = None
                        try:
                            times = parse_time_list(cycle_times_raw)
                            most_recent_target_utc = previous_occurrence(times, tz_name, dt_now)
                        except Exception as e:
                            logger.debug(f"[Recovery] Failed calculating previous occurrence: {e}")

                        needs_recovery = False
                        reason = ""

                        if not last_cycle:
                            if brief_expired:
                                needs_recovery = True
                                reason = "Belum pernah ada siklus yang berjalan / Fundamental Brief belum tersedia"
                        elif most_recent_target_utc is not None and cycle_at is not None:
                            tolerance = timedelta(minutes=90)
                            cycle_covered = cycle_at >= (most_recent_target_utc - tolerance)
                            if not cycle_covered:
                                tz = get_tzinfo(tz_name)
                                target_local_str = most_recent_target_utc.astimezone(tz).strftime("%Y-%m-%d %H:%M")
                                last_local_str = cycle_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
                                needs_recovery = True
                                reason = f"Jadwal sesi {target_local_str} ({tz_name}) terlewat (siklus terakhir: {last_local_str})"
                            elif brief_expired:
                                needs_recovery = True
                                if brief_age is not None:
                                    reason = (
                                        f"Fundamental Brief sudah kedaluwarsa ({brief_age:.1f}h > {max_brief_age:.1f}h)"
                                    )
                                else:
                                    reason = "Fundamental Brief belum tersedia / tidak valid"
                        else:
                            if hours_since_last is not None and hours_since_last > effective_threshold:
                                needs_recovery = True
                                reason = f"Siklus terakhir {hours_since_last:.1f}h lalu (> ambang {effective_threshold:.1f}h)"
                            elif brief_expired:
                                needs_recovery = True
                                reason = "Fundamental Brief sudah kedaluwarsa / belum tersedia"

                        if needs_recovery:
                            logger.warning(f"[Recovery] {reason}. Menjadwalkan SATU siklus pemulihan sekarang.")
                            if not _recovery_cycle_dispatched and self.cycle_scheduler:
                                self._create_background_task(
                                    self.cycle_scheduler.run_once(forced=True), name="recovery_cycle"
                                )
                                _recovery_cycle_dispatched = True
                        else:
                            if hours_since_last is not None:
                                brief_age_str = f"age={brief_age:.1f}h" if brief_age is not None else "no brief"
                                logger.info(
                                    f"[Recovery] Siklus terakhir {hours_since_last:.1f}h lalu dan Fundamental Brief masih valid "
                                    f"({brief_age_str} <= {max_brief_age:.1f}h). Tidak perlu catch-up; siklus berikutnya mengikuti jadwal."
                                )
                            else:
                                logger.info(
                                    "[Recovery] Belum ada siklus tercatat di DB (instalasi baru). Menunggu jadwal pertama."
                                )
            except Exception as e:
                logger.error(f"[Recovery] Cycle and brief catch-up check failed: {e}")

            # Check news digest freshness
            try:
                is_stale = True
                async with get_session() as session:
                    last_digest = (
                        await session.execute(select(NewsDigest).order_by(NewsDigest.generated_at.desc()).limit(1))
                    ).scalar_one_or_none()

                    dt_now = datetime.now(timezone.utc)
                    if last_digest and last_digest.generated_at:
                        l_gen = last_digest.generated_at
                        if l_gen.tzinfo is None:
                            l_gen = l_gen.replace(tzinfo=timezone.utc)
                        is_stale = (dt_now - l_gen).total_seconds() > 4 * 3600

                if is_stale:
                    logger.info("[Recovery] News digest stale/missing, generating fresh digest...")
                    processor = NewsDigestProcessor(self.settings)
                    async with get_session() as digest_session:
                        await processor.create_news_digest(digest_session, hours_back=12)
            except Exception as e:
                logger.error(f"[Recovery] News digest recovery failed: {e}")

            # 3. Send recovery notification
            if self.telegram_bot:
                try:
                    await asyncio.sleep(30)  # Wait for Telegram bot to be ready
                    open_pos_count = 0
                    try:
                        if self.execution_service and getattr(self.execution_service, "mt5", None):
                            positions = await self.execution_service.mt5.get_open_positions()
                            open_pos_count = len(positions) if positions else 0
                    except Exception:
                        pass

                    await self.telegram_bot.send_notification(
                        f"[SYNC] *Agent Restarted Successfully*\n\n"
                        f"All systems online.\n"
                        f"Open positions synced: {open_pos_count}\n"
                        f"EA dead-man's switch: Reset\n\n"
                        f"Use /status to verify all systems."
                    )
                except Exception as e:
                    logger.debug(f"Recovery notification failed: {e}")
        finally:
            logger.info("[Recovery] Post-restart recovery complete")
            # Signal to position guards and cycle schedulers that startup recovery is complete.
            self._recovery_complete.set()
            warmup_evt = getattr(self, "_warmup_complete", None)
            if warmup_evt is not None:
                warmup_evt.set()
            logger.info("[Recovery] _recovery_complete and _warmup_complete events set — schedulers may now start.")


__all__ = ["AgentRecoveryMixin"]
