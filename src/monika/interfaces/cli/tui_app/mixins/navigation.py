# ==============================================================================
# File: interfaces/cli/tui_app/mixins/navigation.py
# Description: Tab navigation and theme switching mixin for Monika TUI
# ==============================================================================

import asyncio
import logging

from textual import events
from textual.widgets import DataTable, TabbedContent

from monika.interfaces.cli.theme import THEMES, build_tui_css
from monika.interfaces.cli.tui_app.base import _TuiMixinBase

logger = logging.getLogger("TradingAgent.TUI")


class NavigationMixin(_TuiMixinBase):
    """Mixin handling tab navigation, responsive resize, and theme switches."""

    def _is_input_focused(self) -> bool:
        """Check if any input or textarea currently has keyboard focus."""
        try:
            from textual.widgets import Input, TextArea

            return isinstance(self.focused, (Input, TextArea))
        except ImportError:
            from textual.widgets import Input

            return isinstance(self.focused, Input)

    def on_resize(self, event: events.Resize) -> None:
        """Handle dynamic terminal resize using progressive width budget."""
        self.terminal_width = event.size.width
        self._refresh_status_bar()
        new_narrow = event.size.width < 90
        try:
            panels = self.query_one("#main_panels")
            if event.size.width < 100:
                panels.add_class("stacked-panels")
            else:
                panels.remove_class("stacked-panels")
        except Exception:
            pass

        if getattr(self, "_positions_narrow_mode", None) != new_narrow:
            self._positions_narrow_mode = new_narrow
            try:
                table = self.query_one("#positions_table", DataTable)
                table.clear(columns=True)
                if new_narrow:
                    table.add_columns("Symbol", "Side", "Lots", "Entry", "PnL")
                else:
                    table.add_columns("ID", "Type", "Symbol", "Side", "Lots", "Entry", "SL", "TP", "PnL")
                if self.is_running:
                    asyncio.create_task(self.refresh_data())
            except Exception:
                pass

    def action_switch_tab(self) -> None:
        """Switch to next tab."""
        if self._is_input_focused():
            return
        tabs = self.query_one("#main_tabs", TabbedContent)
        tab_ids = [
            "tab_overview",
            "tab_analysis",
            "tab_signals",
            "tab_risk",
            "tab_performance",
            "tab_market",
            "tab_plugins",
            "tab_benchmark",
            "tab_chat",
        ]
        curr = tabs.active
        if curr in tab_ids:
            next_idx = (tab_ids.index(curr) + 1) % len(tab_ids)
            tabs.active = tab_ids[next_idx]

    def action_prev_tab(self) -> None:
        """Switch to previous tab."""
        if self._is_input_focused():
            return
        tabs = self.query_one("#main_tabs", TabbedContent)
        tab_ids = [
            "tab_overview",
            "tab_analysis",
            "tab_signals",
            "tab_risk",
            "tab_performance",
            "tab_market",
            "tab_plugins",
            "tab_benchmark",
            "tab_chat",
        ]
        curr = tabs.active
        if curr in tab_ids:
            prev_idx = (tab_ids.index(curr) - 1) % len(tab_ids)
            tabs.active = tab_ids[prev_idx]

    def action_tab_overview(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_overview"

    def action_tab_analysis(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_analysis"

    def action_tab_signals(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_signals"

    def action_tab_risk(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_risk"

    def action_tab_performance(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_performance"

    def action_tab_market(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_market"

    def action_tab_chat(self) -> None:
        if self._is_input_focused():
            return
        self.query_one("#main_tabs", TabbedContent).active = "tab_chat"

    def action_tab_plugins(self) -> None:
        if self._is_input_focused():
            return
        try:
            self.query_one("#main_tabs", TabbedContent).active = "tab_plugins"
            asyncio.create_task(self.refresh_plugins_table())
        except Exception:
            pass

    def action_tab_benchmark(self) -> None:
        if self._is_input_focused():
            return
        try:
            self.query_one("#main_tabs", TabbedContent).active = "tab_benchmark"
            asyncio.create_task(self.refresh_benchmark_table())
        except Exception:
            pass

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Provide visual notification and audit log when user switches tabs."""
        if not getattr(self, "_tabs_mounted", False):
            self._tabs_mounted = True
            return
        label = event.tab.label_text if hasattr(event.tab, "label_text") and event.tab.label_text else "TAB"
        if event.tab.id == "tab_plugins":
            asyncio.create_task(self.refresh_plugins_table())
        try:
            self.notify(f"Switched to [{label.upper()}] workspace", title="MONIKA TUI", timeout=1.5)
        except Exception:
            pass

    def set_theme(self, theme_name: str, persist: bool = True) -> bool:
        """Switch current UI theme pack, dynamically reload styles, and optionally persist."""
        if theme_name not in THEMES:
            return False
        self.theme_pack = THEMES[theme_name]
        try:
            new_css = build_tui_css(self.theme_pack)
            if hasattr(self, "stylesheet") and hasattr(self.stylesheet, "add_source"):
                self.stylesheet.add_source(new_css)
                if hasattr(self, "refresh_css"):
                    self.refresh_css()
        except Exception as e:
            logger.debug(f"[TUI] Dynamic CSS reload: {e}")

        if persist:
            try:
                from monika.interfaces.cli.theme import persist_theme_to_settings

                persist_theme_to_settings(theme_name)
            except Exception as pe:
                logger.debug(f"[TUI] Persist theme error: {pe}")
        return True
