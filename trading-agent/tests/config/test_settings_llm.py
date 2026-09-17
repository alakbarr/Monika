import pytest
from config.settings import load_all_config
from unittest.mock import patch, mock_open

@patch('config.settings.load_settings')
def test_load_all_config_adds_llm_default(mock_load_settings):
    # Test when llm is missing
    mock_load_settings.return_value = {"trading": {}}
    
    settings = load_all_config()
    
    assert "llm" in settings
    assert settings["llm"]["providers"] == {}
    assert settings["llm"]["model_catalog"] == {}
    assert settings["llm"]["task_roles"] == {}

@patch('config.settings.load_settings')
def test_load_all_config_preserves_llm(mock_load_settings):
    # Test when llm exists
    mock_load_settings.return_value = {
        "llm": {
            "providers": {"gemini": {"enabled": True}},
            "model_catalog": {},
            "task_roles": {}
        }
    }
    
    settings = load_all_config()
    
    assert "llm" in settings
    assert settings["llm"]["providers"]["gemini"]["enabled"] is True
