# ==============================================================================
# File: interfaces/cli/commands/__init__.py
# ==============================================================================

"""
CLI Subcommands and Handlers Registry for Monika.
"""

from monika.interfaces.cli.commands.analysis_ctrl import (
    _cmd_analyze,
    _cmd_ask,
    _cmd_backtest,
    _cmd_backup,
    _cmd_stress_test,
)
from monika.interfaces.cli.commands.benchmark_ctrl import (
    _cmd_benchmark,
    _cmd_benchmark_history,
    _cmd_benchmark_leaderboard,
    _cmd_benchmark_models,
    _cmd_benchmark_run,
    _cmd_benchmark_tasks,
)
from monika.interfaces.cli.commands.config_ctrl import (
    _cmd_config,
    _cmd_config_edit,
    _cmd_config_get,
    _cmd_config_set,
    _cmd_config_show,
    _cmd_config_unset,
    _cmd_onboarding,
)
from monika.interfaces.cli.commands.daemon_ctrl import (
    _acli_run,
    _cmd_chat,
    _cmd_kill,
    _cmd_pause,
    _cmd_positions,
    _cmd_resume,
    _cmd_status,
    _cmd_stop,
    _cmd_tui,
    _cmd_unsuspend,
)
from monika.interfaces.cli.commands.inspect_ctrl import (
    _cmd_doctor,
    _cmd_logs,
    _cmd_profile,
    _cmd_sessions,
    _cmd_setup,
)
from monika.interfaces.cli.commands.auth_ctrl import (
    handle_auth_command,
)
from monika.interfaces.cli.commands.parser import (
    MonikaArgumentParser,
    parse_args,
)

__all__ = [
    "MonikaArgumentParser",
    "parse_args",
    "handle_auth_command",
    "_cmd_status",
    "_cmd_pause",
    "_cmd_resume",
    "_cmd_unsuspend",
    "_cmd_kill",
    "_cmd_stop",
    "_cmd_positions",
    "_acli_run",
    "_cmd_tui",
    "_cmd_chat",
    "_cmd_config_show",
    "_cmd_config_set",
    "_cmd_config_get",
    "_cmd_config_unset",
    "_cmd_config_edit",
    "_cmd_onboarding",
    "_cmd_config",
    "_cmd_sessions",
    "_cmd_logs",
    "_cmd_doctor",
    "_cmd_setup",
    "_cmd_profile",
    "_cmd_ask",
    "_cmd_analyze",
    "_cmd_backtest",
    "_cmd_stress_test",
    "_cmd_backup",
    "_cmd_benchmark_run",
    "_cmd_benchmark_leaderboard",
    "_cmd_benchmark_history",
    "_cmd_benchmark_tasks",
    "_cmd_benchmark_models",
    "_cmd_benchmark",
]
