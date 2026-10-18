# ==============================================================================
# File: bootstrap.py
# Description: Institutional Runtime Bootstrap (RFC 8305 Happy Eyeballs & Console Hardening)
# ==============================================================================

"""
Process Bootstrap & Network Hardening for Monika.

Features:
1. Windows UTF-8 console stream hardening & ANSI/VT processing.
2. True RFC 8305 Happy Eyeballs socket connection racer:
   Races IPv4 and IPv6 concurrently with non-blocking selectors and 250ms staggered launch.
   Eliminates 30-60s timeout freezes when IPv6 routes stall/blackhole on Windows networks.
3. Windows console flash guard:
   Stubs platform._syscmd_ver to prevent popup console windows when child workers spawn.
4. Urllib3 connection patcher hook for universal HTTP client acceleration.
"""

import errno
import itertools
import logging
import os
import platform
import selectors
import socket
import sys
import time
from typing import Any, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Bootstrap")


class BootstrapRuntime:
    """Encapsulates runtime bootstrap state and reset hooks."""

    _initialized: bool = False

    @classmethod
    def is_initialized(cls) -> bool:
        return cls._initialized

    @classmethod
    def set_initialized(cls, val: bool = True) -> None:
        cls._initialized = val

    @classmethod
    def reset(cls) -> None:
        cls._initialized = False


_DEFAULT_TIMEOUT: Any = getattr(socket, "_GLOBAL_DEFAULT_TIMEOUT", object())
_HAPPY_EYEBALLS_DELAY_S = 0.25


def race_dual_stack_socket(
    addr_info: List[Tuple[Any, ...]],
    effective_timeout: float = 15.0,
    source_address: Optional[Tuple[str, int]] = None,
) -> socket.socket:
    """
    True non-blocking RFC 8305 Happy Eyeballs socket connection racer.
    Interleaves IPv6 and IPv4 addresses and launches connection attempts
    with a 250ms stagger. Returns the first socket that connects successfully.
    """
    v4_targets = [ai for ai in addr_info if ai[0] == socket.AF_INET]
    v6_targets = [ai for ai in addr_info if ai[0] == socket.AF_INET6]

    # Interleave: IPv6 first, then IPv4, alternating
    interleaved: List[Tuple[Any, ...]] = []
    for pair in itertools.zip_longest(v6_targets, v4_targets):
        for item in pair:
            if item is not None:
                interleaved.append(item)

    if not interleaved:
        raise OSError("No valid socket targets found.")

    selector = selectors.DefaultSelector()
    in_flight_socks: List[socket.socket] = []
    start_time = time.monotonic()
    deadline = start_time + effective_timeout

    target_idx = 0
    next_launch_time = start_time
    last_err: Optional[Exception] = None

    try:
        while time.monotonic() < deadline and (target_idx < len(interleaved) or in_flight_socks):
            now = time.monotonic()

            # Launch next candidate if interval reached
            if target_idx < len(interleaved) and now >= next_launch_time:
                af, socktype, proto, canonname, sa = interleaved[target_idx]
                target_idx += 1
                next_launch_time = now + _HAPPY_EYEBALLS_DELAY_S

                try:
                    s = socket.socket(af, socktype, proto)
                    if source_address:
                        s.bind(source_address)
                    s.setblocking(False)

                    err = s.connect_ex(sa)
                    if err == 0:
                        # Instant connection (e.g. local or fast loopback)
                        s.setblocking(True)
                        for pending in in_flight_socks:
                            try:
                                pending.close()
                            except Exception:
                                pass
                        return s
                    elif err in (errno.EINPROGRESS, errno.EWOULDBLOCK, 10035):  # 10035 = WSAEWOULDBLOCK on Windows
                        selector.register(s, selectors.EVENT_WRITE, data=sa)
                        in_flight_socks.append(s)
                    else:
                        s.close()
                except Exception as ex:
                    last_err = ex

            # Wait for any socket to become writable
            timeout_poll = max(
                0.01,
                min(
                    next_launch_time - time.monotonic() if target_idx < len(interleaved) else 0.5,
                    deadline - time.monotonic(),
                ),
            )
            if in_flight_socks:
                events = selector.select(timeout=timeout_poll)
            else:
                time.sleep(timeout_poll)
                events = []

            for key, mask in events:
                sock = key.fileobj
                if not isinstance(sock, socket.socket):
                    continue
                selector.unregister(sock)
                if sock in in_flight_socks:
                    in_flight_socks.remove(sock)

                # Check if connection succeeded
                err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if err == 0:
                    # Winner found!
                    sock.setblocking(True)
                    if effective_timeout is not None:
                        sock.settimeout(effective_timeout)
                    # Close all losers
                    for loser in in_flight_socks:
                        try:
                            selector.unregister(loser)
                        except Exception:
                            pass
                        try:
                            loser.close()
                        except Exception:
                            pass
                    return sock
                else:
                    last_err = OSError(err, os.strerror(err) if hasattr(os, "strerror") else f"Socket error {err}")
                    try:
                        sock.close()
                    except Exception:
                        pass

        if last_err:
            raise last_err
        raise TimeoutError(f"RFC 8305 connection race timed out after {effective_timeout}s.")
    finally:
        selector.close()
        for remaining in in_flight_socks:
            try:
                remaining.close()
            except Exception:
                pass


