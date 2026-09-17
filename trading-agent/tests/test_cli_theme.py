"""
Unit Tests for Retro-Vintage CLI Theme (cli/theme.py).
"""
import pytest
from cli.theme import (
    PHOSPHOR_AMBER,
    BRASS,
    BULL_PROFIT,
    BEAR_LOSS,
    MUTED,
    PAPER,
    CHARCOAL,
    LEDGER_BOX,
    MONIKA_THEME,
    get_console,
    stamp_ok,
    stamp_err,
    stamp_warn,
    stamp_info,
    stamp_exec,
    build_tui_css,
    build_chat_css,
)
from rich import box


def test_theme_color_constants():
    """Verify retro vintage color tokens."""
    assert PHOSPHOR_AMBER == "#E8B94A"
    assert BRASS == "#F5BD38"
    assert BULL_PROFIT == "#4CAF50"
    assert BEAR_LOSS == "#E25B45"
    assert CHARCOAL == "#14120E"
    assert LEDGER_BOX == box.DOUBLE


def test_stamp_formatters():
    """Verify stamp formatters return bracketed badges."""
    assert "[ OK ]" in stamp_ok()
    assert "[ FAILED ]" in stamp_err()
    assert "[ WARNING ]" in stamp_warn()
    assert "[ INFO ]" in stamp_info()
    assert "[ EXECUTE ]" in stamp_exec()

    # Custom text
    assert "[ SUCCESS ]" in stamp_ok("SUCCESS")
    assert "[ REJECTED ]" in stamp_err("REJECTED")


def test_get_console():
    """Verify preconfigured rich console."""
    console = get_console()
    assert console is not None
    assert getattr(console, "_theme_stack", None) is not None


def test_build_tui_css():
    """Verify TUI CSS includes retro tokens and zero high-radius borders."""
    css = build_tui_css()
    assert PHOSPHOR_AMBER in css
    assert CHARCOAL in css
    assert "border-radius" not in css or "border-radius: 0" in css or "border-radius: 2px" in css


def test_build_chat_css():
    """Verify chat screen CSS includes retro styling."""
    css = build_chat_css()
    assert PHOSPHOR_AMBER in css
    assert CHARCOAL in css
