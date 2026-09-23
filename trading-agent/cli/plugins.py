# ==============================================================================
# File: cli/plugins.py
# ==============================================================================

"""
CLI Plugin Management for Monika.
Handles 'monika plugin list', 'monika plugin install', 'monika plugin uninstall',
and 'monika plugin info' commands.
"""

import sys
import subprocess
import logging
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from harness.contract import PluginCategory, PluginOrigin
from harness.engine import PluginEngine
from config.settings import load_all_config

logger = logging.getLogger("TradingAgent.CLI.Plugins")
console = Console()


def handle_plugin_command(args) -> int:
    """Entrypoint dispatcher for `monika plugin ...` subcommands."""
    subaction = getattr(args, "plugin_action", "list")
    if subaction == "list":
        return cmd_plugin_list(args)
    elif subaction == "install":
        return cmd_plugin_install(args)
    elif subaction == "uninstall":
        return cmd_plugin_uninstall(args)
    elif subaction == "info":
        return cmd_plugin_info(args)
    elif subaction == "enable":
        return cmd_plugin_enable(args)
    elif subaction == "disable":
        return cmd_plugin_disable(args)
    else:
        console.print(f"[red]Unknown plugin action: {subaction}[/red]")
        return 1


def _create_engine(settings: Optional[dict] = None) -> PluginEngine:
    cfg = settings or load_all_config()
    engine = PluginEngine()
    # Discover installed plugins without starting full runtime loops
    for ep_plugin in engine.discover_entrypoints():
        engine.register_plugin_instance(ep_plugin)

    plugins_cfg = cfg.get("plugins", {})
    auto_dirs = plugins_cfg.get("directories", ["trading-agent/plugins", "custom_plugins"])
    for d in auto_dirs:
        import os
        abs_d = d if os.path.isabs(d) else os.path.join(os.getcwd(), d)
        for dir_plugin in engine.discover_directory_plugins(abs_d):
            engine.register_plugin_instance(dir_plugin)

    engine.apply_settings_overrides(cfg)
    return engine


