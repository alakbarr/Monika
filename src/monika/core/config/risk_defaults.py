"""Canonical risk-contract defaults shared by code and ``settings.example.yaml``.

Keeping these values in one module prevents the prompt, validation, and execution
layers from silently drifting apart when a setting is missing.
"""

DEFAULT_MIN_RR_RATIO: float = 1.5
DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT: float = 4.0
DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT: float = 15.0
DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE: int = 7
DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE: float = 0.60
DEFAULT_MIN_VERIFIABLE_CONFLUENCE: int = 4

__all__ = [
    "DEFAULT_MIN_RR_RATIO",
    "DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT",
    "DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT",
    "DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE",
    "DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE",
    "DEFAULT_MIN_VERIFIABLE_CONFLUENCE",
]
