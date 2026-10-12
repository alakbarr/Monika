# ==============================================================================
# File: tests/cli/test_plugin_cli.py
# ==============================================================================

import pytest
from unittest.mock import MagicMock, patch
from cli.plugins import cmd_plugin_list, cmd_plugin_info, handle_plugin_command
from harness.contract import TradingPlugin, PluginMetadata, PluginCategory


def test_cmd_plugin_list(capsys):
    args = MagicMock()
    args.plugin_action = "list"
    res = handle_plugin_command(args)
    assert res == 0


def test_cmd_plugin_info_missing_arg(capsys):
    args = MagicMock()
    args.plugin_action = "info"
    args.package_name = None
    res = handle_plugin_command(args)
    assert res == 1


def test_cmd_plugin_info_found():
    dummy_meta = PluginMetadata(
        id="test_dummy_plugin",
        name="Test Dummy",
        version="1.2.3",
        category=PluginCategory.TOOL,
        description="A test tool plugin",
    )
    dummy_plugin = MagicMock()
    dummy_plugin.metadata = dummy_meta
    dummy_plugin.status = "ACTIVE"
    dummy_plugin.config = {"foo": "bar"}

    with patch("cli.plugins._create_engine") as mock_engine_fn:
        mock_eng = MagicMock()
        mock_eng.get_plugin.return_value = dummy_plugin
        mock_engine_fn.return_value = mock_eng

        args = MagicMock()
        args.plugin_action = "info"
        args.package_name = "test_dummy_plugin"
        res = handle_plugin_command(args)
        assert res == 0
