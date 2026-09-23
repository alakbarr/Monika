# ==============================================================================
# File: config/settings.py
# ==============================================================================

import yaml
import os
import logging
from typing import Dict, Any, Optional, Union, overload, Literal

try:
    from config.schemas import (
        TradingAgentConfig, RiskConfig, PaperTradingConfig,
        ExecutionConfig, IndicatorsConfig, TradingConfig
    )
    from config.migrations import migrate_config, require_parseable_config
except ImportError:
    from .schemas import (
        TradingAgentConfig, RiskConfig, PaperTradingConfig,
        ExecutionConfig, IndicatorsConfig, TradingConfig
    )
    from .migrations import migrate_config, require_parseable_config

DEFAULT_MONTHLY_BUDGET_USD = 100.0

logger = logging.getLogger("TradingAgent.Config")

_LKG_SETTINGS_CACHE: Dict[str, Any] = {}


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge overlay dict into base dict."""
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def validate_config(settings: Dict[str, Any]) -> TradingAgentConfig:
    """Validate settings dict against TradingAgentConfig schema and return strongly-typed model."""
    try:
        validated = TradingAgentConfig.model_validate(settings)
        return validated
    except Exception as exc:
        logger.error(f"Configuration validation failed: {exc}")
        raise ValueError(f"Invalid configuration: {exc}") from exc


@overload
def load_settings(path: Union[str, Dict[str, Any], None] = None, validate: bool = False, *, return_model: Literal[True]) -> TradingAgentConfig: ...
@overload
def load_settings(path: Union[str, Dict[str, Any], None] = None, validate: bool = False, return_model: Literal[False] = False) -> Dict[str, Any]: ...
@overload
def load_settings(path: Union[str, Dict[str, Any], None] = None, validate: bool = False, return_model: bool = False) -> Union[Dict[str, Any], TradingAgentConfig]: ...
def load_settings(path: Union[str, Dict[str, Any], None] = None, validate: bool = False, return_model: bool = False) -> Union[Dict[str, Any], TradingAgentConfig]:
    """Memuat pengaturan utama dari file YAML beserta file split modular jika ada."""
    settings: Dict[str, Any]
    if isinstance(path, dict):
        settings = dict(path)
    else:
        if path is None:
            # Check for active profile marker first
            active_profile_path = None
            for p_cand in ("profiles/active_profile", "trading-agent/profiles/active_profile"):
                if os.path.exists(p_cand):
                    try:
                        with open(p_cand, "r", encoding="utf-8") as pf:
                            p_name = pf.read().strip()
                            if p_name and p_name != "default":
                                cand_cfg = f"profiles/{p_name}/settings.yaml" if os.path.exists(f"profiles/{p_name}/settings.yaml") else f"trading-agent/profiles/{p_name}/settings.yaml"
                                if os.path.exists(cand_cfg):
                                    active_profile_path = cand_cfg
                    except Exception:
                        pass
            if active_profile_path:
                path = active_profile_path
            elif os.path.exists("config/settings.yaml"):
                path = "config/settings.yaml"
            elif os.path.exists("trading-agent/config/settings.yaml"):
                path = "trading-agent/config/settings.yaml"
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                path = os.path.join(base_dir, "config", "settings.yaml")
                
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
                import time, shutil
                corrupt_path = f"{path}.corrupt.{int(time.time())}"
                if os.path.exists(path):
                    shutil.copy2(path, corrupt_path)
                    logger.warning(f"Corrupt configuration archived to {corrupt_path}")
            except Exception:
                pass
            if os.path.exists(good_backup_path):
                logger.warning(f"Recovering from last-known-good disk backup: {good_backup_path}")
                with open(good_backup_path, "r", encoding="utf-8") as gf:
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
                    with open(split_path, "r", encoding="utf-8") as sf:
                        raw_split = yaml.safe_load(sf)
                        split_data: Dict[str, Any] = dict(raw_split) if isinstance(raw_split, dict) else {}
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
                        with open(fpath, "r", encoding="utf-8") as pf:
                            p_data = yaml.safe_load(pf) or {}
                        if isinstance(p_data, dict):
                            settings["plugins"][plugin_id] = _deep_merge(
                                settings["plugins"].get(plugin_id, {}), p_data
                            )
                            logger.info(f"Loaded per-plugin config from {fpath} for '{plugin_id}'")
                    except Exception as pe:
                        logger.warning(f"Failed to load plugin config {fpath}: {pe}")

        logger.info(f"Settings loaded from {path}")

    if isinstance(settings, dict) and ("trading" in settings or "paper_trading" in settings):
        trading_cfg = settings.get("trading")
        root_pt = settings.get("paper_trading")
        if isinstance(trading_cfg, dict) and isinstance(trading_cfg.get("paper_trading"), dict) and isinstance(root_pt, dict):
            pt_cfg = trading_cfg["paper_trading"]
            if isinstance(pt_cfg, dict):
                merged_pt = _deep_merge(root_pt, pt_cfg)
                settings["paper_trading"] = merged_pt
                trading_cfg["paper_trading"] = merged_pt
        elif isinstance(trading_cfg, dict) and "paper_trading" in trading_cfg and root_pt is None:
            settings["paper_trading"] = trading_cfg["paper_trading"]
        elif isinstance(root_pt, dict) and isinstance(trading_cfg, dict) and "paper_trading" not in trading_cfg:
            trading_cfg["paper_trading"] = root_pt

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

    # Apply schema versioning and migrations
    if isinstance(settings, dict):
        settings, _ = migrate_config(settings)
        llm_cfg = settings.get("llm")
        if isinstance(llm_cfg, dict):
            cp_cfg = llm_cfg.get("credential_pool")
            if isinstance(cp_cfg, dict):
                try:
                    from provider.credential_pool import get_credential_pool
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
    global _LKG_SETTINGS_CACHE
    if isinstance(settings, dict) and settings:
        _LKG_SETTINGS_CACHE = dict(settings)

    return settings


def load_settings_with_lkg(
    path: Union[str, Dict[str, Any], None] = None,
    validate: bool = False,
    return_model: bool = False,
) -> Union[Dict[str, Any], TradingAgentConfig]:
    """
    Resilient settings loader: attempts normal load_settings, but falls back to
    _LKG_SETTINGS_CACHE if reading or parsing encounters runtime file errors.
    """
    global _LKG_SETTINGS_CACHE
    try:
        return load_settings(path, validate=validate, return_model=return_model)
    except Exception as exc:
        if _LKG_SETTINGS_CACHE:
            logger.warning(
                f"Failed to load settings ({exc}); falling back to Last-Known-Good configuration."
            )
            if validate or return_model:
                model = validate_config(_LKG_SETTINGS_CACHE)
                return model if return_model else dict(_LKG_SETTINGS_CACHE)
            return dict(_LKG_SETTINGS_CACHE)
        raise


def load_all_config(settings_path: str | None = None, validate: bool = True) -> Dict[str, Any]:
    """Memuat pengaturan utama dari file YAML (settings.yaml)."""
    settings = load_settings(settings_path, validate=validate)
    
    # Validasi struktur LLM baru
    if isinstance(settings, dict) and "llm" not in settings:
        logger.warning("Bagian 'llm' tidak ditemukan di settings.yaml. Default kosong.")
        settings["llm"] = {"providers": {}, "model_catalog": {}, "task_roles": {}}
        
    return dict(settings) if isinstance(settings, dict) else settings.model_dump()


# Backward-compatible alias
get_settings = load_settings
