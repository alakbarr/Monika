"""
Package: agent.monitors
Background monitoring loops extracted from TradingAgent.
"""
from agent.monitors.drawdown_monitor import run_floating_drawdown_monitor
from agent.monitors.scraper_loop import run_scraper_loop
from agent.monitors.db_health import run_db_health_check
from agent.monitors.paper_trade_monitor import run_paper_trade_monitor
from agent.monitors.startup_watchdog import StartupWatchdog, global_startup_watchdog

__all__ = [
    "run_floating_drawdown_monitor",
    "run_scraper_loop",
    "run_db_health_check",
    "run_paper_trade_monitor",
    "StartupWatchdog",
    "global_startup_watchdog",
]
