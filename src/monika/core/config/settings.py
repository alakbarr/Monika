# ==============================================================================
# File: config/settings.py
# ==============================================================================

import logging
import os
import re
from typing import Any, Dict, Literal, Optional, Union, overload

import yaml

from monika.core.paths import get_config_dir


def _resolve_env_str(val: str) -> str:
    """Resolve ${VAR:default} environment variable placeholders recursively."""
    if not isinstance(val, str) or "${" not in val:
        return val
    curr = val
    for _ in range(5):
        if "${" not in curr:
            break

        def _repl(m: re.Match) -> str:
            inner = m.group(1)
            if ":" in inner:
                var_name, default_val = inner.split(":", 1)
                env_val = os.environ.get(var_name.strip())
                return env_val if (env_val is not None and env_val != "") else _resolve_env_str(default_val)
            return os.environ.get(inner.strip(), "")

        new_val = re.sub(r"\$\{([^{}]+)\}", _repl, curr)
        if new_val == curr:
            break
        curr = new_val
    return curr


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively interpolate environment variables in dicts, lists, and strings."""
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        return _resolve_env_str(obj)
    return obj


try:
    from monika.core.config.migrations import migrate_config, require_parseable_config
    from monika.core.config.schemas import (
        ExecutionConfig,
        IndicatorsConfig,
        PaperTradingConfig,
        RiskConfig,
        TradingAgentConfig,
        TradingConfig,
    )
except ImportError:
    from .migrations import migrate_config, require_parseable_config
    from .schemas import (
        ExecutionConfig,
        IndicatorsConfig,
        PaperTradingConfig,
        RiskConfig,
        TradingAgentConfig,
        TradingConfig,
    )

DEFAULT_MONTHLY_BUDGET_USD = 100.0

logger = logging.getLogger("TradingAgent.Config")

_LKG_SETTINGS_CACHE: dict[str, Any] = {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay dict into base dict."""
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_paper_trading_config(settings: dict[str, Any] | None) -> dict[str, Any]:
    """
    Extract and normalize paper_trading configuration safely whether specified
    as a boolean (e.g. paper_trading: true) or a dictionary.
    Guarantees that downstream callers can safely access keys via .get() or brackets.
    """
    defaults: dict[str, Any] = {
        "enabled": True,
        "initial_balance": 10000.0,
        "streak_loss_policy": "warn_and_scale",
        "streak_risk_scale_factor": 0.5,
        "pause_system_on_daily_sl_limit": False,
        "suspension_hours": 12,
        "tp_detection_method": "close_price",
        "realistic_sl_tp_conflict": "sl_wins",
        "max_paper_trade_holding_hours": 48.0,
        "spread_realistic_multiplier": 2.0,
    }
    if not isinstance(settings, dict):
        return defaults

    trading_cfg = settings.get("trading") if isinstance(settings.get("trading"), dict) else {}
    trading_pt = trading_cfg.get("paper_trading") if isinstance(trading_cfg, dict) else None
    root_pt = settings.get("paper_trading")

    merged = dict(defaults)

    if isinstance(root_pt, bool):
        merged["enabled"] = root_pt
    elif isinstance(root_pt, dict):
        merged = _deep_merge(merged, root_pt)

    if isinstance(trading_pt, bool):
        merged["enabled"] = trading_pt
    elif isinstance(trading_pt, dict):
        merged = _deep_merge(merged, trading_pt)

    return merged


def validate_config(settings: dict[str, Any]) -> TradingAgentConfig:
    """Validate settings dict against TradingAgentConfig schema and return strongly-typed model."""
    try:
        validated = TradingAgentConfig.model_validate(settings)
        return validated
    except Exception as exc:
        logger.error(f"Configuration validation failed: {exc}")
        raise ValueError(f"Invalid configuration: {exc}") from exc


