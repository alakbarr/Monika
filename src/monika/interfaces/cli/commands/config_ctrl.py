# ==============================================================================
# File: interfaces/cli/commands/config_ctrl.py
# ==============================================================================

"""
Configuration and Onboarding Commands for Monika.
Handles config show, set, get, unset, edit, and onboarding wizard.
"""

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import aiohttp

from monika.interfaces.cli.context import cli_main
from monika.interfaces.cli.theme import (
    BRASS,
    PHOSPHOR_AMBER,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

_parent_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)


async def _cmd_config_show(args: Any) -> None:
    """Show system configuration or section."""
    import yaml
    from rich.syntax import Syntax

    console = cli_main.get_console()

    url = getattr(args, "url", cli_main.DEFAULT_API_URL)
    token = getattr(args, "token", None) or os.getenv("DASHBOARD_API_KEY", "")
    section = getattr(args, "section", None)
    is_json = getattr(args, "json", False)

    settings = None
    try:
        headers = {"X-API-Key": token} if token else {}
        timeout = aiohttp.ClientTimeout(total=2.0)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
            res = await sess.get(f"{url.rstrip('/')}/api/config/settings")
            if res.status == 200:
                body = await res.json()
                settings = body.get("settings")
    except Exception:
        settings = None

    if settings is None:
        settings = cli_main.load_settings()

    target = settings
    if section:
        parts = section.split(".")
        for p in parts:
            if isinstance(target, dict) and p in target:
                target = target[p]
            else:
                console.print(f"{stamp_err('ERROR')} Configuration path '{section}' not found.")
                return

    if is_json:
        import json as _json

        formatted = _json.dumps(target, indent=2)
        syntax = Syntax(formatted, "json", theme="monokai", line_numbers=False)
    else:
        formatted = yaml.dump(target, default_flow_style=False, sort_keys=False, allow_unicode=True)
        syntax = Syntax(formatted, "yaml", theme="monokai", line_numbers=False)

    console.print(f"[bold {PHOSPHOR_AMBER}]── Configuration: {section or 'Full settings.yaml'} ──[/]")
    console.print(syntax)