def _install_happy_eyeballs() -> None:
    """Install RFC 8305 Dual-Stack Socket Connection Racer into socket.create_connection."""
    orig_create_connection = socket.create_connection

    def happy_eyeballs_create_connection(
        address,
        timeout=_DEFAULT_TIMEOUT,
        source_address=None,
        *args,
        **kwargs,
    ):
        host, port = address[:2]
        # Skip for numeric IP addresses or localhost
        if host in ("localhost", "127.0.0.1", "::1"):
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

        try:
            addr_info = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except Exception:
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

        effective_timeout = 60.0 if (timeout is _DEFAULT_TIMEOUT or timeout is None) else float(timeout)

        try:
            return race_dual_stack_socket(addr_info, effective_timeout=effective_timeout, source_address=source_address)
        except Exception:
            # Fallback to standard creation if racer raises an unexpected error
            return orig_create_connection(address, timeout, source_address, *args, **kwargs)

    socket.create_connection = happy_eyeballs_create_connection


def _install_console_guards() -> None:
    """Harden Windows console and prevent process flashing."""
    if sys.platform != "win32":
        return

    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"

    # Reconfigure streams if supported
    for s_name in ("stdout", "stderr"):
        stream = getattr(sys, s_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    # Stub platform._syscmd_ver on Windows to prevent console flashing on subprocess calls
    if hasattr(platform, "_syscmd_ver"):
        try:
            setattr(platform, "_syscmd_ver", lambda *a, **k: ("Windows", "10.0.0", "", ""))
        except Exception:
            pass


def bootstrap_runtime() -> None:
    """One-shot idempotent runtime bootstrapper."""
    if BootstrapRuntime.is_initialized():
        return

    _install_console_guards()
    _install_happy_eyeballs()

    BootstrapRuntime.set_initialized(True)
    logger.debug("Runtime bootstrap initialized: UTF-8 hardened, RFC 8305 Happy Eyeballs active.")


# Alias for backward compatibility
install_bootstrap_hardening = bootstrap_runtime


def build_application_container(
    settings: Optional[dict[str, Any]] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Build and configure the canonical ServiceContainer for Monika.
    Registers domain ports, infrastructure adapters, and application services.
    """
    from monika.core.container import ServiceContainer, get_container

    container = get_container()

    if settings is None:
        from monika.core.config.settings import load_all_config

        cfg = load_all_config()
    else:
        cfg = settings

    container.register("settings", cfg)

    # Core singletons and factories
    from monika.core.primitives.event_bus import get_event_bus

    container.register_factory("event_bus", lambda c: get_event_bus())

    from monika.core.telemetry.activity_logger import ActivityLogger

    container.register_factory("activity_logger", lambda c: ActivityLogger.get_instance())

    from monika.application.agent.task_registry import TaskRegistry

    container.register_factory("task_registry", lambda c: TaskRegistry.get_instance())

    # Infrastructure ports & adapters
    from monika.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork

    container.register_factory("unit_of_work", lambda c: SqlAlchemyUnitOfWork())

    from monika.infrastructure.brokers.mt5_client import MT5Client

    container.register_factory("mt5_client", lambda c: MT5Client(settings=c.get("settings", {})))

    from monika.domain.risk.risk_gate import RiskGate

    container.register_factory("risk_gate", lambda c: RiskGate(settings=c.get("settings", {})))

    # Canonical application services
    from monika.application.services.market_data_service import MarketDataService
    from monika.application.services.market_intel_service import MarketIntelService
    from monika.application.services.portfolio_service import PortfolioService
    from monika.application.services.system_status_service import SystemStatusService
    from monika.application.services.trading_service import TradingService

    container.register("portfolio_service", PortfolioService)
    container.register("trading_service", TradingService)
    container.register("market_data_service", MarketDataService)
    container.register("system_status_service", SystemStatusService)
    container.register("market_intel_service", MarketIntelService)

    # Execution service
    from monika.application.execution.execution_service import ExecutionService

    container.register_factory(
        "execution_service",
        lambda c: ExecutionService(
            settings=c.get("settings", {}),
            mt5_client=c.get("mt5_client"),
            risk_gate=c.get("risk_gate"),
        ),
    )

    from monika.infrastructure.credentials.credential_pool import CredentialPool

    container.register_factory("credential_pool", lambda c: CredentialPool.get_instance())

    from monika.application.harness.engine import PluginEngine

    container.register_factory(
        "plugin_engine",
        lambda c: PluginEngine(
            container=c,
            event_bus=c.get("event_bus"),
            task_registry=c.get("task_registry"),
        ),
    )

    # Wire domain risk ports with application and infrastructure providers
    try:
        from monika.domain.risk.ports import (
            register_adaptive_risk_policy_factory,
            register_broker_client_factory,
            register_copula_tail_risk_fitter,
            register_evidence_store_factory,
            register_evt_tail_calculator,
            register_regime_classifier,
            register_risk_data_provider_factory,
            register_risk_hook_emitter,
            register_strategy_factor_family_resolver,
            register_timesfm_alpha_calculator,
        )
        from monika.infrastructure.database.repositories.risk_repository import SqlAlchemyRiskRepository

        register_risk_data_provider_factory(
            lambda session=None, settings=None: SqlAlchemyRiskRepository(session=session, settings=settings)
        )

        from monika.application.analysis.calculators.regime_classifier import classify_market_regime

        register_regime_classifier(classify_market_regime)

        from monika.application.analysis.calculators.timesfm_alpha import TimesFMAlphaCalculator

        register_timesfm_alpha_calculator(TimesFMAlphaCalculator)

        from monika.application.analysis.calculators.evt_tail_calculator import fit_evt_peaks_over_threshold

        register_evt_tail_calculator(fit_evt_peaks_over_threshold)

        from monika.application.analysis.calculators.adaptive_policy import AdaptiveRiskPolicy

        register_adaptive_risk_policy_factory(lambda settings=None: AdaptiveRiskPolicy(settings=settings))

        from monika.application.analysis.strategies.evidence_store import EvidenceStore

        register_evidence_store_factory(lambda: EvidenceStore())

        from monika.application.analysis.calculators.copula_tail_risk import fit_clayton_copula

        register_copula_tail_risk_fitter(fit_clayton_copula)

        from monika.application.analysis.strategies.registry import StrategyRegistry

        def _resolve_family(strat_id: str | None) -> str:
            cls = StrategyRegistry.get_strategy(strat_id) if strat_id else None
            return str(getattr(cls, "factor_family", "trend")) if cls else "trend"

        register_strategy_factor_family_resolver(_resolve_family)

        from monika.application.execution.broker_registry import get_broker

        register_broker_client_factory(
            lambda s: get_broker(s.get("broker", {}).get("active_broker", "mt5") if isinstance(s, dict) else "mt5")
        )

        from monika.application.plugins.manager.manager import PluginHook, get_plugin_manager

        async def _emit_hook(name: str, **kw: Any) -> None:
            hook_enum = getattr(PluginHook, name, None)
            if hook_enum:
                await get_plugin_manager().emit(hook_enum, **kw)

        register_risk_hook_emitter(_emit_hook)
    except Exception as e:
        logger.warning(f"Error wiring domain risk ports at bootstrap: {e}")

    if overrides:
        for k, v in overrides.items():
            container.register(k, v)

    return container


def bootstrap_application(
    settings: Optional[dict[str, Any]] = None,
    overrides: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Unified one-shot application composition root.
    Hardens runtime/networking and configures the canonical ServiceContainer.
    """
    bootstrap_runtime()
    container = build_application_container(settings=settings, overrides=overrides)
    return container


__all__ = [
    "BootstrapRuntime",
    "race_dual_stack_socket",
    "bootstrap_runtime",
    "install_bootstrap_hardening",
    "build_application_container",
    "bootstrap_application",
]
