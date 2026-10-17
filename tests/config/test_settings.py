import pytest
import os
from unittest.mock import patch, mock_open
from monika.core.config.settings import load_settings, load_all_config


class TestSettings:
    @patch("shutil.copy2")
    @patch("os.path.exists", side_effect=lambda p: p == "dummy_path")
    @patch("builtins.open", new_callable=mock_open, read_data="test_key: test_val")
    def test_load_settings_success(self, mock_file, mock_exists, mock_copy):
        settings = load_settings("dummy_path")
        assert settings["test_key"] == "test_val"
        assert settings.get("_config_version") >= 1
        mock_file.assert_called_once_with("dummy_path", "r", encoding="utf-8")

    @patch("os.path.exists", return_value=False)
    def test_load_settings_not_found(self, mock_exists):
        with pytest.raises(FileNotFoundError):
            load_settings("dummy_path")

    @patch("monika.core.config.settings.load_settings", return_value={"test_key": "test_val"})
    def test_load_all_config(self, mock_load_settings):
        config = load_all_config()
        assert config["test_key"] == "test_val"
        assert "llm" in config
        mock_load_settings.assert_called_once()


def test_get_paper_trading_config_normalization():
    from monika.core.config.settings import get_paper_trading_config

    # Case 1: Raw boolean True
    cfg1 = get_paper_trading_config({"paper_trading": True})
    assert isinstance(cfg1, dict)
    assert cfg1["enabled"] is True
    assert cfg1["initial_balance"] == 10000.0
    assert cfg1.get("streak_loss_policy") == "warn_and_scale"

    # Case 2: Raw boolean False
    cfg2 = get_paper_trading_config({"paper_trading": False})
    assert isinstance(cfg2, dict)
    assert cfg2["enabled"] is False

    # Case 3: Nested boolean in trading.paper_trading
    cfg3 = get_paper_trading_config({"trading": {"paper_trading": True}})
    assert isinstance(cfg3, dict)
    assert cfg3["enabled"] is True

    # Case 4: Dict override
    cfg4 = get_paper_trading_config({"paper_trading": {"enabled": False, "initial_balance": 50000.0}})
    assert isinstance(cfg4, dict)
    assert cfg4["enabled"] is False
    assert cfg4["initial_balance"] == 50000.0
    assert cfg4["streak_loss_policy"] == "warn_and_scale"

    # Case 5: Empty / None
    cfg5 = get_paper_trading_config(None)
    assert isinstance(cfg5, dict)
    assert cfg5["enabled"] is True