async def _cmd_config_set(args: Any) -> None:
    """Update configuration parameter via API or local settings.yaml with validation."""
    console = cli_main.get_console()
    assignments = getattr(args, "assignments", [])
    reason = getattr(args, "reason", "Updated via CLI")
    url = getattr(args, "url", cli_main.DEFAULT_API_URL)
    token = getattr(args, "token", None) or os.getenv("DASHBOARD_API_KEY", "")

    if not assignments:
        console.print(f"{stamp_warn('CONFIG')} No configuration parameter specified.")
        return

    update_dict: Dict[str, Any] = {}
    for item in assignments:
        if "=" not in item:
            console.print(f"{stamp_err('CONFIG')} Invalid assignment '{item}'. Expected format 'path.to.key=value'.")
            return
        key_path, raw_val = item.split("=", 1)
        key_path = key_path.strip()
        raw_val = raw_val.strip()

        val: Any
        if raw_val.lower() == "true":
            val = True
        elif raw_val.lower() == "false":
            val = False
        elif raw_val.lower() in ("none", "null"):
            val = None
        elif raw_val.startswith(("[", "{")) and raw_val.endswith(("]", "}")):
            import json as _json

            try:
                val = _json.loads(raw_val)
            except Exception:
                val = raw_val
        else:
            try:
                if "." in raw_val:
                    val = float(raw_val)
                else:
                    val = int(raw_val)
            except ValueError:
                val = raw_val

        from monika.core.config.key_validator import validate_config_key

        key_err = validate_config_key(key_path)
        if key_err:
            console.print(f"{stamp_err('KEY')} {key_err}")
            return

        keys = key_path.split(".")
        cur = update_dict
        for k in keys[:-1]:
            if k not in cur:
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = val

    # Try API first (unless custom local config path is explicitly provided)
    api_success = False
    if not getattr(args, "config", None):
        try:
            headers = {"X-API-Key": token} if token else {}
            timeout = aiohttp.ClientTimeout(total=3.0)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
                res = await sess.put(
                    f"{url.rstrip('/')}/api/config/settings",
                    json={"settings": update_dict, "reason": reason},
                )
                if res.status == 200:
                    console.print(f"{stamp_ok('CONFIG')} Configuration successfully updated via API ({reason}).")
                    api_success = True
                elif res.status == 422:
                    err = await res.json()
                    console.print(f"{stamp_err('VALIDATION')} {err.get('message', 'Invalid value')}")
                    return
                elif res.status in (401, 403):
                    console.print(
                        f"{stamp_err('ACCESS')} Permission denied: Updating configuration via API requires Admin role. Check API token."
                    )
                    return
                else:
                    err_text = await res.text()
                    console.print(f"{stamp_err('API')} Server returned error ({res.status}): {err_text[:200]}")
                    return
        except aiohttp.ClientConnectorError, asyncio.TimeoutError, aiohttp.ClientConnectionError:
            api_success = False
        except Exception as ex:
            if getattr(args, "url", None) and args.url != cli_main.DEFAULT_API_URL:
                console.print(f"{stamp_err('CONNECTION')} Failed to connect to {url}: {ex}")
                return
            api_success = False

    if not api_success:
        from monika.core.config.settings import _deep_merge, validate_config
        from monika.infrastructure.database.models import ActivityLog

        settings_path = getattr(args, "config", None)
        if not settings_path:
            for cand in (
                os.path.join(_parent_dir, "config", "settings.yaml"),
                "config/settings.yaml",
            ):
                if os.path.exists(cand):
                    settings_path = cand
                    break
        if not settings_path:
            settings_path = "config/settings.yaml"

        existing = cli_main.load_settings(settings_path)
        merged = _deep_merge(existing, update_dict)

        try:
            validate_config(merged)
        except Exception as e:
            console.print(f"{stamp_err('VALIDATION')} {e}")
            return

        from monika.core.config.atomic_writer import AtomicConfigWriter

        try:
            AtomicConfigWriter.update_in_place(settings_path, update_dict, create_backup=True)
        except Exception as e:
            console.print(f"{stamp_err('CONFIG')} Failed to update configuration: {e}")
            return

        try:
            await cli_main.init_db()
            async with cli_main.get_session() as session:
                session.add(
                    ActivityLog(
                        category="system",
                        description=f"Config updated via CLI: {assignments} ({reason})",
                        actor="cli_operator",
                    )
                )
                await session.commit()
        except Exception:
            pass

        console.print(f"{stamp_ok('CONFIG')} Configuration updated and verified in {settings_path}! (Backup created)")


async def _cmd_config_get(args: Any) -> None:
    """Retrieve and display a specific configuration value."""
    console = cli_main.get_console()
    key_path = getattr(args, "key", "")
    is_raw = getattr(args, "raw", False)
    if not key_path:
        console.print(f"{stamp_warn('CONFIG')} No configuration key specified.")
        return

    settings = cli_main.load_settings(getattr(args, "config", None))
    parts = key_path.split(".")
    val = settings
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            console.print(f"{stamp_err('NOT FOUND')} Key '{key_path}' not found in configuration.")
            return

    val_str = str(val)
    if not is_raw and any(s in key_path.lower() for s in ("key", "password", "secret", "token")):
        val_str = "********" if val else ""

    console.print(f"[bold {BRASS}]{key_path}[/]: {val_str}")


