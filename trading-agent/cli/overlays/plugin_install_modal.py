# ==============================================================================
# File: cli/overlays/plugin_install_modal.py
# Description: Textual Modal Screen for Installing Monika Plugins via Pip
# ==============================================================================

"""
Interactive Modal Dialog for Installing Third-Party & Community Plugins into Monika.

Features:
- Package specification input field (supports pip package name, git URLs, .whl files)
- Preset shortcuts for curated catalog plugins
- Live output console rendering pip install logs
- Retro-vintage styling with double brass border matching Monika TUI design system
"""

import asyncio
from typing import Any, Dict, Optional
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog, Static

from harness.installer import (
    validate_package_spec,
    run_pip_install,
    get_community_catalog,
)


class PluginInstallModalScreen(ModalScreen[Optional[bool]]):
    """
    Modal dialog allowing operator to input a package name or pick a preset catalog plugin
    and run pip installation with live feedback.
    """

    DEFAULT_CSS = """
    PluginInstallModalScreen {
        align: center middle;
        background: rgba(14, 12, 10, 0.85);
    }

    #install_dialog {
        width: 82;
        height: auto;
        max-height: 88%;
        background: #1C1917;
        border: double #F5BD38;
        padding: 1 2;
        box-shadow: 0 4 8 rgba(0, 0, 0, 0.7);
    }

    #install_title {
        text-align: center;
        width: 100%;
        color: #F5BD38;
        text-style: bold;
        padding-bottom: 1;
        border-bottom: heavy #3A352A;
    }

    #install_desc {
        padding: 1 0;
        color: #D8D2C2;
    }

    #preset_container {
        border: round #3A352A;
        background: #151311;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }

    .preset_header {
        color: #F5BD38;
        text-style: bold;
        margin-bottom: 1;
    }

    .preset_item {
        color: #D8D2C2;
        padding: 0 1;
    }

    #pkg_input {
        margin: 1 0;
        border: tall #F5BD38;
        background: #25221E;
        color: #F5E8C7;
    }

    #install_log {
        height: 8;
        border: heavy #3A352A;
        background: #0E0C0A;
        margin: 1 0;
        padding: 0 1;
    }

    #install_buttons {
        width: 100%;
        align: center middle;
        height: auto;
        margin-top: 1;
    }

    #install_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("1", "select_preset_1", "Preset 1", show=False),
        Binding("2", "select_preset_2", "Preset 2", show=False),
        Binding("3", "select_preset_3", "Preset 3", show=False),
        Binding("4", "select_preset_4", "Preset 4", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.catalog = get_community_catalog()[:4]
        self._is_busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="install_dialog"):
            yield Static("🔌 MONIKA PLUG-IN HARNESS INSTALLER", id="install_title")
            yield Static(
                "Install verified community packages, Git repositories, or local .whl packages into Monika's virtualenv.",
                id="install_desc",
            )

            with Vertical(id="preset_container"):
                yield Static("CURATED CATALOG PRESETS (Press number to auto-fill):", classes="preset_header")
                for i, item in enumerate(self.catalog, start=1):
                    yield Static(
                        f" [{i}] {item['name']} ({item['package']}) — {item['category']}",
                        classes="preset_item",
                    )

            yield Input(
                placeholder="Enter package name: e.g. monika-plugin-deepseek or https://github.com/...",
                id="pkg_input",
            )

            yield RichLog(id="install_log", wrap=True, highlight=True, markup=True)

            with Horizontal(id="install_buttons"):
                yield Button("📥 Install via pip", variant="primary", id="btn_run_install")
                yield Button("✕ Cancel / Close", variant="default", id="btn_close_install")

    def on_mount(self) -> None:
        log = self.query_one("#install_log", RichLog)
        log.write("[dim]Ready. Enter package specification above or press [1]-[4] to select a preset.[/dim]")
        self.query_one("#pkg_input", Input).focus()

    def action_select_preset_1(self) -> None:
        if len(self.catalog) >= 1:
            self._fill_package(self.catalog[0]["package"])

    def action_select_preset_2(self) -> None:
        if len(self.catalog) >= 2:
            self._fill_package(self.catalog[1]["package"])

    def action_select_preset_3(self) -> None:
        if len(self.catalog) >= 3:
            self._fill_package(self.catalog[2]["package"])

    def action_select_preset_4(self) -> None:
        if len(self.catalog) >= 4:
            self._fill_package(self.catalog[3]["package"])

    def _fill_package(self, pkg_name: str) -> None:
        inp = self.query_one("#pkg_input", Input)
        inp.value = pkg_name
        inp.cursor_position = len(pkg_name)
        log = self.query_one("#install_log", RichLog)
        log.write(f"[yellow]Selected preset:[/] {pkg_name}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_close_install":
            self.dismiss(None)
        elif button_id == "btn_run_install":
            await self._execute_install()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._execute_install()

    async def _execute_install(self) -> None:
        if self._is_busy:
            return

        inp = self.query_one("#pkg_input", Input)
        pkg = inp.value.strip()
        log = self.query_one("#install_log", RichLog)

        if not pkg:
            log.write("[bold red]Error:[/] Package specification cannot be empty.")
            return

        valid, err = validate_package_spec(pkg)
        if not valid:
            log.write(f"[bold red]Validation Rejected:[/] {err}")
            return

        self._is_busy = True
        btn_run = self.query_one("#btn_run_install", Button)
        btn_run.disabled = True
        log.write(f"[bold cyan]Starting pip install:[/] {pkg}...")
        log.write("[dim]Executing in Monika virtualenv (non-blocking)...[/dim]")

        # Run in worker thread
        success, output = await asyncio.to_thread(run_pip_install, pkg)

        for line in output.splitlines():
            if "Successfully installed" in line:
                log.write(f"[bold green]{line}[/]")
            elif "ERROR" in line or "error" in line.lower():
                log.write(f"[red]{line}[/]")
            else:
                log.write(f"[dim]{line}[/]")

        if success:
            log.write("[bold green]✓ Installation succeeded![/] Press [Esc] or Close to return.")
            btn_run.label = "✓ Installed"
        else:
            log.write("[bold red]✗ Installation failed.[/] Check error details above.")
            btn_run.disabled = False
            btn_run.label = "Retry Install"

        self._is_busy = False

    def action_cancel(self) -> None:
        self.dismiss(None)
