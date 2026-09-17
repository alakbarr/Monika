# ==============================================================================
# File: cli/theme.py
# Description: Theme Engine for CLI & Textual TUI (Retro-Vintage & Presets)
# ==============================================================================

"""
Central theme definitions for Monika AI Trading Agent terminal interfaces.

Includes:
- Default retro-vintage ledger & telegraph aesthetic.
- ThemePack semantic token system with 4 presets:
  1. retro_vintage (default): Amber phosphor, deep ledger green/wax red, charcoal.
  2. modern_dark: Slate, blue-indigo accents, clean high-tech dark.
  3. high_contrast: Pure black/white with vivid red/green/yellow for accessibility.
  4. daylight: Warm parchment light mode for bright ambient environments.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from rich import box
from rich.console import Console
from rich.theme import Theme

# Core color constants (retro_vintage defaults)
PHOSPHOR_AMBER = "#E8B94A"
BRASS = "#F5BD38"
BULL_PROFIT = "#4CAF50"
BEAR_LOSS = "#E25B45"
MUTED = "#877F75"
DIM = "#5C544C"
PAPER = "#D8D2C2"
CHARCOAL = "#14120E"
SURFACE = "#1C1917"
BORDER = "#3A352A"

MONIKA_THEME = Theme({
    "primary": PHOSPHOR_AMBER,
    "brass": BRASS,
    "profit": BULL_PROFIT,
    "loss": BEAR_LOSS,
    "warning": BRASS,
    "muted": MUTED,
    "dim": DIM,
    "paper": PAPER,
    "info": BRASS,
    "stamp.ok": f"bold {BULL_PROFIT}",
    "stamp.err": f"bold {BEAR_LOSS}",
    "stamp.warn": f"bold {BRASS}",
    "stamp.info": f"bold {BRASS}",
    "stamp.exec": f"bold {PHOSPHOR_AMBER}",
})

LEDGER_BOX = box.DOUBLE


@dataclass
class ThemePack:
    """Semantic color token palette for CLI and Textual UI."""

    name: str = "retro_vintage"
    # Core brand & state colors
    primary: str = PHOSPHOR_AMBER
    accent: str = BRASS
    profit: str = BULL_PROFIT
    loss: str = BEAR_LOSS
    muted: str = MUTED
    dim: str = DIM
    text: str = PAPER
    # Surfaces & structure
    background: str = CHARCOAL
    surface: str = SURFACE
    border: str = BORDER
    # Badges / Stamps
    stamp_ok_color: str = BULL_PROFIT
    stamp_err_color: str = BEAR_LOSS
    stamp_warn_color: str = BRASS
    stamp_exec_color: str = PHOSPHOR_AMBER
    # Analysis Tree steps
    step_running: str = PHOSPHOR_AMBER
    step_completed: str = BULL_PROFIT
    step_failed: str = BEAR_LOSS
    step_waiting: str = MUTED
    # Context / Bar gauges
    gauge_ok: str = BULL_PROFIT
    gauge_warn: str = BRASS
    gauge_critical: str = BEAR_LOSS


THEMES: Dict[str, ThemePack] = {
    "retro_vintage": ThemePack(name="retro_vintage"),
    "modern_dark": ThemePack(
        name="modern_dark",
        primary="#60A5FA",
        accent="#818CF8",
        profit="#10B981",
        loss="#EF4444",
        muted="#64748B",
        dim="#475569",
        text="#E2E8F0",
        background="#0F172A",
        surface="#1E293B",
        border="#334155",
        stamp_ok_color="#10B981",
        stamp_err_color="#EF4444",
        stamp_warn_color="#F59E0B",
        stamp_exec_color="#60A5FA",
        step_running="#60A5FA",
        step_completed="#10B981",
        step_failed="#EF4444",
        step_waiting="#64748B",
        gauge_ok="#10B981",
        gauge_warn="#F59E0B",
        gauge_critical="#EF4444",
    ),
    "high_contrast": ThemePack(
        name="high_contrast",
        primary="#FFFFFF",
        accent="#FFFF00",
        profit="#00FF00",
        loss="#FF0000",
        muted="#888888",
        dim="#555555",
        text="#FFFFFF",
        background="#000000",
        surface="#111111",
        border="#FFFFFF",
        stamp_ok_color="#00FF00",
        stamp_err_color="#FF0000",
        stamp_warn_color="#FFFF00",
        stamp_exec_color="#FFFFFF",
        step_running="#FFFF00",
        step_completed="#00FF00",
        step_failed="#FF0000",
        step_waiting="#888888",
        gauge_ok="#00FF00",
        gauge_warn="#FFFF00",
        gauge_critical="#FF0000",
    ),
    "daylight": ThemePack(
        name="daylight",
        primary="#92400E",
        accent="#A16207",
        profit="#166534",
        loss="#991B1B",
        muted="#78716C",
        dim="#A8A29E",
        text="#1C1917",
        background="#FFFBEB",
        surface="#FEF3C7",
        border="#D97706",
        stamp_ok_color="#166534",
        stamp_err_color="#991B1B",
        stamp_warn_color="#A16207",
        stamp_exec_color="#92400E",
        step_running="#92400E",
        step_completed="#166534",
        step_failed="#991B1B",
        step_waiting="#78716C",
        gauge_ok="#166534",
        gauge_warn="#A16207",
        gauge_critical="#991B1B",
    ),
}


def get_theme(name: Optional[str] = None) -> ThemePack:
    """Retrieve ThemePack by name; defaults to retro_vintage."""
    if not name:
        return THEMES["retro_vintage"]
    normalized = name.strip().lower().replace("-", "_")
    return THEMES.get(normalized, THEMES["retro_vintage"])


def get_console() -> Console:
    """Return a Rich Console preconfigured with Monika's retro-vintage theme."""
    return Console(theme=MONIKA_THEME)


