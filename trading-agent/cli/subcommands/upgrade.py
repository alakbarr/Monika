# ==============================================================================
# File: cli/subcommands/upgrade.py
# ==============================================================================

"""
Subcommand: upgrade
Interactive, step-by-step upgrade from Monika Trial Package to Full Package.
Handles PostgreSQL transition, Web Dashboard compilation, 9Router, and TimesFM.
"""

import os
import sys
import shutil
import subprocess
import argparse
from typing import Optional, Dict, Any

from cli.subcommands.base import Subcommand
from cli.theme import (
    get_console, stamp_ok, stamp_err, stamp_warn, stamp_info,
    PHOSPHOR_AMBER, BRASS, MUTED, PAPER, LEDGER_BOX
)
from rich.table import Table
from rich.prompt import Confirm, Prompt
from config.settings import load_settings, get_installation_tier
from config.atomic_writer import AtomicConfigWriter
from utils.infra.env_file_manager import EnvFileManager


class UpgradeSubcommand(Subcommand):
    """Handles migration and feature unlocking from Trial to Full package."""

    name: str = "upgrade"
    description: str = "Upgrade installation from Trial Package to Full Package"

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        parser = subparsers.add_parser(
            self.name,
            help=self.description,
            description="Upgrade from Trial to Full package with automated DB migration and dependency setup."
        )
        parser.add_argument("--yes", "-y", action="store_true", default=False, help="Automatic non-interactive confirmation")
        parser.add_argument("--skip-npm", action="store_true", default=False, help="Skip dashboard npm dependencies installation")
        parser.add_argument("--skip-weights", action="store_true", default=False, help="Skip TimesFM neural forecasting weights download")
        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        console = get_console()
        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"[{PHOSPHOR_AMBER}]       MONIKA — UPGRADE TO FULL PACKAGE                      [/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")

        settings = load_settings()
        curr_tier = get_installation_tier(settings)

        if curr_tier == "full":
            console.print(f"{stamp_ok('ALREADY FULL')} System is already configured in Full Package mode.")
            re_run = Confirm.ask("Re-run upgrade checklist to verify all components?", default=False)
            if not re_run:
                return 0

        # Display upgrade summary table
        tbl = Table(title=f"[{PHOSPHOR_AMBER}]Upgrade Components Overview[/]", box=LEDGER_BOX, header_style=f"bold {PHOSPHOR_AMBER}")
        tbl.add_column("Component", style=f"bold {BRASS}")
        tbl.add_column("Trial Mode", style=MUTED)
        tbl.add_column("Full Package Target", style=PAPER)

        tbl.add_row("Database", "Zero-config SQLite", "PostgreSQL 16+ (multi-process)")
        tbl.add_row("Dashboard UI", "CLI + Telegram only", "React 19 / Vite Web Cockpit")
        tbl.add_row("AI Routing", "Direct Gemini Pool", "9Router Gateway + Multi-Provider")
        tbl.add_row("Forecasting", "ATR / ADR Indicators", "Google TimesFM 3.0 Neural Quantiles")
        tbl.add_row("Execution", "Paper Trading Sandbox", "Dual Engine (Paper + MT5 Live Bridge)")
        console.print(tbl)
        console.print()

        auto_yes = getattr(args, "yes", False)
        if not auto_yes:
            if not Confirm.ask("Proceed with upgrading Monika to Full Package?", default=True):
                console.print(f"\n[{MUTED}]Upgrade cancelled by operator.[/{MUTED}]\n")
                return 0

        env_updates: Dict[str, str] = {}
        settings_updates: Dict[str, Any] = {"installation_tier": "full"}
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # ── 1. Database Upgrade: SQLite -> PostgreSQL ──
        console.print(f"\n{stamp_info('DATABASE')} [bold {BRASS}]Phase 1: PostgreSQL Configuration[/]")
        curr_db = os.environ.get("DATABASE_URL", "")
        if "postgresql" not in curr_db.lower():
            console.print(f"  [{MUTED}]Current DB is SQLite. Full Package requires PostgreSQL for concurrent processing.[/{MUTED}]")
            pg_url = Prompt.ask(
                "PostgreSQL Connection URL (asyncpg format)",
                default="postgresql+asyncpg://postgres:postgres@localhost:5432/trading_agent"
            )
            env_updates["DATABASE_URL"] = pg_url

            # Test connection
            from cli.setup_wizard import SetupWizard
            wizard = SetupWizard()
            pg_ok = wizard._test_db_connection(pg_url)

            if not pg_ok:
                if Confirm.ask("PostgreSQL connection failed. Spawn local Docker PostgreSQL container (monika-postgres)?", default=True):
                    try:
                        console.print(f"  {stamp_info('DOCKER')} Spawning container monika-postgres...")
                        run_res = subprocess.run([
                            "docker", "run", "-d",
                            "--name", "monika-postgres",
                            "-e", "POSTGRES_PASSWORD=postgres",
                            "-e", "POSTGRES_DB=trading_agent",
                            "-p", "5432:5432",
                            "postgres:16-alpine"
                        ], capture_output=True, text=True)
                        if run_res.returncode == 0:
                            console.print(f"  {stamp_ok('DOCKER')} PostgreSQL container active! Waiting 3s...")
                            import time
                            time.sleep(3)
                            pg_ok = wizard._test_db_connection(pg_url)
                        else:
                            console.print(f"  {stamp_warn('DOCKER')} Docker error: {run_res.stderr or run_res.stdout}")
                    except Exception as d_err:
                        console.print(f"  {stamp_warn('DOCKER')} Docker execution failed: {d_err}")

            if pg_ok or Confirm.ask("Continue with database migration (alembic upgrade head)?", default=True):
                try:
                    console.print(f"  {stamp_info('ALEMBIC')} Running database migrations...")
                    m_res = subprocess.run(["alembic", "upgrade", "head"], cwd=base_dir, capture_output=True, text=True)
                    if m_res.returncode == 0:
                        console.print(f"  {stamp_ok('MIGRATION')} PostgreSQL schema initialized to latest revision.")
                    else:
                        console.print(f"  {stamp_warn('MIGRATION')} Alembic warning: {m_res.stderr or m_res.stdout}")
                except Exception as m_err:
                    console.print(f"  {stamp_warn('MIGRATION')} Failed to run alembic: {m_err}")
        else:
            console.print(f"  {stamp_ok('DATABASE')} PostgreSQL already configured ({curr_db[:35]}...).")

        # ── 2. Dashboard Frontend (Node.js & npm install) ──
        console.print(f"\n{stamp_info('DASHBOARD')} [bold {BRASS}]Phase 2: React 19 Web Dashboard[/]")
        skip_npm = getattr(args, "skip_npm", False)
        frontend_dir = os.path.join(base_dir, "logging_observability", "dashboard", "frontend")
        node_bin = shutil.which("node")
        npm_bin = shutil.which("npm")

        if skip_npm:
            console.print(f"  [{MUTED}]Skipping npm dependencies install per flag.[/{MUTED}]")
        elif not npm_bin:
            console.print(f"  {stamp_warn('NODE MISSING')} npm/Node.js is not found on PATH.")
            console.print(f"  [{MUTED}]Please install Node.js (v18+) from https://nodejs.org to use the Web Dashboard.[/{MUTED}]")
        else:
            node_modules = os.path.join(frontend_dir, "node_modules")
            if not os.path.exists(node_modules) or Confirm.ask("Install/update Web Dashboard npm dependencies?", default=True):
                console.print(f"  {stamp_info('NPM')} Installing dashboard dependencies in {frontend_dir}...")
                try:
                    # Windows shell handling
                    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
                    n_res = subprocess.run([npm_cmd, "install", "--silent"], cwd=frontend_dir, capture_output=True, text=True)
                    if n_res.returncode == 0:
                        console.print(f"  {stamp_ok('NPM')} Web Dashboard dependencies ready.")
                    else:
                        console.print(f"  {stamp_warn('NPM')} npm install reported warnings: {n_res.stderr[:200]}")
                except Exception as npm_err:
                    console.print(f"  {stamp_warn('NPM')} Could not run npm: {npm_err}")
            else:
                console.print(f"  {stamp_ok('NPM')} node_modules already exists.")

        # ── 3. 9Router AI Gateway ──
        console.print(f"\n{stamp_info('9ROUTER')} [bold {BRASS}]Phase 3: 9Router AI Gateway[/]")
        npx_bin = shutil.which("npx")
        router_bin = shutil.which("9router")
        if router_bin or npx_bin:
            enable_9r = Confirm.ask("Enable 9Router AI Gateway (localhost:20128) for smart model load balancing?", default=True)
            if enable_9r:
                settings_updates.setdefault("llm", {}).setdefault("nine_router", {})["enabled"] = True
                console.print(f"  {stamp_ok('9ROUTER')} 9Router enabled in configuration.")
        else:
            console.print(f"  [{MUTED}]npx not found. 9Router can be enabled later after installing Node.js.[/{MUTED}]")

        # ── 4. TimesFM Volatility Weights (Optional) ──
        console.print(f"\n{stamp_info('TIMESFM')} [bold {BRASS}]Phase 4: Google TimesFM 3.0 Forecasting[/]")
        skip_weights = getattr(args, "skip_weights", False)
        if not skip_weights:
            weights_script = os.path.join(base_dir, "scripts", "download_timesfm_weights.py")
            if os.path.exists(weights_script):
                if Confirm.ask("Download Google TimesFM 3.0 model weights (~1.3 GB from Hugging Face)?", default=False):
                    try:
                        console.print(f"  {stamp_info('WEIGHTS')} Running download_timesfm_weights.py...")
                        w_res = subprocess.run([sys.executable, weights_script], cwd=base_dir)
                        if w_res.returncode == 0:
                            console.print(f"  {stamp_ok('TIMESFM')} Weights successfully downloaded and verified.")
                        else:
                            console.print(f"  {stamp_warn('TIMESFM')} TimesFM weights download completed with non-zero exit code.")
                    except Exception as w_err:
                        console.print(f"  {stamp_warn('TIMESFM')} Could not execute weights script: {w_err}")
            else:
                console.print(f"  [{MUTED}]TimesFM download script not found at scripts/download_timesfm_weights.py.[/{MUTED}]")
        else:
            console.print(f"  [{MUTED}]Skipped TimesFM weights download.[/{MUTED}]")

        # ── 5. Save Configuration & Marker ──
        console.print(f"\n{stamp_info('PERSIST')} [bold {BRASS}]Finalizing Upgrade Settings[/]")
        if env_updates:
            EnvFileManager.update_env_values(env_updates)
            for k, v in env_updates.items():
                os.environ[k] = v
            console.print(f"  {stamp_ok('ENV')} Environment credentials updated in .env.")

        settings_path = "config/settings.yaml"
        if not os.path.exists(settings_path) and os.path.exists("trading-agent/config/settings.yaml"):
            settings_path = "trading-agent/config/settings.yaml"

        try:
            AtomicConfigWriter.update_in_place(settings_path, settings_updates)
            console.print(f"  {stamp_ok('SETTINGS')} settings.yaml updated with Full Package tier.")
        except Exception as e:
            console.print(f"  {stamp_warn('SETTINGS')} Could not atomically update {settings_path}: {e}")

        # Update .monika_tier file
        try:
            root_dir = base_dir
            if os.path.basename(root_dir) == "trading-agent":
                root_dir = os.path.dirname(root_dir)
            tier_file = os.path.join(root_dir, ".monika_tier")
            with open(tier_file, "w", encoding="utf-8") as f:
                f.write("full\n")
        except Exception:
            pass

        # ── 6. Run Doctor Check ──
        console.print(f"\n{stamp_info('DOCTOR')} Running system diagnostics verification...")
        from cli.doctor import SystemDoctor
        doc = SystemDoctor(fix=True, live_probes=True, verbose=False)
        await doc.run_diagnostics()
        doc.render_report()

        console.print(f"\n[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]")
        console.print(f"{stamp_ok('UPGRADE COMPLETE')} Monika is now upgraded to FULL PACKAGE!")
        console.print(f"[{MUTED}]You can now launch all systems including Web Dashboard:[/{MUTED}]")
        console.print(f"  • Windows: [bold {BRASS}]start_monika.bat[/]")
        console.print(f"  • Linux:   [bold {BRASS}]./start_monika.sh[/]")
        console.print(f"[{PHOSPHOR_AMBER}]══════════════════════════════════════════════════════════════[/]\n")
        return 0
