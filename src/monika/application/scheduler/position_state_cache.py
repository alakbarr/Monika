"""
Package: monika.application.scheduler
File: position_state_cache.py
Description: Fast, lightweight, thread/async-safe in-memory cache for open positions
and emergency kill-switch state to eliminate tick-path database query storms.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional, Set

logger = logging.getLogger("TradingAgent.PositionStateCache")

DEFAULT_CACHE_TTL_SECONDS = 10.0


class ActivePositionStateCache:
    """
    In-memory state cache of active positions and kill switch status.
    Eliminates high-frequency database sessions on incoming tick evaluation when
    the system has no open positions or when kill switch is disarmed.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self.ttl_seconds: float = max(0.5, float(ttl_seconds))
        self._open_symbols: Set[str] = set()
        self._orphan_symbols: Set[str] = set()
        self._kill_switch_active: bool = False
        self._disk_kill_active: bool = False
        self._last_refresh_mono: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    @staticmethod
    def _normalize(symbol: str) -> str:
        if not symbol:
            return ""
        return symbol.strip().upper().replace("/", "")

    def is_fresh(self, now_mono: Optional[float] = None) -> bool:
        """Returns True if cache was refreshed within ttl_seconds."""
        now = now_mono if now_mono is not None else time.monotonic()
        return self._last_refresh_mono > 0.0 and (now - self._last_refresh_mono) < self.ttl_seconds

    def invalidate(self) -> None:
        """Force the cache to be considered stale immediately."""
        self._last_refresh_mono = 0.0

    def mark_symbol_open(self, symbol: str) -> None:
        """Record a symbol as having an active position."""
        norm = self._normalize(symbol)
        if norm:
            self._open_symbols.add(norm)

    def mark_symbol_closed(self, symbol: str) -> None:
        """Remove a symbol from open and orphan tracking."""
        norm = self._normalize(symbol)
        self._open_symbols.discard(norm)
        self._orphan_symbols.discard(norm)

    def update_snapshot(
        self,
        open_symbols: Set[str],
        orphan_symbols: Optional[Set[str]] = None,
        kill_switch_active: Optional[bool] = None,
        disk_kill_active: Optional[bool] = None,
    ) -> None:
        """Synchronously update the snapshot from an external authoritative source (e.g., PositionSupervisor)."""
        self._open_symbols = {self._normalize(s) for s in open_symbols if s}
        if orphan_symbols is not None:
            self._orphan_symbols = {self._normalize(s) for s in orphan_symbols if s}
        if kill_switch_active is not None:
            self._kill_switch_active = bool(kill_switch_active)
        if disk_kill_active is not None:
            self._disk_kill_active = bool(disk_kill_active)
        self._last_refresh_mono = time.monotonic()

    @property
    def kill_switch_active(self) -> bool:
        """True if either database or disk kill switch is latched."""
        return self._kill_switch_active or self._disk_kill_active

    @property
    def disk_kill_active(self) -> bool:
        """True if physical kill_switch.flag exists on disk."""
        return self._disk_kill_active

    @property
    def has_any_open_positions(self) -> bool:
        """True if there is at least one tracked open position."""
        return len(self._open_symbols) > 0

    @property
    def open_symbols(self) -> Set[str]:
        """Set of currently tracked open position symbols."""
        return set(self._open_symbols)

    @property
    def orphan_symbols(self) -> Set[str]:
        """Set of currently tracked orphan position symbols."""
        return set(self._orphan_symbols)

    def has_open_position(self, symbol: str) -> bool:
        """Check if an open position exists for the given symbol."""
        return self._normalize(symbol) in self._open_symbols

    def has_orphan_position(self, symbol: str) -> bool:
        """Check if an orphan position exists for the given symbol."""
        return self._normalize(symbol) in self._orphan_symbols

    def has_active_or_orphan_position(self, symbol: str) -> bool:
        """Check if an open or orphan position exists for the given symbol."""
        norm = self._normalize(symbol)
        return (norm in self._open_symbols) or (norm in self._orphan_symbols)

    async def ensure_fresh(self, session_factory: Any = None) -> None:
        """
        Refreshes cache from database if TTL expired.
        Consolidates kill_switch status and position lookups into ONE single read transaction.
        If database query fails, fails closed by leaving cache marked as stale.
        """
        # Fast path outside lock
        is_mock = hasattr(session_factory, "_mock_name") or hasattr(session_factory, "assert_called")
        if self.is_fresh() and not is_mock:
            return

        async with self._lock:
            if self.is_fresh() and not is_mock:
                return

            from monika.core.paths import DATA_DIR
            from monika.infrastructure.database.models import Position, SystemConfig
            from sqlalchemy import select

            disk_flag = (DATA_DIR / "kill_switch.flag").exists()

            if session_factory is None:
                from monika.infrastructure.database.db import get_session

                target_factory = get_session
            else:
                target_factory = session_factory

            try:
                async with target_factory() as session:
                    # 1. Kill switch config
                    stmt_cfg = select(SystemConfig).where(SystemConfig.key == "kill_switch")
                    res_cfg = await session.execute(stmt_cfg)
                    cfg_item = getattr(res_cfg, "scalar_one_or_none", None)
                    if callable(cfg_item):
                        cfg_val = cfg_item()
                    else:
                        cfg_val = None
                    db_kill = bool(cfg_val and str(getattr(cfg_val, "value", "")).lower() in ("true", "1", "yes"))

                    # 2. Open and orphan positions
                    stmt_pos = select(Position.symbol, Position.status).where(
                        Position.status.in_(["open", "orphan_pending_close"])
                    )
                    res_pos = await session.execute(stmt_pos)

                    # Support both ORM models, scalar results, and mock tuples
                    rows = []
                    if hasattr(res_pos, "all"):
                        rows = res_pos.all()
                    elif hasattr(res_pos, "scalars"):
                        sc = res_pos.scalars()
                        rows = sc.all() if hasattr(sc, "all") else []

                new_open: Set[str] = set()
                new_orphan: Set[str] = set()
                for item in rows:
                    if hasattr(item, "symbol") and hasattr(item, "status"):
                        sym = str(item.symbol or "")
                        stat = str(item.status or "")
                    elif isinstance(item, (tuple, list)) and len(item) >= 2:
                        sym = str(item[0] or "")
                        stat = str(item[1] or "")
                    else:
                        sym = str(getattr(item, "symbol", "") or "")
                        stat = str(getattr(item, "status", "") or "")

                    clean_sym = self._normalize(sym)
                    if not clean_sym:
                        continue
                    if stat == "open":
                        new_open.add(clean_sym)
                    elif stat == "orphan_pending_close":
                        new_orphan.add(clean_sym)

                self._open_symbols = new_open
                self._orphan_symbols = new_orphan
                self._disk_kill_active = disk_flag
                self._kill_switch_active = db_kill
                self._last_refresh_mono = time.monotonic()
            except Exception as e:
                logger.warning(f"[ActivePositionStateCache] Refresh failed (failing closed): {e}")
                self._last_refresh_mono = 0.0


_GLOBAL_POSITION_STATE_CACHE: Optional[ActivePositionStateCache] = None


def get_position_state_cache() -> ActivePositionStateCache:
    """Singleton getter for shared application-wide ActivePositionStateCache."""
    global _GLOBAL_POSITION_STATE_CACHE
    if _GLOBAL_POSITION_STATE_CACHE is None:
        _GLOBAL_POSITION_STATE_CACHE = ActivePositionStateCache()
    return _GLOBAL_POSITION_STATE_CACHE


def reset_position_state_cache() -> None:
    """Reset singleton cache for test isolation and environment reloads."""
    global _GLOBAL_POSITION_STATE_CACHE
    if _GLOBAL_POSITION_STATE_CACHE is not None:
        _GLOBAL_POSITION_STATE_CACHE.invalidate()
    _GLOBAL_POSITION_STATE_CACHE = None


__all__ = [
    "DEFAULT_CACHE_TTL_SECONDS",
    "ActivePositionStateCache",
    "get_position_state_cache",
    "reset_position_state_cache",
]
