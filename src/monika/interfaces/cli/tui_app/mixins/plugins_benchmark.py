# ==============================================================================
# File: interfaces/cli/tui_app/mixins/plugins_benchmark.py
# Description: Plugins and LLM benchmark leaderboard mixin for Monika TUI
# ==============================================================================

import asyncio
import logging
from typing import Any

import aiohttp
from textual.widgets import DataTable, TabbedContent

from monika.interfaces.cli.tui_app.base import _TuiMixinBase

logger = logging.getLogger("TradingAgent.TUI")


class PluginsBenchmarkMixin(_TuiMixinBase):
    """Mixin handling plugins registry management and benchmark leaderboard rendering."""

    async def refresh_benchmark_table(self) -> None:
        """Fetch and populate benchmark leaderboard DataTable."""
        try:
            bench_table = self.query_one("#benchmark_table", DataTable)
            if self.standalone:
                from sqlalchemy import desc, select

                from monika.application.benchmark.db_models import BenchmarkResult, BenchmarkRun
                from monika.infrastructure.database.db import get_session

                async with get_session() as session:
                    latest = (
                        await session.execute(select(BenchmarkRun).order_by(desc(BenchmarkRun.started_at)).limit(1))
                    ).scalar_one_or_none()
                    if not latest:
                        return
                    rows = (
                        (await session.execute(select(BenchmarkResult).where(BenchmarkResult.run_id == latest.id)))
                        .scalars()
                        .all()
                    )

                    stats: dict[str, dict[str, Any]] = {}
                    for r in rows:
                        m = r.model_name
                        if m not in stats:
                            stats[m] = {"tasks": 0, "passed": 0, "score": 0.0, "cost": 0.0, "lat": 0.0}
                        st = stats[m]
                        st["tasks"] += 1
                        st["cost"] += r.cost_usd or 0.0
                        st["lat"] += r.latency_s or 0.0
                        if not r.error and r.overall_score:
                            st["score"] += r.overall_score
                            if r.overall_score >= 0.70:
                                st["passed"] += 1

                    bench_table.clear()
                    sorted_stats = sorted(
                        stats.items(), key=lambda x: x[1]["score"] / max(x[1]["tasks"], 1), reverse=True
                    )
                    for idx, (m, st) in enumerate(sorted_stats, 1):
                        cnt = max(st["tasks"], 1)
                        avg_sc = st["score"] / cnt
                        pass_rt = (st["passed"] / cnt) * 100.0
                        avg_lat = st["lat"] / cnt
                        avg_cst = st["cost"] / cnt
                        bench_table.add_row(
                            f"#{idx}",
                            m,
                            f"{avg_sc * 100:.1f}%",
                            f"{pass_rt:.1f}%",
                            f"{avg_lat:.2f}s",
                            f"${avg_cst:.4f}",
                            str(st["tasks"]),
                        )
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.api_url}/api/benchmark/leaderboard") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            leaders = data.get("leaderboard", [])
                            bench_table.clear()
                            for idx, l in enumerate(leaders, 1):
                                bench_table.add_row(
                                    f"#{idx}",
                                    l.get("model_name", "N/A"),
                                    f"{(l.get('avg_score', 0) * 100):.1f}%",
                                    f"{l.get('pass_rate_pct', 0):.1f}%",
                                    f"{l.get('avg_latency_s', 0):.2f}s",
                                    f"${l.get('avg_cost_usd', 0):.4f}",
                                    str(l.get("total_tasks", 0)),
                                )
        except Exception as ex:
            logger.debug(f"Error refreshing benchmark table in TUI: {ex}")

    async def refresh_plugins_table(self) -> None:
        """Fetch unified plugin statuses and refresh DataTable."""
        try:
            from monika.application.harness.installer import list_all_plugins_status

            plugins = list_all_plugins_status()
            table = self.query_one("#plugins_table", DataTable)
            table.clear()
            for p in plugins:
                if p["enabled"]:
                    status_styled = "[bold green]ACTIVE[/]"
                elif p["status"].startswith("DEGRADED"):
                    status_styled = "[bold yellow]DEGRADED[/]"
                else:
                    status_styled = "[dim]DISABLED[/]"

                desc_short = p["description"][:45] + ("..." if len(p["description"]) > 45 else "")
                table.add_row(
                    p["id"],
                    p["name"],
                    p["category"],
                    p["version"],
                    p["origin"],
                    status_styled,
                    desc_short,
                    key=p["id"],
                )
        except Exception as ex:
            logger.debug(f"Error refreshing plugins table in TUI: {ex}")

    async def action_toggle_plugin(self) -> None:
        """Toggle active state of highlighted plugin in plugins table."""
        if self._is_input_focused():
            return
        try:
            tabs = self.query_one("#main_tabs", TabbedContent)
            if tabs.active != "tab_plugins":
                tabs.active = "tab_plugins"
                await self.refresh_plugins_table()
                return

            table = self.query_one("#plugins_table", DataTable)
            if table.cursor_row is None:
                return

            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            if not row_key or not row_key.value:
                return

            plugin_id = str(row_key.value)
            from monika.application.harness.installer import list_all_plugins_status, toggle_plugin_state

            plugins = {p["id"]: p for p in list_all_plugins_status()}
            if plugin_id in plugins:
                p = plugins[plugin_id]
                if not p["can_toggle"]:
                    self.notify(f"Plugin '{plugin_id}' is a core non-bypassable invariant.", severity="warning")
                    return
                next_state = not p["enabled"]
                ok, msg = toggle_plugin_state(plugin_id, p["category"], next_state)
                if ok:
                    self.notify(msg, severity="information")
                    await self.refresh_plugins_table()
                else:
                    self.notify(msg, severity="error")
        except Exception as ex:
            logger.error(f"Error in action_toggle_plugin: {ex}")

    def action_install_plugin(self) -> None:
        """Open plugin installation modal dialog."""
        if self._is_input_focused():
            return
        from monika.interfaces.cli.overlays.plugin_install_modal import PluginInstallModalScreen

        self.push_screen(PluginInstallModalScreen(), self._on_plugin_install_modal_closed)

    async def _on_plugin_install_modal_closed(self, result: Any) -> None:
        await self.refresh_plugins_table()
