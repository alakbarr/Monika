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
    "_config_version",
}


def validate_config_key(key: str, known_keys: Optional[Set[str]] = None) -> Optional[str]:
    """
    Validates dot-separated configuration keys.
    Returns None if valid or recognized open structure; returns error string with close suggestions if typo detected.
    """
    if not key or not isinstance(key, str):
        return "Configuration key cannot be empty."

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