def stamp_ok(text: str = "OK") -> str:
    return f"[{BULL_PROFIT}][ {text} ][/]"


def stamp_err(text: str = "FAILED") -> str:
    return f"[{BEAR_LOSS}][ {text} ][/]"


def stamp_warn(text: str = "WARNING") -> str:
    return f"[{BRASS}][ {text} ][/]"


def stamp_info(text: str = "INFO") -> str:
    return f"[{BRASS}][ {text} ][/]"


def stamp_exec(text: str = "EXECUTE") -> str:
    return f"[{PHOSPHOR_AMBER}][ {text} ][/]"


def build_tui_css(theme: Optional[ThemePack] = None) -> str:
    """Generate theme-aware CSS for Textual TUI dashboard."""
    t = theme or THEMES["retro_vintage"]
    return f"""
Screen {{
    background: {t.background};
    color: {t.text};
}}

#ticker {{
    height: 3;
    background: {t.surface};
    color: {t.primary};
    padding: 0 1;
    border-bottom: solid {t.border};
}}

#main_tabs {{
    height: 1fr;
}}

TabbedContent {{
    background: {t.background};
    color: {t.text};
}}

Tabs {{
    background: {t.surface};
    color: {t.muted};
    border-bottom: solid {t.border};
}}

Tab {{
    padding: 0 2;
    color: {t.muted};
}}

Tabs > Tab.-active,
Tab.-active {{
    color: {t.background} !important;
    background: {t.primary} !important;
    text-style: bold;
}}

#tab_overview, #tab_analysis, #tab_performance, #tab_chat {{
    height: 1fr;
    padding: 0;
}}

#main_panels {{
    height: 1fr;
    margin: 0;
    padding: 0;
}}

#positions_container {{
    width: 55%;
    height: 100%;
    border: double {t.accent};
    background: {t.surface};
    padding: 0;
}}

#activity_container {{
    width: 45%;
    height: 100%;
    border: double {t.border};
    background: {t.surface};
    padding: 0;
}}

.panel_title {{
    background: {t.surface};
    color: {t.primary};
    text-style: bold;
    padding: 0 1;
    height: 2;
    border-bottom: solid {t.accent};
}}

#positions_table {{
    height: 1fr;
    background: {t.background};
}}

DataTable {{
    background: {t.background};
}}

DataTable > .datatable--header {{
    background: {t.surface};
    color: {t.primary};
    text-style: bold;
}}

DataTable > .datatable--cursor {{
    background: #252219;
    color: {t.primary};
    text-style: bold;
}}

Toast {{
    background: {t.surface};
    color: {t.text};
    border: solid {t.border};
}}

.toast--title {{
    text-style: bold;
    color: {t.primary};
}}

Toast.-information {{
    border-left: outer {t.accent};
}}

Toast.-warning {{
    border-left: outer {t.stamp_warn_color};
}}

Toast.-error {{
    border-left: outer {t.stamp_err_color};
}}

#activity_log {{
    height: 1fr;
    background: {t.background};
    color: {t.text};
}}

#analysis_horizontal, #perf_horizontal {{
    height: 1fr;
    margin: 0;
    padding: 0;
}}

#analysis_container {{
    width: 50%;
    height: 100%;
    border: double {t.accent};
    background: {t.surface};
    padding: 0;
}}

#cycle_tree {{
    height: 1fr;
    background: {t.background};
    color: {t.text};
    padding: 1;
}}

#analysis_log_container {{
    width: 50%;
    height: 100%;
    border: double {t.border};
    background: {t.surface};
    padding: 0;
}}

#analysis_detail_log {{
    height: 1fr;
    background: {t.background};
    color: {t.text};
}}

#perf_left_container {{
    width: 45%;
    height: 100%;
    border: double {t.accent};
    background: {t.surface};
    padding: 0;
}}

#perf_right_container {{
    width: 55%;
    height: 100%;
    border: double {t.border};
    background: {t.surface};
    padding: 0;
}}

#perf_sparkline {{
    padding: 1;
    color: {t.primary};
    background: {t.background};
    height: auto;
}}

#performance_container {{
    height: 1fr;
    padding: 0;
    background: {t.background};
}}

#cmd_input {{
    dock: bottom;
    height: 3;
    background: {t.surface};
    color: {t.primary};
    border-top: solid {t.border};
    border: solid {t.accent};
}}

#status_bar {{
    dock: bottom;
    height: 1;
    background: {t.surface};
    color: {t.muted};
    padding: 0 1;
    border-top: solid {t.border};
}}

Footer {{
    background: {t.surface};
    color: {t.muted};
}}
"""