@overload
def load_settings(
    path: Union[str, dict[str, Any], None] = None, validate: bool = False, *, return_model: Literal[True]
) -> TradingAgentConfig: ...
@overload
def load_settings(
    path: Union[str, dict[str, Any], None] = None, validate: bool = False, return_model: Literal[False] = False
) -> dict[str, Any]: ...
@overload
def load_settings(
    path: Union[str, dict[str, Any], None] = None, validate: bool = False, return_model: bool = False
) -> Union[dict[str, Any], TradingAgentConfig]: ...
def load_settings(
    path: Union[str, dict[str, Any], None] = None, validate: bool = False, return_model: bool = False
) -> Union[dict[str, Any], TradingAgentConfig]:
    """Memuat pengaturan utama dari file YAML beserta file split modular jika ada."""
    settings: dict[str, Any]
    if isinstance(path, dict):
        settings = dict(path)
    else:
        if path is None:
            # Check for active profile marker first
            active_profile_path = None
            if os.path.exists("profiles/active_profile"):
                try:
                    with open("profiles/active_profile", encoding="utf-8") as pf:
                        p_name = pf.read().strip()
                        if p_name and p_name != "default":
                            cand_cfg = f"profiles/{p_name}/settings.yaml"
                            if os.path.exists(cand_cfg):
                                active_profile_path = cand_cfg
                except Exception:
                    pass
            cfg_dir = get_config_dir()
            cfg_yaml = cfg_dir / "settings.yaml"
            cfg_example = cfg_dir / "settings.example.yaml"

            if active_profile_path:
                path = active_profile_path
            elif cfg_yaml.exists():
                path = str(cfg_yaml)
            elif cfg_example.exists():
                path = str(cfg_example)
            elif os.path.exists("config/settings.yaml"):
                path = "config/settings.yaml"
            else:
                path = "config/settings.example.yaml"

        good_backup_path = f"{path}.good"
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_loaded = yaml.safe_load(f)
                settings = dict(raw_loaded) if isinstance(raw_loaded, dict) else {}
            # Update last-known-good disk backup on successful load
            try:
                import shutil

                shutil.copy2(path, good_backup_path)
            except Exception:
                pass
        except Exception as read_err:
            logger.error(f"Failed to parse settings at {path}: {read_err}")
            try:
                import shutil
                import time

                corrupt_path = f"{path}.corrupt.{int(time.time())}"
                if os.path.exists(path):
                    shutil.copy2(path, corrupt_path)
                    logger.warning(f"Corrupt configuration archived to {corrupt_path}")
            except Exception:
                pass
            if os.path.exists(good_backup_path):
                logger.warning(f"Recovering from last-known-good disk backup: {good_backup_path}")
                with open(good_backup_path, encoding="utf-8") as gf:
                    raw_loaded = yaml.safe_load(gf)
                    settings = dict(raw_loaded) if isinstance(raw_loaded, dict) else {}
            else:
                raise read_err

    if isinstance(path, str):
        config_dir = os.path.dirname(os.path.abspath(path))
        # Modular split file support (I8)
        split_modules = {
            "risk": "risk.yaml",
            "llm": "llm.yaml",
            "scheduler": "scheduler.yaml",
            "strategies": "strategies.yaml",
        }
        for section, filename in split_modules.items():
            split_path = os.path.join(config_dir, filename)
            if os.path.exists(split_path):
                try:
                    with open(split_path, encoding="utf-8") as sf:
                        raw_split = yaml.safe_load(sf)
                        split_data: dict[str, Any] = dict(raw_split) if isinstance(raw_split, dict) else {}
                    if section == "risk":
                        trading_val = settings.get("trading")
                        if isinstance(trading_val, dict) and isinstance(trading_val.get("risk"), dict):
                            trading_val["risk"] = _deep_merge(trading_val["risk"], split_data)
                        else:
                            risk_val = settings.get("risk")
                            settings["risk"] = _deep_merge(risk_val if isinstance(risk_val, dict) else {}, split_data)
                    else:
                        sec_val = settings.get(section)
                        settings[section] = _deep_merge(sec_val if isinstance(sec_val, dict) else {}, split_data)
                    logger.info(f"Merged modular config from {split_path} into '{section}'")
                except Exception as e:
                    logger.warning(f"Failed to merge split config {split_path}: {e}")

        # Per-plugin configuration directory scanning (Phase 4)
        plugins_config_dir = os.path.join(config_dir, "plugins")
        if os.path.isdir(plugins_config_dir):
            if "plugins" not in settings or not isinstance(settings["plugins"], dict):
                settings["plugins"] = {}
            for fname in os.listdir(plugins_config_dir):
                fpath = os.path.join(plugins_config_dir, fname)
                if fname.endswith((".yaml", ".yml")) and os.path.isfile(fpath):
                    plugin_id = os.path.splitext(fname)[0]
                    try:
                        with open(fpath, encoding="utf-8") as pf:
                            p_data = yaml.safe_load(pf) or {}
                        if isinstance(p_data, dict):
                            settings["plugins"][plugin_id] = _deep_merge(settings["plugins"].get(plugin_id, {}), p_data)
                            logger.info(f"Loaded per-plugin config from {fpath} for '{plugin_id}'")
                    except Exception as pe:
                        logger.warning(f"Failed to load plugin config {fpath}: {pe}")

        logger.info(f"Settings loaded from {path}")

    if isinstance(settings, dict):
        settings = _resolve_env_vars(settings)

    if isinstance(settings, dict):
        trading_cfg = settings.get("trading")
        has_trading_pt = isinstance(trading_cfg, dict) and "paper_trading" in trading_cfg
        has_root_pt = "paper_trading" in settings
        if has_trading_pt or has_root_pt:
            normalized_pt = get_paper_trading_config(settings)
            settings["paper_trading"] = normalized_pt
            if isinstance(trading_cfg, dict):
                trading_cfg["paper_trading"] = normalized_pt

    if isinstance(settings, dict):
        # Sinkronisasi schedule cycle interval: trading.schedule.analysis_cycle_hours <-> scheduler.cycle_interval_hours
        sched_root = settings.get("scheduler")
        trading_cfg = settings.get("trading")
        trading_sched = trading_cfg.get("schedule", {}) if isinstance(trading_cfg, dict) else {}

        cycle_hours = None
        if isinstance(trading_sched, dict) and "analysis_cycle_hours" in trading_sched:
            cycle_hours = trading_sched["analysis_cycle_hours"]
        elif isinstance(sched_root, dict) and "cycle_interval_hours" in sched_root:
            cycle_hours = sched_root["cycle_interval_hours"]

        if cycle_hours is not None:
            if isinstance(trading_sched, dict):
                trading_sched["analysis_cycle_hours"] = cycle_hours
            if isinstance(sched_root, dict):
                sched_root["cycle_interval_hours"] = cycle_hours
            elif "scheduler" not in settings or not isinstance(settings.get("scheduler"), dict):
                settings["scheduler"] = {"cycle_interval_hours": cycle_hours}

        # Sinkronisasi news_check_minutes: trading.schedule.news_check_minutes <-> scheduler.news_check_minutes
        news_mins = None
        if isinstance(trading_sched, dict) and "news_check_minutes" in trading_sched:
            news_mins = trading_sched["news_check_minutes"]
        elif isinstance(sched_root, dict) and "news_check_minutes" in sched_root:
            news_mins = sched_root["news_check_minutes"]

        if news_mins is not None:
            if isinstance(trading_sched, dict):
                trading_sched["news_check_minutes"] = news_mins
            if isinstance(sched_root, dict):
                sched_root["news_check_minutes"] = news_mins
            elif "scheduler" not in settings or not isinstance(settings.get("scheduler"), dict):
                settings["scheduler"] = {"news_check_minutes": news_mins}

        # Sinkronisasi trigger_check_minutes: trading.schedule.trigger_check_minutes <-> scheduler.trigger_check_minutes
        trigger_mins = None
        if isinstance(trading_sched, dict) and "trigger_check_minutes" in trading_sched:
            trigger_mins = trading_sched["trigger_check_minutes"]
        elif isinstance(sched_root, dict) and "trigger_check_minutes" in sched_root:
            trigger_mins = sched_root["trigger_check_minutes"]

        if trigger_mins is not None:
            if isinstance(trading_sched, dict):
                trading_sched["trigger_check_minutes"] = trigger_mins
            if isinstance(sched_root, dict):
                sched_root["trigger_check_minutes"] = trigger_mins
            elif isinstance(settings.get("scheduler"), dict):
                settings["scheduler"]["trigger_check_minutes"] = trigger_mins

        # Sinkronisasi cron_expression: trading.schedule.cron_expression <-> scheduler.cron_expression
        cron_expr = None
        if isinstance(trading_sched, dict) and "cron_expression" in trading_sched:
            cron_expr = trading_sched["cron_expression"]
        elif isinstance(sched_root, dict) and "cron_expression" in sched_root:
            cron_expr = sched_root["cron_expression"]

        if cron_expr is not None:
            if isinstance(trading_sched, dict):
                trading_sched["cron_expression"] = cron_expr
            if isinstance(sched_root, dict):
                sched_root["cron_expression"] = cron_expr
            elif isinstance(settings.get("scheduler"), dict):
                settings["scheduler"]["cron_expression"] = cron_expr

        # Sinkronisasi trading.symbols <-> trading.asset_universe
        if isinstance(trading_cfg, dict):
            syms = trading_cfg.get("symbols")
            universe = trading_cfg.get("asset_universe")
            if syms and not universe:
                trading_cfg["asset_universe"] = list(syms)
            elif universe and not syms:
                trading_cfg["symbols"] = list(universe)

        # Sinkronisasi risk: max_daily_drawdown_percent <-> daily_drawdown_limit
        risk_cfg = None
        if isinstance(trading_cfg, dict) and isinstance(trading_cfg.get("risk"), dict):
            risk_cfg = trading_cfg["risk"]
        elif isinstance(settings.get("risk"), dict):
            risk_cfg = settings["risk"]

        if isinstance(risk_cfg, dict):
            dd_pct = risk_cfg.get("max_daily_drawdown_percent")
            dd_limit = risk_cfg.get("daily_drawdown_limit")
            if dd_pct is not None and dd_limit is None:
                risk_cfg["daily_drawdown_limit"] = float(dd_pct)
            elif dd_limit is not None and dd_pct is None:
                risk_cfg["max_daily_drawdown_percent"] = float(dd_limit)

    # Apply schema versioning and migrations
    if isinstance(settings, dict):
        settings, _ = migrate_config(settings)
        llm_cfg = settings.get("llm")
        if isinstance(llm_cfg, dict):
            cp_cfg = llm_cfg.get("credential_pool")
            if isinstance(cp_cfg, dict):
                try:
                    from monika.infrastructure.credentials.credential_pool import get_credential_pool

                    pool = get_credential_pool()
                    if "base_cooldown_seconds" in cp_cfg:
                        pool.base_cooldown_seconds = float(cp_cfg["base_cooldown_seconds"])
                    if "max_cooldown_seconds" in cp_cfg:
                        pool.max_cooldown_seconds = float(cp_cfg["max_cooldown_seconds"])
                except Exception:
                    pass

    if validate or return_model:
        model = validate_config(settings)
        if return_model:
            return model

    # Cache last-known-good configuration in memory
    if isinstance(settings, dict) and settings:
        _LKG_SETTINGS_CACHE.clear()
        _LKG_SETTINGS_CACHE.update(settings)

    return settings


