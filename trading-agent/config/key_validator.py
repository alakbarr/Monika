"""
Fuzzy configuration key validation with 'did you mean' suggestions.
"""

import difflib
from typing import Optional, Set

from config.schemas import TradingAgentConfig

KNOWN_TOP_LEVEL_KEYS: Set[str] = set(TradingAgentConfig.model_fields.keys()) | {
    "app_name",
    "environment",
    "trading",
    "risk",
    "execution",
    "paper_trading",
    "scheduler",
    "indicators",
    "llm",
    "database",
    "telegram",
    "scraping",
    "data_quality",
    "plugins",
    "_config_version",
}

DYNAMIC_KEYS: Set[str] = {
    "trading.symbols",
    "trading.lot_size",
    "trading.asset_universe",
    "trading.auto_execute",
    "trading.cost_mode",
    "risk.daily_drawdown_limit",
    "risk.max_daily_drawdown_percent",
    "risk.max_weekly_drawdown_percent",
    "risk.max_concurrent_positions",
    "risk.max_portfolio_heat_pct",
    "scheduler.cycle_interval_hours",
    "scheduler.news_check_minutes",
    "scheduler.trigger_check_minutes",
    "scheduler.cron_expression",
}


def validate_config_key(key: str, known_keys: Optional[Set[str]] = None) -> Optional[str]:
    """
    Validates dot-separated configuration keys.
    Returns None if valid or recognized open structure; returns error string with close suggestions if typo detected.
    """
    if not key or not isinstance(key, str):
        return "Configuration key cannot be empty."

    if key in DYNAMIC_KEYS:
        return None

    candidates = known_keys or KNOWN_TOP_LEVEL_KEYS
    parts = key.split(".")
    top_level = parts[0].strip()

    if top_level not in candidates:
        matches = difflib.get_close_matches(top_level, candidates, n=3, cutoff=0.55)
        msg = f"Unknown configuration section '{top_level}'."
        if matches:
            msg += f" Did you mean: {', '.join(matches)}?"
        return msg

    return None