async def _cmd_config_unset(args: Any) -> None:
    """Remove a configuration key."""
    console = cli_main.get_console()
    key_path = getattr(args, "key", "")
    if not key_path:
        console.print(f"{stamp_warn('CONFIG')} No configuration key specified.")
        return

    from monika.core.config.atomic_writer import AtomicConfigWriter
    from monika.core.config.settings import validate_config

    settings_path = getattr(args, "config", None) or "config/settings.yaml"
    settings = cli_main.load_settings(settings_path)
    parts = key_path.split(".")
    cur = settings
    for p in parts[:-1]:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            console.print(f"{stamp_err('NOT FOUND')} Key '{key_path}' not found.")
            return

    if isinstance(cur, dict) and parts[-1] in cur:
        del cur[parts[-1]]
        try:
            validate_config(settings)
            AtomicConfigWriter.write(settings_path, settings, create_backup=True)
            console.print(f"{stamp_ok('CONFIG')} Successfully unset '{key_path}'.")
        except Exception as e:
            console.print(f"{stamp_err('CONFIG')} Failed to unset '{key_path}': {e}")
    else:
        console.print(f"{stamp_err('NOT FOUND')} Key '{key_path}' not found.")


async def _cmd_config_edit(args: Any) -> None:
    """Open settings.yaml or plugin config in default editor and validate upon close."""
    import subprocess
    import yaml

    console = cli_main.get_console()
    plugin_id = getattr(args, "plugin_id", None)

    if plugin_id:
        plugin_cands = [
            os.path.join(_parent_dir, "config", "plugins", f"{plugin_id}.yaml"),
            f"config/plugins/{plugin_id}.yaml",
        ]
        target_path = None
        for cand in plugin_cands:
            if os.path.exists(cand):
                target_path = cand
                break
        if not target_path:
            target_dir = os.path.join(_parent_dir, "config", "plugins")
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, f"{plugin_id}.yaml")
            if not os.path.exists(target_path):
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(f"# Plugin configuration for {plugin_id}\nenabled: true\n")
        edit_target = target_path
        is_plugin = True
    else:
        settings_path = getattr(args, "config", None) or "config/settings.yaml"
        edit_target = settings_path
        is_plugin = False

    editor = os.environ.get("EDITOR") or ("notepad" if sys.platform == "win32" else "nano")
    console.print(f"{stamp_info('EDIT')} Opening {edit_target} with {editor}...")
    try:
        import asyncio

        res = await asyncio.to_thread(subprocess.run, [editor, edit_target])
        if res.returncode == 0:
            if is_plugin:
                try:
                    with open(edit_target, "r", encoding="utf-8") as f:
                        yaml.safe_load(f)
                    console.print(f"{stamp_ok('VALIDATED')} Plugin configuration '{plugin_id}' is valid YAML.")
                except Exception as y_err:
                    console.print(f"{stamp_err('INVALID')} YAML syntax error in plugin config: {y_err}")
            else:
                from monika.core.config.settings import validate_config

                try:
                    cfg = cli_main.load_settings(edit_target)
                    validate_config(cfg)
                    console.print(f"{stamp_ok('VALIDATED')} Configuration file is valid and ready.")
                except Exception as val_err:
                    console.print(f"{stamp_err('INVALID')} Configuration error detected: {val_err}")
    except Exception as e:
        console.print(f"{stamp_err('EDIT')} Failed to launch editor: {e}")


async def _cmd_onboarding(args: Any) -> None:
    """Launch trader onboarding personalization wizard."""
    from monika.interfaces.cli.onboarding_trader import TraderOnboarding

    onboarding = TraderOnboarding()
    onboarding.run_interview()


async def _cmd_config(args: Any) -> None:
    """Handle config subcommand routing."""
    action = getattr(args, "config_action", None)
    if action == "show":
        await _cmd_config_show(args)
    elif action == "set":
        await _cmd_config_set(args)
    elif action == "get":
        await _cmd_config_get(args)
    elif action == "unset":
        await _cmd_config_unset(args)
    elif action == "edit":
        await _cmd_config_edit(args)
    else:
        await _cmd_config_show(args)
