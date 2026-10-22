"""
Connection lifecycle, priority queue worker, and gateway failover logic for MT5Client.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import functools
import os
from typing import Any, Optional

from dotenv import load_dotenv

from .base import MT5MixinBase
from .constants import (
    MT5ProfileMismatchError,
    PRIORITY_BACKGROUND,
    PRIORITY_CRITICAL,
    PRIORITY_STANDARD,
    logger,
)
from .primitives import _connect, _disconnect, _get_account_info, _is_connected

load_dotenv()


class MT5ConnectionMixin(MT5MixinBase):
    """Mixin handling connection lifecycle, worker queues, and secondary gateway failover."""

    def __init__(self, settings: Optional[dict[str, Any]] = None):
        self.settings = settings or {}

        # Centralized credential resolution: settings -> CredentialVault -> os.getenv
        from monika.core.security.credential_vault import vault

        def _resolve_cred(setting_path: list[str], env_var: str, default: Any = "") -> Any:
            # 1. settings dict lookup by nested key path
            cur: Any = self.settings
            for key in setting_path:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    cur = None
                    break
            if cur is not None and cur != "":
                return cur
            # 2. CredentialVault lookup (handles OS vault, encrypted file vault, env)
            vault_val = vault.get_secret(env_var)
            if vault_val is not None and vault_val != "":
                return vault_val
            # 3. Fallback to os.getenv
            return os.getenv(env_var, default)

        raw_acc = _resolve_cred(["execution", "mt5_account"], "MT5_ACCOUNT", 0)
        try:
            self.account = int(raw_acc)
        except ValueError, TypeError:
            self.account = 0

        self.password = str(_resolve_cred(["execution", "mt5_password"], "MT5_PASSWORD", ""))
        self.server = str(_resolve_cred(["execution", "mt5_server"], "MT5_SERVER", ""))
        self.path = str(
            _resolve_cred(
                ["execution", "mt5_path"],
                "MT5_PATH",
                "C:/Program Files/MetaTrader 5/terminal64.exe",
            )
        )

        # Secondary Gateway Configuration
        raw_sec_acc = _resolve_cred(["execution", "mt5_secondary_account"], "MT5_SECONDARY_ACCOUNT", 0)
        try:
            self.secondary_account = int(raw_sec_acc)
        except ValueError, TypeError:
            self.secondary_account = 0

        self.secondary_password = str(
            _resolve_cred(["execution", "mt5_secondary_password"], "MT5_SECONDARY_PASSWORD", "")
        )
        self.secondary_server = str(_resolve_cred(["execution", "mt5_secondary_server"], "MT5_SECONDARY_SERVER", ""))
        self.secondary_path = str(_resolve_cred(["execution", "mt5_secondary_path"], "MT5_SECONDARY_PATH", ""))
        self.active_gateway: str = "primary"  # "primary" or "secondary"
        self.notifier: Optional[Any] = None

        self._connected = False
        self._timeframe_map: dict[str, int] = {}
        self.paper_trading = self.settings.get("paper_trading", {}).get("enabled", True)
        # Dedicated single-thread executor for thread-affine MetaTrader5 COM API calls
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
        self._priority_queue: Optional[asyncio.PriorityQueue[Any]] = None
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._queue_counter: int = 0
        # Sub-second micro-batch tick poller state (MEDIUM-5)
        self._tick_poller_thread: Optional[Any] = None
        self._tick_poller_stop_event: Optional[Any] = None
        self._last_ticks: dict[str, tuple[float, float]] = {}
        self._poller_interval: float = float(
            self.settings.get("trading", {}).get("schedule", {}).get("tick_poller_interval_seconds", 0.25)
        )
        self._broker_utc_offset_seconds: Optional[int] = None
        # 2-Phase Order Commit Protocol Manager
        from monika.domain.risk.pending_action import PendingActionManager

        self.pending_action_manager = PendingActionManager()
        self.mt5_fail_count = 0
        self._trade_mode: Optional[int] = None

    def get_current_gateway_params(self) -> tuple[str, int, str, str]:
        """Mengembalikan parameter koneksi untuk gateway yang sedang aktif."""
        if self.active_gateway == "secondary" and self.secondary_account > 0:
            return (
                self.secondary_path or self.path,
                self.secondary_account,
                self.secondary_password,
                self.secondary_server,
            )
        return self.path, self.account, self.password, self.server

    # ------------------------------------------------------------------
    # Connection lifecycle & Redundant Failover
    # ------------------------------------------------------------------

    async def connect(self, timeout: float = 15.0) -> bool:
        """Inisialisasi dan login ke MT5 (menggunakan gateway aktif). Mengembalikan True jika berhasil."""
        if not hasattr(self, "_executor") or self._executor is None or getattr(self._executor, "_shutdown", False):
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
        curr_path, curr_acc, curr_pass, curr_serv = self.get_current_gateway_params()
        expected_trade_mode = self.settings.get("execution", {}).get("expected_trade_mode") or os.getenv(
            "MT5_EXPECTED_TRADE_MODE"
        )
        try:
            success = await self._run(
                _connect, curr_path, curr_acc, curr_pass, curr_serv, expected_trade_mode, timeout=timeout
            )
            self._connected = success
            if success:
                try:
                    from .primitives import _LAST_CONNECTED_TRADE_MODE

                    if _LAST_CONNECTED_TRADE_MODE is not None:
                        self._trade_mode = _LAST_CONNECTED_TRADE_MODE
                except Exception:
                    pass
                try:
                    from monika.core.telemetry.metrics_exporter import metrics

                    metrics.set_gauge("active_gateway_is_primary", 1.0 if self.active_gateway == "primary" else 0.0)
                    metrics.set_gauge("mt5_primary_connected", 1.0 if self.active_gateway == "primary" else 0.0)
                    metrics.set_gauge("mt5_secondary_connected", 1.0 if self.active_gateway == "secondary" else 0.0)
                except Exception:
                    pass
            return success
        except MT5ProfileMismatchError as pe:
            logger.critical(f"MT5 [{self.active_gateway.upper()}] Profile Mismatch: {pe}")
            self._connected = False
            raise
        except (ConnectionError, TimeoutError) as ce:
            logger.error(f"MT5 [{self.active_gateway.upper()}] Connection failed or timed out: {ce}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"MT5 [{self.active_gateway.upper()}] Init unexpectedly failed: {e}")
            self._connected = False
            return False

    async def failover_to_secondary(self) -> bool:
        """Berpindah ke gateway MT5 sekunder saat gateway primer tidak dapat dihubungi."""
        if not self.secondary_account or not self.secondary_server:
            logger.warning("Failover to secondary MT5 gateway requested, but secondary credentials are not configured.")
            return False
        logger.warning(f"Initiating MT5 Failover: Switching from {self.active_gateway} -> secondary gateway...")
        await self.disconnect()
        self.active_gateway = "secondary"
        success = await self.connect()
        if success:
            logger.warning("MT5 Failover SUCCESSFUL: Operating on secondary terminal gateway.")
            if self.notifier is not None:
                try:
                    asyncio.create_task(
                        self.notifier.send_warning(
                            "[DARURAT] <b>MT5 FAILOVER</b>: System switched to secondary MT5 gateway."
                        )
                    )
                except Exception:
                    pass
        else:
            logger.error("MT5 Failover FAILED: Could not establish connection to secondary MT5 gateway.")
        return success

    async def fallback_to_primary(self) -> bool:
        """Kembali ke gateway MT5 primer saat sudah pulih."""
        logger.info("Attempting fallback from secondary to primary MT5 gateway...")
        await self.disconnect()
        self.active_gateway = "primary"
        success = await self.connect()
        if success:
            logger.info("MT5 Fallback SUCCESSFUL: Restored primary gateway connection.")
            if self.notifier is not None:
                try:
                    asyncio.create_task(
                        self.notifier.send_info("[INFO] <b>MT5 RESTORED</b>: System returned to primary MT5 gateway.")
                    )
                except Exception:
                    pass
        else:
            logger.warning("MT5 Fallback failed: Primary gateway still down, reverting to secondary.")
            self.active_gateway = "secondary"
            await self.connect()
        return success

    @property
    def trade_mode(self) -> Optional[int]:
        """MT5 account trade mode: 0=DEMO, 1=CONTEST, 2=REAL."""
        return getattr(self, "_trade_mode", None)

    @property
    def is_demo_account(self) -> bool:
        """True if MT5 account is verified to be a DEMO account (trade_mode == 0)."""
        return getattr(self, "_trade_mode", None) == 0

    async def disconnect(self) -> None:
        """Tutup koneksi MT5."""
        self.stop_tick_poller()
        try:
            await self._run(_disconnect, priority=PRIORITY_CRITICAL, timeout=3.0)
        except Exception:
            pass
        finally:
            self._connected = False
            self._trade_mode = None
            self._broker_utc_offset_seconds = None
            queue = self._priority_queue
            self._priority_queue = None
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError, Exception:
                    pass
            if queue is not None:
                while not queue.empty():
                    try:
                        item = queue.get_nowait()
                        fut = item[-1]
                        if hasattr(fut, "done") and not fut.done() and not fut.cancelled():
                            fut.set_exception(ConnectionError("MT5 disconnected"))
                    except Exception:
                        break
            try:
                if hasattr(self, "_executor") and self._executor:
                    self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        logger.info(f"MT5 ({self.active_gateway}) disconnected.")

    async def is_connected(self) -> bool:
        """Periksa apakah terminal MT5 masih hidup."""
        if not getattr(self, "_connected", False):
            return False
        connected = await self._run(_is_connected)
        if not connected:
            self._connected = False
        return connected

    async def ensure_connected(self) -> bool:
        """Cek koneksi dan lakukan reconnect dengan auto-failover ke gateway sekunder jika perlu."""
        if await self.is_connected():
            if getattr(self, "mt5_fail_count", 0) > 0:
                self.mt5_fail_count = 0
                try:
                    from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                    await AgentNotifier().send_info("[OK] <b>MT5 Reconnected</b>")
                except Exception:
                    pass
            return True

        logger.info(f"MT5 ({self.active_gateway}) connection lost, attempting to reconnect...")

        max_attempts = 2 if self.paper_trading else 4
        delay = 2.0

        for attempt in range(1, max_attempts + 1):
            if await self.connect():
                logger.info(f"MT5 ({self.active_gateway}) reconnected successfully on attempt {attempt}")
                self.mt5_fail_count = 0
                return True
            logger.warning(f"MT5 reconnect attempt {attempt} failed, waiting {delay}s...")
            await asyncio.sleep(delay)
            delay = min(20.0, delay * 2)

        # Jika primary gagal dan secondary terkonfigurasi, coba failover
        if self.active_gateway == "primary" and self.secondary_account > 0:
            logger.warning("Primary MT5 reconnect exhausted. Triggering automatic failover to secondary gateway...")
            return await self.failover_to_secondary()

        if self.paper_trading:
            logger.warning(
                "MT5 auto-reconnect failed. Operating in offline mode because paper_trading=True. Continuing without MT5."
            )
            return False

        logger.error("MT5 auto-reconnect failed after maximum attempts.")
        self.mt5_fail_count = getattr(self, "mt5_fail_count", 0) + 1

        if self.mt5_fail_count % 6 == 1:
            try:
                from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

                notifier = AgentNotifier()
                await notifier.send_critical(
                    f"[DARURAT] <b>MT5 CONNECTION FAILED</b>\n"
                    f"Cannot reconnect to MetaTrader5 after max attempts.\n"
                    f"(Fail count: {self.mt5_fail_count}).\n"
                    f"Please check MT5 terminal immediately!"
                )
            except Exception as notif_err:
                logger.error(f"Failed to send MT5 connection critical alert: {notif_err}")
        return False

    def _ensure_worker(self) -> asyncio.PriorityQueue[Any]:
        """Menginisialisasi asyncio PriorityQueue dan worker task secara lazy."""
        loop = asyncio.get_running_loop()
        if not hasattr(self, "_executor") or self._executor is None or getattr(self._executor, "_shutdown", False):
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="MT5Worker")
        if self._priority_queue is None or self._worker_task is None or self._worker_task.done():
            self._priority_queue = asyncio.PriorityQueue()
            self._worker_task = loop.create_task(self._priority_worker_loop())
        return self._priority_queue

    async def _priority_worker_loop(self) -> None:
        """Dedicated worker loop yang mengambil tugas dari PriorityQueue dan menjalankannya di STA ThreadPoolExecutor."""
        while True:
            queue = self._priority_queue
            if queue is None:
                break
            try:
                priority, counter, fn, args, kwargs, future = await queue.get()
            except asyncio.CancelledError, GeneratorExit:
                break
            except Exception as ex:
                logger.error(f"[MT5PriorityWorker] Queue retrieval error: {ex}")
                continue

            if future.cancelled():
                try:
                    queue.task_done()
                except Exception:
                    pass
                continue

            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(self._executor, functools.partial(fn, *args, **kwargs))
                if not future.cancelled() and not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if not future.cancelled() and not future.done():
                    future.set_exception(ConnectionError("MT5 disconnected"))
                try:
                    queue.task_done()
                except Exception:
                    pass
                break
            except Exception as exc:
                if not future.cancelled() and not future.done():
                    future.set_exception(exc)
            finally:
                try:
                    queue.task_done()
                except Exception:
                    pass

    def _resolve_priority(self, fn: Any, explicit_priority: Optional[int] = None) -> int:
        """Menentukan tingkat prioritas eksekusi MT5 (0=Critical, 5=Standard, 10=Background)."""
        if explicit_priority is not None:
            return explicit_priority
        fn_name = getattr(fn, "__name__", "")
        if fn_name in (
            "_place_order",
            "place_order",
            "_modify_position",
            "modify_position",
            "_modify_order",
            "modify_order",
            "_close_position",
            "close_position",
            "_close_all_positions",
            "close_all_positions",
            "emergency_close_all",
            "kill_switch",
            "_disconnect",
            "disconnect",
        ):
            return PRIORITY_CRITICAL
        if fn_name in ("_copy_rates_from_pos", "_copy_rates_range", "copy_rates_range", "fetch_and_save_all"):
            return PRIORITY_BACKGROUND
        return PRIORITY_STANDARD

    async def _run(
        self,
        fn: Any,
        *args: Any,
        priority: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """Jalankan fungsi sinkron MT5 via asyncio PriorityQueue di atas dedicated single-thread executor."""
        loop = asyncio.get_running_loop()
        queue = self._ensure_worker()
        self._queue_counter += 1
        eff_priority = self._resolve_priority(fn, priority)
        future = loop.create_future()

        await queue.put((eff_priority, self._queue_counter, fn, args, kwargs, future))

        if timeout is not None:
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            except asyncio.TimeoutError:
                future.cancel()
                fn_name = getattr(fn, "__name__", str(fn))
                logger.warning(f"[MT5Client] Operation {fn_name} exceeded timeout {timeout}s; future cancelled.")
                raise TimeoutError(f"MT5 operation {fn_name} timed out")
        return await future
