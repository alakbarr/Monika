# ==============================================================================
# File: tests/cli/test_theme_packs.py
# Description: Unit Tests for ThemePack Palettes and CSS
# ==============================================================================

import pytest
from cli.theme import THEMES, get_theme, ThemePack, build_tui_css, build_chat_css


def test_theme_presets_exist():
    """Verify the 4 required presets exist."""
    required = ["retro_vintage", "modern_dark", "high_contrast", "daylight"]
    for r in required:
        assert r in THEMES
        theme = get_theme(r)
        assert isinstance(theme, ThemePack)
        assert theme.name == r
        assert theme.primary
        assert theme.background


def test_get_theme_fallback():
    """Unknown theme falls back to retro_vintage."""
    theme = get_theme("non_existent_theme")
    assert theme.name == "retro_vintage"

    theme_none = get_theme(None)
    assert theme_none.name == "retro_vintage"


def test_theme_tui_css_custom():
    """TUI CSS reflects theme-specific colors."""
    dark_css = build_tui_css(THEMES["modern_dark"])
    assert THEMES["modern_dark"].primary in dark_css
    assert THEMES["modern_dark"].background in dark_css

    daylight_css = build_tui_css(THEMES["daylight"])
    assert THEMES["daylight"].background in daylight_css


def test_persist_theme_to_settings(tmp_path):
    """Verify persisting theme to yaml updates ui.theme (Q3)."""
    import yaml
    from cli.theme import persist_theme_to_settings

    dummy_cfg = tmp_path / "settings.yaml"
    dummy_cfg.write_text("app_name: Monika\nui:\n  theme: retro_vintage\n", encoding="utf-8")

    ok = persist_theme_to_settings("modern_dark", config_path=str(dummy_cfg))
    assert ok is True

    with open(dummy_cfg, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["ui"]["theme"] == "modern_dark"

    # Test invalid theme rejection
    assert persist_theme_to_settings("invalid_pack", config_path=str(dummy_cfg)) is False
