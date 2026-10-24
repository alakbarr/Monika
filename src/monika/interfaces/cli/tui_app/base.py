# ==============================================================================
# File: interfaces/cli/tui_app/base.py
# Description: Base mixin typing definitions for Monika TUI Terminal Dashboard
# ==============================================================================

"""
Base typing infrastructure for modular TUI dashboard mixins.
Provides static attribute and cross-mixin method declarations during type-checking
without introducing runtime overhead or metaclass conflicts.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    import asyncio
    from textual.app import App
    from monika.interfaces.cli.busy_input import BusyInputBuffer
    from monika.interfaces.cli.theme import ThemePack

    class _TuiMixinBase(App):
        api_url: str
        api_key: str
        refresh_interval: int
        standalone: bool
        theme_pack: ThemePack
        busy_buffer: BusyInputBuffer
        _start_time: float
        _seen_activity_ids: Set[Any]
        _seen_analysis_ids: Set[Any]
        _background_tasks: Set[asyncio.Task[Any]]
        _ws_status: str
        _ws_task: Optional[asyncio.Task[Any]]
        _quotes: Dict[str, float]
        _cached_tokens: int
        _input_tokens: int
        _output_tokens: int
        _cost_usd: float
        _context_used: int
        _context_max: int
        _cache_hit_rate: float
        _budget_tier: str
        _pnl_history: List[float]
        _vix_history: List[float]
        kill_switch: bool
        system_paused: bool
        auto_execute: bool
        daily_pnl: float
        daily_pnl_pct: Optional[float]
        vix: Optional[float]
        real_count: int
        paper_count: int
        _tabs_mounted: bool
        _refresh_lock: asyncio.Lock
        _inline_chat_agent: Optional[Any]
        terminal_width: int
        _positions_narrow_mode: bool

        # Cross-mixin methods
        def _is_input_focused(self) -> bool: ...
        def _refresh_status_bar(self) -> None: ...
        async def refresh_data(self) -> None: ...
        async def _fetch_overview_data(self) -> Dict[str, Any]: ...
        async def _fetch_data_from_db(self) -> Dict[str, Any]: ...
        def _update_ui_state(self, data: Dict[str, Any]) -> None: ...
        def _scheduled_refresh(self) -> None: ...
        async def refresh_benchmark_table(self) -> None: ...
        async def refresh_plugins_table(self) -> None: ...
        def action_install_plugin(self) -> None: ...
        def action_tab_plugins(self) -> None: ...
        async def action_pause(self) -> None: ...
        def action_kill(self) -> None: ...
        async def _execute_kill(self) -> None: ...
        async def action_chat(self) -> None: ...
        async def action_refresh(self) -> None: ...
        async def _send_inline_chat(self, prompt: str) -> None: ...
        async def _dispatch_steer(self, msg: str, mode: str = "steer") -> None: ...
        def set_theme(self, theme_name: str, persist: bool = True) -> bool: ...

else:

    class _TuiMixinBase:
        """Lightweight runtime base class."""

        pass