def cmd_plugin_list(args) -> int:
    """List all detected plugins with status and metadata."""
    settings = load_all_config()
    engine = _create_engine(settings)

    table = Table(title="Monika Installed & Builtin Plugins", header_style="bold cyan")
    table.add_column("Plugin ID", style="bold green")
    table.add_column("Name", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Version", style="magenta")
    table.add_column("Origin", style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Description", style="dim")

    for pid, plugin in sorted(engine.plugins.items()):
        meta = plugin.metadata
        engine.check_required_packages(plugin)

        if not plugin.is_enabled:
            status_str = "[dim red]DISABLED[/dim red]"
        elif plugin.status == "DEGRADED_MISSING_DEPENDENCIES":
            status_str = "[yellow]DEGRADED[/yellow]"
        else:
            status_str = "[green]ACTIVE[/green]"

        cat_str = meta.category.value if hasattr(meta.category, "value") else str(meta.category)
        origin_str = meta.origin.value if hasattr(meta.origin, "value") else str(meta.origin)

        table.add_row(
            meta.id,
            meta.name,
            cat_str,
            meta.version,
            origin_str,
            status_str,
            (meta.description or "")[:45] + ("..." if len(meta.description or "") > 45 else ""),
        )

    console.print(table)
    console.print("\n[dim]To inspect a plugin: `python -m cli.main plugin info <plugin_id>`[/dim]")
    return 0


def cmd_plugin_install(args) -> int:
    """Install a plugin package via pip and verify entry points."""
    target = getattr(args, "package_name", None)
    if not target:
        console.print("[red]Error: Package name required. Usage: monika plugin install <name>[/red]")
        return 1

    package_name = target if target.startswith("monika-plugin-") or "/" in target or target.endswith(".whl") else f"monika-plugin-{target}"
    console.print(f"[bold cyan]Installing Monika plugin package:[/] [bold]{package_name}[/]")

    cmd = [sys.executable, "-m", "pip", "install", package_name]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        console.print(f"[bold red]Installation failed for {package_name}[/]")
        return res.returncode

    console.print(f"[bold green]Successfully installed {package_name}![/]")
    console.print("\n[cyan]Verifying discovered entry points...[/]")

    engine = _create_engine()
    matching = [p for p in engine.plugins.values() if p.metadata.origin == PluginOrigin.PIP_PACKAGE]
    if matching:
        console.print(f"[green]Discovered {len(matching)} pip plugin(s):[/]")
        for p in matching:
            console.print(f"  - [bold]{p.metadata.id}[/] ({p.metadata.name} v{p.metadata.version})")
    else:
        console.print("[yellow]Note: No 'monika.plugins' entry_points found in package. Ensure package implements entry points.[/]")

    console.print("\n[dim]Configure plugin options in `settings.yaml:plugins` to activate.[/dim]")
    return 0


def cmd_plugin_uninstall(args) -> int:
    """Uninstall a plugin package via pip."""
    target = getattr(args, "package_name", None)
    if not target:
        console.print("[red]Error: Package name required. Usage: monika plugin uninstall <name>[/red]")
        return 1

    package_name = target if target.startswith("monika-plugin-") else f"monika-plugin-{target}"
    console.print(f"[bold yellow]Uninstalling plugin package:[/] [bold]{package_name}[/]")

    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package_name]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        console.print(f"[bold green]Successfully uninstalled {package_name}![/]")
    return res.returncode


def cmd_plugin_info(args) -> int:
    """Show detailed metadata and configuration schema for a specific plugin."""
    target_id = getattr(args, "package_name", None)
    if not target_id:
        console.print("[red]Error: Plugin ID required. Usage: monika plugin info <plugin_id>[/red]")
        return 1

    engine = _create_engine()
    plugin = engine.get_plugin(target_id)
    if not plugin:
        console.print(f"[red]Plugin '{target_id}' not found in active registries.[/red]")
        return 1

    meta = plugin.metadata
    info_text = f"""[bold cyan]Plugin ID:[/] {meta.id}
[bold cyan]Name:[/] {meta.name} (v{meta.version})
[bold cyan]Category:[/] {meta.category.value if hasattr(meta.category, 'value') else meta.category}
[bold cyan]Origin:[/] {meta.origin.value if hasattr(meta.origin, 'value') else meta.origin}
[bold cyan]Author:[/] {meta.author or 'Unknown'}
[bold cyan]Is Core:[/] {meta.is_core}
[bold cyan]Status:[/] {plugin.status}
[bold cyan]Description:[/] {meta.description or 'No description provided.'}
[bold cyan]Dependencies:[/] {', '.join(meta.dependencies) if meta.dependencies else 'None'}
[bold cyan]Required Packages:[/] {', '.join(meta.required_packages) if meta.required_packages else 'None'}
[bold cyan]Current Config:[/] {plugin.config}
"""
    console.print(Panel(info_text.strip(), title=f"Plugin Info: {meta.id}", border_style="cyan"))
    return 0


def cmd_plugin_enable(args) -> int:
    """Enable a plugin by ID."""
    plugin_id = getattr(args, "plugin_name", None) or getattr(args, "target", None)
    if not plugin_id:
        console.print("[red]Error: Plugin ID is required to enable (e.g. monika plugin enable discord_alert)[/red]")
        return 1

    from harness.installer import list_all_plugins_status, toggle_plugin_state
    plugins = list_all_plugins_status()
    target = next((p for p in plugins if p["id"] == plugin_id), None)
    category = target["category"] if target else "middleware"

    ok, msg = toggle_plugin_state(plugin_id, category, True)
    if ok:
        console.print(f"[bold green]Successfully enabled plugin '{plugin_id}'[/]")
        return 0
    else:
        console.print(f"[bold red]Failed to enable plugin '{plugin_id}': {msg}[/]")
        return 1


def cmd_plugin_disable(args) -> int:
    """Disable a plugin by ID."""
    plugin_id = getattr(args, "plugin_name", None) or getattr(args, "target", None)
    if not plugin_id:
        console.print("[red]Error: Plugin ID is required to disable (e.g. monika plugin disable discord_alert)[/red]")
        return 1

    from harness.installer import list_all_plugins_status, toggle_plugin_state
    plugins = list_all_plugins_status()
    target = next((p for p in plugins if p["id"] == plugin_id), None)
    category = target["category"] if target else "middleware"

    ok, msg = toggle_plugin_state(plugin_id, category, False)
    if ok:
        console.print(f"[bold yellow]Successfully disabled plugin '{plugin_id}'[/]")
        return 0
    else:
        console.print(f"[bold red]Failed to disable plugin '{plugin_id}': {msg}[/]")
        return 1
