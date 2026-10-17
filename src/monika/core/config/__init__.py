"""
Monika Core Configuration Package.

Provides strongly-typed configuration schemas, atomic round-trip YAML persistence,
fail-closed environment variable guards, schema migrations, and hot-reload event bus.
"""

from monika.core.config.atomic_writer import AtomicConfigWriter
from monika.core.config.config_manager import ConfigManager
from monika.core.config.env_file_manager import EnvFileManager
from monika.core.config.hot_reload import ConfigReloader, RiskParameterReloader
from monika.core.config.migrations import (
    CURRENT_CONFIG_VERSION,
    get_config_version,
    migrate_config,
    migrate_settings,
    require_parseable_config,
)
from monika.core.config.schemas import (
    DatabaseConfig,
    ExecutionConfig,
    IndicatorsConfig,
    LLMConfig,
    PaperTradingConfig,
    RiskConfig,
    SchedulerConfig,
    SecurityConfig,
    TelegramConfig,
    TradingAgentConfig,
    TradingConfig,
)
from monika.core.config.security import BLOCKED_ENV_VARS, validate_env_mutation
from monika.core.config.settings import (
    get_paper_trading_config,
    load_settings,
)

__all__ = [
    # Settings loading
    "load_settings",
    "get_paper_trading_config",
    # Schemas
    "TradingAgentConfig",
    "TradingConfig",
    "RiskConfig",
    "PaperTradingConfig",
    "SecurityConfig",
    "DatabaseConfig",
    "TelegramConfig",
    "ExecutionConfig",
    "IndicatorsConfig",
    "LLMConfig",
    "SchedulerConfig",
    # Atomic writing and persistence
    "AtomicConfigWriter",
    "EnvFileManager",
    # Hot reload and supervisor
    "ConfigManager",
    "ConfigReloader",
    "RiskParameterReloader",
    # Security guards
    "BLOCKED_ENV_VARS",
    "validate_env_mutation",
    # Migrations
    "CURRENT_CONFIG_VERSION",
    "get_config_version",
    "migrate_config",
    "migrate_settings",
    "require_parseable_config",
]
