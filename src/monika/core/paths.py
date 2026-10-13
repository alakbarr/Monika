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
    return p.parents[3]  # fallback for src/monika/core layout


REPO_ROOT = _resolve_repo_root()


def get_default_monika_home() -> Path:
    """Return platform-standard persistent user directory for Monika."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Monika"
        return Path.home() / "AppData" / "Local" / "Monika"
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "monika"
    return Path.home() / ".local" / "share" / "monika"


def _resolve_base_dir() -> Path:
    """Resolve active base directory respecting MONIKA_HOME override."""
    monika_home = os.environ.get("MONIKA_HOME")
    if monika_home:
        return Path(monika_home).resolve()
    return REPO_ROOT


BASE_DIR = _resolve_base_dir()
TRADING_AGENT_DIR = BASE_DIR

# Core runtime directories (always absolute, never dependent on current working directory)
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
PROFILES_DIR = BASE_DIR / "profiles"
SUBAGENT_LOGS_DIR = LOGS_DIR / "subagents"

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # src/monika
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
    target = (DATA_DIR / clean_name).resolve()
    if not target.exists():
        repo_data = (REPO_ROOT / "data" / clean_name).resolve()
        if repo_data.exists():
            return repo_data
    return target


def resolve_config_path(rel_or_name: str) -> Path:
    """Resolve a config filename, checking active config/ first, then repo config/, then package defaults."""
    get_config_dir()
    clean_name = rel_or_name.replace("trading-agent/config/", "").replace("trading-agent\\config\\", "").lstrip("/\\")
    target = (CONFIG_DIR / clean_name).resolve()
    if target.exists():
        return target
    repo_cfg = (REPO_ROOT / "config" / clean_name).resolve()
    if repo_cfg.exists():
        return repo_cfg
    # Fallback to package defaults in core/config/
    pkg_default = PACKAGE_ROOT / "core" / "config" / clean_name
    if pkg_default.exists():
        return pkg_default
    return target
