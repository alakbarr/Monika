import pytest
import os
from unittest.mock import patch, mock_open
from config.settings import load_settings, load_all_config

class TestSettings:

    @patch('shutil.copy2')
    @patch('os.path.exists', side_effect=lambda p: p == "dummy_path")
    @patch('builtins.open', new_callable=mock_open, read_data="test_key: test_val")
    def test_load_settings_success(self, mock_file, mock_exists, mock_copy):
        settings = load_settings("dummy_path")
        assert settings["test_key"] == "test_val"
        assert settings.get("_config_version") >= 1
        mock_file.assert_called_once_with("dummy_path", "r", encoding="utf-8")

    @patch('os.path.exists', return_value=False)
    def test_load_settings_not_found(self, mock_exists):
        with pytest.raises(FileNotFoundError):
            load_settings("dummy_path")

    @patch('config.settings.load_settings', return_value={"test_key": "test_val"})
    def test_load_all_config(self, mock_load_settings):
        config = load_all_config()
        assert config["test_key"] == "test_val"
        assert "llm" in config
        mock_load_settings.assert_called_once()
