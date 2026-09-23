# ==============================================================================
# File: harness/installer.py
# ==============================================================================

"""
Plugin Installer and Lifecycle Management Service for Monika Trading Harness.
Provides safe pip execution, atomic configuration synchronization,
community catalog curation, and unified status inspection across Web UI, TUI,
and Telegram bot surfaces.
"""

import os
import re
import sys
import yaml
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from harness.contract import PluginCategory, PluginOrigin
from harness.engine import PluginEngine, get_plugin_engine

logger = logging.getLogger("TradingAgent.Harness.Installer")

# Base settings file location
SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"

# Regex patterns for safe package specification
_SAFE_PACKAGE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*([=><~^!]=?[a-zA-Z0-9_\-\.]+)?$")
_SAFE_GIT_URL_RE = re.compile(r"^(git\+)?https://(github\.com|gitlab\.com)/[a-zA-Z0-9_\-\.]*/[a-zA-Z0-9_\-\.]*(\.git)?(@[a-zA-Z0-9_\-\./]+)?$")
_SAFE_WHEEL_PATH_RE = re.compile(r"^([a-zA-Z]:[/\\])?[a-zA-Z0-9_\-\./\\]+\.whl$")
_DISALLOWED_TOKENS = set(";&|`$()\n\r\"'\\{}[]~!#%^?*")


def validate_package_spec(spec: str) -> Tuple[bool, str]:
    """
    Validate that a package specification string is safe for execution via pip.
    Guards against command injection and arbitrary shell tokens.
    """
    if not spec or not isinstance(spec, str):
        return False, "Package specification cannot be empty."

    spec_clean = spec.strip()
    if not spec_clean:
        return False, "Package specification cannot be empty."

    # Reject dangerous shell control characters
    for ch in spec_clean:
        if ch in _DISALLOWED_TOKENS:
            return False, f"Package specification contains forbidden character: '{ch}'"

    # Match against allowed patterns
    if _SAFE_PACKAGE_RE.match(spec_clean):
        return True, ""
    if _SAFE_GIT_URL_RE.match(spec_clean):
        return True, ""
    if _SAFE_WHEEL_PATH_RE.match(spec_clean):
        return True, ""

    return False, (
        f"Invalid package specification: '{spec_clean}'. "
        "Allowed formats: standard package name (e.g. monika-plugin-deepseek), "
        "GitHub/GitLab HTTPS URL, or local .whl file."
    )


