# ==============================================================================
# File: interfaces/cli/tui_app/entrypoints.py
# Description: Runner and CLI entrypoint functions for Monika TUI
# ==============================================================================

from typing import Optional

from monika.interfaces.cli.tui_app.constants import DEFAULT_API_URL
from monika.interfaces.cli.tui_app.dashboard import TradingDashboard


def run_tui(
    api_url: str = DEFAULT_API_URL,
    api_key: Optional[str] = None,
    refresh_interval: int = 5,
    theme_name: Optional[str] = None,
) -> None:
    """Entrypoint function to run the Textual TUI dashboard."""
    app = TradingDashboard(api_url=api_url, api_key=api_key, refresh_interval=refresh_interval, theme_name=theme_name)
    app.run()


TradingAgentApp = TradingDashboard


if __name__ == "__main__":
    run_tui()