def reset_lkg_settings_cache() -> None:
    """Reset last-known-good settings cache (for testing isolation)."""
    _LKG_SETTINGS_CACHE.clear()


def load_settings_with_lkg(
    path: Union[str, dict[str, Any], None] = None,
    validate: bool = False,
    return_model: bool = False,
) -> Union[dict[str, Any], TradingAgentConfig]:
    """
    Resilient settings loader: attempts normal load_settings, but falls back to
    _LKG_SETTINGS_CACHE if reading or parsing encounters runtime file errors.
    """
    try:
        return load_settings(path, validate=validate, return_model=return_model)
    except Exception as exc:
        if _LKG_SETTINGS_CACHE:
            logger.warning(f"Failed to load settings ({exc}); falling back to Last-Known-Good configuration.")
            if validate or return_model:
                model = validate_config(_LKG_SETTINGS_CACHE)
                return model if return_model else dict(_LKG_SETTINGS_CACHE)
            return dict(_LKG_SETTINGS_CACHE)
        raise


def load_all_config(settings_path: str | None = None, validate: bool = True) -> dict[str, Any]:
    """Memuat pengaturan utama dari file YAML (settings.yaml)."""
    settings = load_settings(settings_path, validate=validate)

    # Validasi struktur LLM baru
    if isinstance(settings, dict) and "llm" not in settings:
        logger.warning("Bagian 'llm' tidak ditemukan di settings.yaml. Default kosong.")
        settings["llm"] = {"providers": {}, "model_catalog": {}, "task_roles": {}}

    return dict(settings) if isinstance(settings, dict) else settings.model_dump()


