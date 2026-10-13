# ==============================================================================
# File: scripts/capture_tui_screenshots.py
# Description: Automated screenshot capture for all Monika Textual TUI screens
# ==============================================================================

import asyncio
import os
import sys
from pathlib import Path

# Add src directory to Python path
REPO_ROOT = Path(__file__).resolve().parent.parent
_src_dir = REPO_ROOT / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
try:
    from monika.infrastructure.infra.legacy_compat import install_legacy_compat

    install_legacy_compat()
except Exception:
    pass

from monika.interfaces.cli.tui import TradingDashboard
from textual.widgets import TabbedContent

OUTPUT_DIR = REPO_ROOT / "docs" / "images" / "dashboard"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TUI_TABS = [
    ("tab_overview", "01_tui_overview"),
    ("tab_analysis", "02_tui_analysis"),
    ("tab_signals", "03_tui_signals"),
    ("tab_risk", "04_tui_risk"),
    ("tab_performance", "05_tui_performance"),
    ("tab_market", "06_tui_market"),
    ("tab_plugins", "07_tui_plugins"),
    ("tab_benchmark", "08_tui_benchmark"),
    ("tab_chat", "09_tui_chat"),
]

THEMES = [
    ("retro_vintage", "dark"),
    ("daylight", "light"),
]


async def capture_theme_screens(theme_name: str, mode_label: str):
    print(f"\n=== Capturing TUI Screens in {mode_label.upper()} Mode ({theme_name}) ===")
    app = TradingDashboard(theme_name=theme_name)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        main_tabs = app.query_one("#main_tabs", TabbedContent)

        # 1. Capture All 9 Tabs
        for tab_id, tab_label in TUI_TABS:
            main_tabs.active = tab_id
            await pilot.pause(0.3)
            svg = app.export_screenshot()
            svg_filename = f"{tab_label}_{mode_label}.svg"
            svg_path = OUTPUT_DIR / svg_filename
            svg_path.write_text(svg, encoding="utf-8")
            print(f"[OK] Saved {svg_filename}")

        # 2. Capture Kill Switch Modal
        await pilot.press("k")
        await pilot.pause(0.3)
        modal_svg = app.export_screenshot()
        modal_filename = f"10_tui_modal_kill_{mode_label}.svg"
        (OUTPUT_DIR / modal_filename).write_text(modal_svg, encoding="utf-8")
        print(f"[OK] Saved {modal_filename}")

        # Dismiss modal with Escape
        await pilot.press("escape")
        await pilot.pause(0.2)


async def main():
    for theme_name, mode_label in THEMES:
        await capture_theme_screens(theme_name, mode_label)
    print("\n[SUCCESS] All TUI SVGs captured successfully.")


if __name__ == "__main__":
    asyncio.run(main())
