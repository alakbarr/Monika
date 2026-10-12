"""
Canonical application path resolution for Monika Trading Agent.
Provides CWD-invariant absolute paths for data, logs, configs, and repository root.
"""

from pathlib import Path

# TRADING_AGENT_DIR: D:/Monika/trading-agent
TRADING_AGENT_DIR = Path(__file__).resolve().parents[2]

# REPO_ROOT: D:/Monika
REPO_ROOT = TRADING_AGENT_DIR.parent

# Core runtime directories (always absolute, never dependent on current working directory)
DATA_DIR = TRADING_AGENT_DIR / "data"
LOGS_DIR = TRADING_AGENT_DIR / "logs"
CONFIG_DIR = TRADING_AGENT_DIR / "config"
SUBAGENT_LOGS_DIR = LOGS_DIR / "subagents"


def get_data_dir() -> Path:
    """Return canonical data directory, ensuring it exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_logs_dir() -> Path:
    """Return canonical logs directory, ensuring it exists."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


def get_subagent_logs_dir() -> Path:
    """Return canonical subagent logs directory, ensuring it exists."""
    SUBAGENT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return SUBAGENT_LOGS_DIR


def resolve_data_path(rel_or_name: str) -> Path:
    """Resolve a filename or sub-path inside the canonical data directory."""
    get_data_dir()
    clean_name = rel_or_name.replace("trading-agent/data/", "").replace("trading-agent\\data\\", "").lstrip("/\\")
    return (DATA_DIR / clean_name).resolve()