# Backward-compatible alias
get_settings = load_settings


def get_installation_tier(settings_or_path: Union[dict[str, Any], str, None] = None) -> str:
    """
    Return the configured installation tier ('trial', 'full', or 'unconfigured').
    Adheres strictly to standard configuration cascade hierarchy:
    Explicit Dictionary/File Parameter > OS Environment Variable > Persistent Marker File > Global Settings File > Safe Fallback ('trial').
    """
    if isinstance(settings_or_path, dict):
        val = settings_or_path.get("installation_tier")
        if val is not None and str(val).strip().lower() in ("trial", "full", "unconfigured"):
            return str(val).strip().lower()
    elif isinstance(settings_or_path, str):
        try:
            cfg = load_settings(settings_or_path)
            val = cfg.get("installation_tier")
            if val is not None and str(val).strip().lower() in ("trial", "full", "unconfigured"):
                return str(val).strip().lower()
        except Exception:
            pass

    env_tier = os.getenv("MONIKA_TIER")
    if env_tier and env_tier.strip().lower() in ("trial", "full", "unconfigured"):
        return env_tier.strip().lower()

    from pathlib import Path

    _cur = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / ".monika_tier",
        Path.cwd().parent / ".monika_tier",
        _cur.parent / ".monika_tier",
        _cur.parent.parent / ".monika_tier",
        _cur / ".monika_tier",
    ]
    for cand in candidates:
        if cand.exists():
            try:
                t = cand.read_text(encoding="utf-8").strip().lower()
                if t in ("trial", "full", "unconfigured"):
                    return t
            except Exception:
                pass

    try:
        cfg = load_settings()
        val = cfg.get("installation_tier")
        if val is not None and str(val).strip().lower() in ("trial", "full", "unconfigured"):
            return str(val).strip().lower()
    except Exception:
        pass

    return "trial"