def run_pip_install(spec: str, timeout_sec: int = 180) -> Tuple[bool, str]:
    """
    Execute pip install for the given package specification inside Monika's virtualenv.
    """
    is_valid, err_msg = validate_package_spec(spec)
    if not is_valid:
        return False, err_msg

    spec_clean = spec.strip()
    cmd = [sys.executable, "-m", "pip", "install", spec_clean]
    logger.info(f"[Harness.Installer] Running pip install: {' '.join(cmd)}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        combined = f"{out}\n{err}".strip()

        if proc.returncode == 0:
            logger.info(f"[Harness.Installer] Successfully installed '{spec_clean}'")
            # Trigger discovery on running engine if available
            engine = get_plugin_engine()
            if engine:
                try:
                    engine.discover_entrypoints()
                except Exception as ex:
                    logger.debug(f"[Harness.Installer] Post-install discovery notice: {ex}")
            return True, combined
        else:
            logger.error(f"[Harness.Installer] Failed to install '{spec_clean}' (code {proc.returncode}): {err}")
            return False, combined

    except subprocess.TimeoutExpired:
        logger.error(f"[Harness.Installer] pip install '{spec_clean}' timed out after {timeout_sec}s")
        return False, f"Installation timed out after {timeout_sec} seconds."
    except Exception as ex:
        logger.error(f"[Harness.Installer] Subprocess execution error: {ex}", exc_info=True)
        return False, str(ex)


def run_pip_uninstall(package_name: str, timeout_sec: int = 60) -> Tuple[bool, str]:
    """
    Execute pip uninstall for a specified third-party plugin package.
    """
    if not package_name or not isinstance(package_name, str):
        return False, "Package name cannot be empty."

    pkg_clean = package_name.strip()
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*$", pkg_clean):
        return False, f"Invalid package name format for uninstall: '{pkg_clean}'"

    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", pkg_clean]
    logger.info(f"[Harness.Installer] Running pip uninstall: {' '.join(cmd)}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        combined = f"{out}\n{err}".strip()

        if proc.returncode == 0:
            logger.info(f"[Harness.Installer] Successfully uninstalled '{pkg_clean}'")
            return True, combined
        else:
            logger.warning(f"[Harness.Installer] pip uninstall '{pkg_clean}' returned code {proc.returncode}")
            return False, combined

    except subprocess.TimeoutExpired:
        return False, f"Uninstallation timed out after {timeout_sec} seconds."
    except Exception as ex:
        return False, str(ex)


def get_community_catalog() -> List[Dict[str, Any]]:
    """
    Returns the curated catalog of official and verified community plugins
    available for 1-click installation.
    """
    return [
        {
            "id": "telegram_extended",
            "name": "Telegram Extended Controls",
            "package": "monika-plugin-telegram-extended",
            "category": "notifications",
            "version": "1.0.0",
            "author": "Monika Core Team",
            "description": "Interactive inline charts, order slips, and instant confirmation callback controls for Telegram.",
            "default_enabled": True,
        },
        {
            "id": "crypto_ccxt",
            "name": "CCXT Universal Crypto Broker",
            "package": "monika-plugin-crypto-ccxt",
            "category": "broker",
            "version": "1.2.0",
            "author": "Community / QuantLab",
            "description": "Spot and perpetual futures execution across Binance, Bybit, OKX, and Deribit via CCXT.",
            "default_enabled": False,
        },
        {
            "id": "deepseek_reasoner",
            "name": "DeepSeek R1 / V3 Provider",
            "package": "monika-plugin-deepseek",
            "category": "analysis_pipeline",
            "version": "1.1.0",
            "author": "DeepSeek / Quant",
            "description": "High-speed reasoning LLM provider adapter for Stage 1 macro and Stage 2 asset debate.",
            "default_enabled": False,
        },
        {
            "id": "calendar_pro",
            "name": "Economic Calendar Pro",
            "package": "monika-plugin-economic-calendar-pro",
            "category": "data_sources",
            "version": "1.0.4",
            "author": "Forex Live Feeds",
            "description": "Sub-second low latency macroeconomic release scraper and calendar event socket.",
            "default_enabled": False,
        },
        {
            "id": "kelly_sizing",
            "name": "Fractional Kelly Criterion Sizing",
            "package": "monika-plugin-kelly-sizing",
            "category": "risk_rules",
            "version": "1.0.1",
            "author": "Quant Risk Systems",
            "description": "Dynamic volatility-adjusted fractional Kelly sizing plugin for RiskGate.",
            "default_enabled": False,
        },
        {
            "id": "discord_alerts",
            "name": "Discord Multi-Channel Webhook",
            "package": "monika-plugin-discord-alerts",
            "category": "notifications",
            "version": "1.0.0",
            "author": "Monika Community",
            "description": "Broadcasts trade signals, risk breaches, and daily performance slips to Discord channels.",
            "default_enabled": False,
        },
    ]


def toggle_plugin_state(
    plugin_id: str,
    category: str,
    enabled: bool,
    settings_file: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Atomically toggle a plugin's active state in settings.yaml and notify PluginEngine.
    """
    path = settings_file or SETTINGS_PATH
    if not path.exists():
        return False, f"Settings configuration file not found at: {path}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        plugins_sec = cfg.setdefault("plugins", {})
        cat_norm = category.lower().strip().replace(" ", "_").replace("-", "_")

        # Route to appropriate section in settings.yaml
        if cat_norm in ("analysis_pipeline", "analysis_pipelines"):
            ap = plugins_sec.setdefault("analysis_pipeline", {})
            avail = ap.setdefault("available", {})
            item = avail.setdefault(plugin_id, {})
            item["enabled"] = enabled
            if enabled and not ap.get("active"):
                ap["active"] = plugin_id
        elif cat_norm in ("broker", "brokers"):
            br = plugins_sec.setdefault("broker", {})
            avail = br.setdefault("available", {})
            item = avail.setdefault(plugin_id, {})
            item["enabled"] = enabled
            if enabled and not br.get("active"):
                br["active"] = plugin_id
        elif cat_norm in ("risk_rules", "risk_rule"):
            rr = plugins_sec.setdefault("risk_rules", {})
            mr = rr.setdefault("modular_rules", {})
            item = mr.setdefault(plugin_id, {})
            item["enabled"] = enabled
        elif cat_norm in ("schedulers", "scheduler", "task"):
            sc = plugins_sec.setdefault("schedulers", {})
            item = sc.setdefault(plugin_id, {})
            item["enabled"] = enabled
        elif cat_norm in ("data_sources", "data_source", "scraper", "scrapers"):
            ds = plugins_sec.setdefault("data_sources", {})
            item = ds.setdefault(plugin_id, {})
            item["enabled"] = enabled
        elif cat_norm in ("notifications", "notification", "alert", "alerts"):
            nt = plugins_sec.setdefault("notifications", {})
            item = nt.setdefault(plugin_id, {})
            item["enabled"] = enabled
        else:
            custom = plugins_sec.setdefault("custom", {})
            item = custom.setdefault(plugin_id, {})
            item["enabled"] = enabled

        # Write atomically with comment preservation and backup rotation
        try:
            from config.atomic_writer import AtomicConfigWriter
            AtomicConfigWriter.write(path, cfg, create_backup=True)
        except Exception as write_err:
            logger.debug(f"[Harness.Installer] AtomicConfigWriter fallback: {write_err}")
            temp_file = path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            os.replace(temp_file, path)

        # Notify in-memory engine
        engine = get_plugin_engine()
        if engine:
            engine.set_plugin_enabled(plugin_id, enabled)

        action_str = "diaktifkan" if enabled else "dinonaktifkan"
        msg = f"Plugin '{plugin_id}' ({category}) berhasil {action_str}."
        logger.info(f"[Harness.Installer] {msg}")
        return True, msg

    except Exception as ex:
        logger.error(f"[Harness.Installer] Failed to toggle plugin state: {ex}", exc_info=True)
        return False, f"Gagal memperbarui konfigurasi plugin: {ex}"


def list_all_plugins_status(settings_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Returns unified status of all registered plugins by aggregating
    PluginEngine runtime instances and settings.yaml configuration.
    """
    results: Dict[str, Dict[str, Any]] = {}
    path = settings_file or SETTINGS_PATH
    settings_plugins: Dict[str, Any] = {}

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_cfg = yaml.safe_load(f) or {}
                settings_plugins = raw_cfg.get("plugins", {})
        except Exception as e:
            logger.debug(f"[Harness.Installer] Error reading settings.yaml: {e}")

    # 1. Inspect live PluginEngine if running
    engine = get_plugin_engine()
    if engine and engine.plugins:
        for pid, p in engine.plugins.items():
            cat = p.metadata.category.value if hasattr(p.metadata.category, "value") else str(p.metadata.category)
            origin = p.metadata.origin.value if hasattr(p.metadata.origin, "value") else str(p.metadata.origin)
            status = p.status if hasattr(p, "status") and p.status else ("ACTIVE" if p.is_enabled else "DISABLED")

            results[pid] = {
                "id": pid,
                "name": p.metadata.name,
                "category": cat,
                "version": p.metadata.version,
                "origin": origin,
                "enabled": p.is_enabled,
                "status": status,
                "status_message": getattr(p, "status_message", ""),
                "description": p.metadata.description,
                "author": p.metadata.author or "Monika Harness",
                "can_uninstall": (origin == "pip_package"),
                "can_toggle": not p.metadata.is_core,
            }

    # 2. Inspect settings.yaml plugins to discover any not yet in engine
    # Analysis pipelines
    ap_cfg = settings_plugins.get("analysis_pipeline", {})
    active_ap = ap_cfg.get("active", "macro_to_asset")
    for ap_id, ap_data in ap_cfg.get("available", {}).items():
        if ap_id not in results:
            en = ap_data.get("enabled", True) if isinstance(ap_data, dict) else bool(ap_data)
            results[ap_id] = {
                "id": ap_id,
                "name": ap_id.replace("_", " ").title(),
                "category": "analysis_pipeline",
                "version": "1.0.0",
                "origin": "builtin",
                "enabled": en,
                "status": "ACTIVE" if (en and active_ap == ap_id) else "DISABLED",
                "status_message": "Active pipeline" if (active_ap == ap_id) else "Standby pipeline",
                "description": ap_data.get("description", "") if isinstance(ap_data, dict) else "",
                "author": "Monika Core",
                "can_uninstall": False,
                "can_toggle": True,
            }

    # Brokers
    br_cfg = settings_plugins.get("broker", {})
    active_br = br_cfg.get("active", "paper_trading")
    for br_id, br_data in br_cfg.get("available", {}).items():
        if br_id not in results:
            en = br_data.get("enabled", True) if isinstance(br_data, dict) else bool(br_data)
            results[br_id] = {
                "id": br_id,
                "name": br_id.replace("_", " ").title(),
                "category": "broker",
                "version": "1.0.0",
                "origin": "builtin",
                "enabled": en,
                "status": "ACTIVE" if (en and active_br == br_id) else "DISABLED",
                "status_message": "Active broker" if (active_br == br_id) else "Standby broker",
                "description": br_data.get("description", "") if isinstance(br_data, dict) else "",
                "author": "Monika Core",
                "can_uninstall": False,
                "can_toggle": True,
            }

    # Schedulers
    for sid, sdata in settings_plugins.get("schedulers", {}).items():
        if sid not in results:
            en = sdata.get("enabled", True) if isinstance(sdata, dict) else bool(sdata)
            results[sid] = {
                "id": sid,
                "name": sid.replace("_", " ").title(),
                "category": "scheduler",
                "version": "1.0.0",
                "origin": "builtin",
                "enabled": en,
                "status": "ACTIVE" if en else "DISABLED",
                "status_message": "",
                "description": f"Background scheduler task: {sid}",
                "author": "Monika Core",
                "can_uninstall": False,
                "can_toggle": True,
            }

    # Risk Rules
    rr_cfg = settings_plugins.get("risk_rules", {}).get("modular_rules", {})
    for rid, rdata in rr_cfg.items():
        if rid not in results:
            en = rdata.get("enabled", True) if isinstance(rdata, dict) else bool(rdata)
            results[rid] = {
                "id": rid,
                "name": rid.replace("_", " ").title(),
                "category": "risk_rule",
                "version": "1.0.0",
                "origin": "builtin",
                "enabled": en,
                "status": "ACTIVE" if en else "DISABLED",
                "status_message": "",
                "description": f"Modular risk rule: {rid}",
                "author": "Monika Core",
                "can_uninstall": False,
                "can_toggle": True,
            }

    # Data Sources
    for ds_id, ds_data in settings_plugins.get("data_sources", {}).items():
        if ds_id not in results:
            en = ds_data.get("enabled", True) if isinstance(ds_data, dict) else bool(ds_data)
            results[ds_id] = {
                "id": ds_id,
                "name": ds_id.title(),
                "category": "data_source",
                "version": "1.0.0",
                "origin": "builtin",
                "enabled": en,
                "status": "ACTIVE" if en else "DISABLED",
                "status_message": "",
                "description": f"Market & macroeconomic scraper: {ds_id}",
                "author": "Monika Core",
                "can_uninstall": False,
                "can_toggle": True,
            }

    # Notifications
    for nt_id, nt_data in settings_plugins.get("notifications", {}).items():
        if nt_id not in results:
            en = nt_data.get("enabled", True) if isinstance(nt_data, dict) else bool(nt_data)
            results[nt_id] = {
                "id": nt_id,
                "name": nt_id.title(),
                "category": "notification",
                "version": "1.0.0",
                "origin": "builtin",
                "enabled": en,
                "status": "ACTIVE" if en else "DISABLED",
                "status_message": "",
                "description": f"Event and trade notification adapter: {nt_id}",
                "author": "Monika Core",
                "can_uninstall": False,
                "can_toggle": True,
            }

    # Return sorted by category then name
    return sorted(list(results.values()), key=lambda x: (x["category"], x["name"]))
