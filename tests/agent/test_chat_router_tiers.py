"""Tests for chat model tier detection and WebSocket tier telemetry."""

import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from monika.application.agent.chat.prompt_builder import PromptBuilderMixin
from monika.interfaces.dashboard.api import app


class DummyPromptBuilder(PromptBuilderMixin):
    def __init__(self):
        pass


def test_detect_model_preference_tier_aliases():
    """Verify that _detect_model_preference supports clean tier prefixes and backward-compatible aliases."""
    builder = DummyPromptBuilder()

    # Tier 1 (Fast / Lite)
    for pfx in ["/fast", "/quick", "/lite", "/tier1"]:
        assert builder._detect_model_preference(f"{pfx} analyze price") == "tier_lite"
        assert builder._detect_model_preference(f"{pfx.upper()} analyze price") == "tier_lite"

    # Tier 2 (Balanced / Medium)
    for pfx in ["/medium", "/mid", "/balanced", "/tier2"]:
        assert builder._detect_model_preference(f"{pfx} check orders") == "tier_medium"
        assert builder._detect_model_preference(f"{pfx.upper()} check orders") == "tier_medium"

    # Tier 3 (Reasoning / Deep)
    for pfx in ["/analyze", "/analisis", "/deep", "/reasoning", "/complex", "/tier3"]:
        assert builder._detect_model_preference(f"{pfx} evaluate EURUSD") == "tier_deep"
        assert builder._detect_model_preference(f"{pfx.upper()} evaluate EURUSD") == "tier_deep"

    # Tier 4 (Deep Research / Pro)
    for pfx in ["/research", "/pro"]:
        assert builder._detect_model_preference(f"{pfx} global macro outlook") == "deep_research"
        assert builder._detect_model_preference(f"{pfx.upper()} global macro outlook") == "deep_research"

    # Auto fallback
    assert builder._detect_model_preference("halo monika") == "auto"
    assert builder._detect_model_preference("what is the current spread?") == "auto"


def test_websocket_connection_established_includes_tier_models():
    """Verify that WebSocket handshake connection_established payload includes tier_models mapping."""
    client = TestClient(app)

    env = {"DASHBOARD_API_KEYS": "operator:ops_key", "DASHBOARD_API_KEY": ""}
    with patch.dict(os.environ, env):
        with client.websocket_connect("/ws/agent-chat?token=ops_key&session_id=dash:test_tier_models") as ws:
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["role"] == "operator"
            assert "tier_models" in init_msg
            tier_models = init_msg["tier_models"]
            assert isinstance(tier_models, dict)
            assert "fast" in tier_models
            assert "medium" in tier_models
            assert "complex" in tier_models
            assert "deep_research" in tier_models