def build_chat_css(theme: Optional[ThemePack] = None) -> str:
    """Generate theme-aware CSS for Textual chat screen."""
    t = theme or THEMES["retro_vintage"]
    return f"""
ChatScreen {{
    background: {t.background};
    color: {t.text};
}}

#chat_header {{
    height: 2;
    background: {t.surface};
    color: {t.primary};
    padding: 0 1;
    border-bottom: solid {t.accent};
}}

#transcript {{
    height: 1fr;
    background: {t.background};
    color: {t.text};
    padding: 1 2;
}}

#streaming_output {{
    height: auto;
    max-height: 4;
    background: {t.background};
    color: {t.primary};
    padding: 0 2;
}}

#chat_input {{
    dock: bottom;
    background: {t.surface};
    color: {t.text};
    border: solid {t.accent};
    height: 3;
}}
"""


def persist_theme_to_settings(theme_name: str, config_path: Optional[str] = None) -> bool:
    """Persist the selected theme name into settings.yaml under ui.theme (Q3)."""
    import os
    import yaml

    norm_name = theme_name.strip().lower().replace("-", "_")
    if norm_name not in THEMES:
        return False

    candidates = [
        config_path,
        os.getenv("SETTINGS_PATH"),
        "config/settings.yaml",
        "trading-agent/config/settings.yaml",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.yaml"),
    ]
    target_path = None
    for c in candidates:
        if c and os.path.exists(c):
            target_path = os.path.abspath(c)
            break

    if not target_path:
        return False

    # 1. Try ruamel.yaml for comment-preserving round-trip
    try:
        from ruamel.yaml import YAML
        ruamel_yaml = YAML()
        ruamel_yaml.preserve_quotes = True
        with open(target_path, "r", encoding="utf-8") as f:
            doc = ruamel_yaml.load(f)
        if doc is None:
            doc = {}
        if "ui" not in doc or not isinstance(doc["ui"], dict):
            doc["ui"] = {}
        doc["ui"]["theme"] = norm_name
        with open(target_path, "w", encoding="utf-8") as f:
            ruamel_yaml.dump(doc, f)
        return True
    except ImportError:
        pass
    except Exception:
        pass

    # 2. Fallback: Surgical regex replacement to preserve comments and structure 100%
    try:
        import re
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        ui_match = re.search(r"^(ui:\s*)$", content, flags=re.MULTILINE)
        if ui_match:
            theme_pattern = r"(^ui:\s*\n(?:[ \t]*#[^\n]*\n)*[ \t]*theme:\s*)[^\n]+"
            if re.search(theme_pattern, content, flags=re.MULTILINE):
                new_content = re.sub(
                    theme_pattern,
                    rf'\g<1>"{norm_name}"',
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )
            else:
                idx = ui_match.end()
                new_content = content[:idx] + f'\n  theme: "{norm_name}"' + content[idx:]
        else:
            new_content = content.rstrip() + f'\n\nui:\n  theme: "{norm_name}"\n'

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception:
        return False
