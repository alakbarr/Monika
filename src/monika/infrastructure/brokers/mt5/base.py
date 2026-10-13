"""
Base mixin contract and typing protocol for MT5Client components.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession


class MT5MixinBase:
    """Type contract and shared base attributes for MT5Client mixins."""

    settings: dict[str, Any]
    account: int
    password: str
    server: str
    path: str
    secondary_account: int
    secondary_password: str
    secondary_server: str
    secondary_path: str
    active_gateway: str
    notifier: Optional[Any]
    _connected: bool
    _timeframe_map: dict[str, int]
    paper_trading: bool
    _executor: ThreadPoolExecutor
    _priority_queue: Optional[asyncio.PriorityQueue[Any]]
    _worker_task: Optional[asyncio.Task[None]]
    _queue_counter: int
    _tick_poller_thread: Optional[Any]
    _tick_poller_stop_event: Optional[Any]
    _last_ticks: dict[str, tuple[float, float]]
    _poller_interval: float
    _broker_utc_offset_seconds: Optional[int]
    pending_action_manager: Any
    mt5_fail_count: int

    async def _run(
        self,
        fn: Any,
        *args: Any,
        priority: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Any: ...

    async def ensure_connected(self) -> bool: ...

    async def is_connected(self) -> bool: ...

    async def connect(self, timeout: float = 15.0) -> bool: ...

    async def disconnect(self) -> None: ...

    def stop_tick_poller(self) -> None: ...

    def _timeframe_to_mt5(self, timeframe: str) -> int: ...

    def _resolve_timeframe(self, tf_str: str) -> Optional[int]: ...

    def get_current_gateway_params(self) -> tuple[str, int, str, str]: ...

    async def get_open_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]: ...

    async def get_orders(self, symbol: Optional[str] = None) -> list[dict[str, Any]]: ...

    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> dict[str, Any]: ...

    async def close_all_positions(
        self,
        symbol: Optional[str] = None,
        comment: str = "Emergency close all",
    ) -> dict[str, Any]: ...

    async def get_latest_tick(self, symbol: str) -> Any: ...

    async def get_spread(self, symbol: str) -> dict[str, Any]: ...

    async def get_symbol_info(self, symbol: str) -> Optional[dict[str, Any]]: ...

    async def get_account_info(self) -> Optional[dict[str, Any]]: ...

    async def get_rates(
        self,
        symbol: str,
        timeframe: str = "H1",
        count: int = 100,
    ) -> pd.DataFrame: ...

    async def copy_rates_range(
        self,
        symbol: str,
        timeframe: str,
        date_from: Any,
        date_to: Any,
        chunk_days: int = 7,
    ) -> Optional[pd.DataFrame]: ...
