"""
Canonical application path resolution for Monika Trading Agent.
Provides CWD-invariant absolute paths for data, logs, configs, and repository root.
"""

import os
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Find the canonical repository root by searching upward for project markers."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src").is_dir():
            return parent
    return p.parents[4]  # fallback for standard src/monika/infrastructure/infra layout


REPO_ROOT = _resolve_repo_root()

# Support MONIKA_HOME override for testing/isolated environments
_monika_home = os.environ.get("MONIKA_HOME")
if _monika_home:
    BASE_DIR = Path(_monika_home).resolve()
else:
    BASE_DIR = REPO_ROOT

TRADING_AGENT_DIR = BASE_DIR

# Core runtime directories (always absolute, never dependent on current working directory)
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
PROFILES_DIR = BASE_DIR / "profiles"
SUBAGENT_LOGS_DIR = LOGS_DIR / "subagents"

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # src/monika
BUILTIN_SKILLS_DIR = PACKAGE_ROOT / "application" / "skills"
USER_SKILLS_DIR = BASE_DIR / "skills"


def get_repo_root() -> Path:
    """Return repository root directory."""
    return REPO_ROOT


def get_base_dir() -> Path:
    """Return base root directory (either REPO_ROOT or MONIKA_HOME)."""
    return BASE_DIR


def get_data_dir() -> Path:
    """Return canonical data directory, ensuring it exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_logs_dir() -> Path:
    """Return canonical logs directory, ensuring it exists."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


def get_config_dir() -> Path:
    """Return canonical config directory, ensuring it exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def get_profiles_dir() -> Path:
    """Return canonical profiles directory, ensuring it exists."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR


def get_subagent_logs_dir() -> Path:
    """Return canonical subagent logs directory, ensuring it exists."""
    SUBAGENT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return SUBAGENT_LOGS_DIR


def get_builtin_skills_dir() -> Path:
    """Return package-builtin skills directory."""
    return BUILTIN_SKILLS_DIR


def get_skills_dir() -> Path:
    """Return user/runtime skills directory, ensuring it exists."""
    USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_SKILLS_DIR


def resolve_data_path(rel_or_name: str) -> Path:
    """Resolve a filename or sub-path inside the canonical data directory."""
    get_data_dir()
    clean_name = rel_or_name.replace("trading-agent/data/", "").replace("trading-agent\\data\\", "").lstrip("/\\")
    return (DATA_DIR / clean_name).resolve()


def resolve_config_path(rel_or_name: str) -> Path:
    """Resolve a config filename, checking root config/ first, then package defaults."""
    get_config_dir()
    clean_name = rel_or_name.replace("trading-agent/config/", "").replace("trading-agent\\config\\", "").lstrip("/\\")
    target = (CONFIG_DIR / clean_name).resolve()
    if target.exists():
        return target
    # Fallback to package defaults in core/config/
    pkg_default = PACKAGE_ROOT / "core" / "config" / clean_name
    if pkg_default.exists():
        return pkg_default
    return target
