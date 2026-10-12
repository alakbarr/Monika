"""
Unit tests for Log Redactor (H7), Container (I1), Spillover (I6), Plugin Hooks (M1), and Credential Pool (M2).
"""
import pytest
import asyncio
import tempfile
import os
from utils.infra.log_redactor import redact_sensitive_text
from utils.infra.container import ServiceContainer
from utils.llm.context_compaction import spill_tool_output
from utils.plugins.manager import PluginManager, PluginHook
from utils.api.credential_pool import CredentialPool


def test_h7_log_redactor_masks_secrets():
    """H7: Log redactor masks sensitive API keys, tokens, and database passwords."""
    raw_log = (
        "Connected using postgresql://postgres:SuperSecretP@ss@localhost:5432/tradingdb. "
        "Anthropic key: sk-ant-api03-abcdef1234567890abcdef1234567890. "
        "OpenAI key: sk-proj-1234567890abcdef1234567890abcdef. "
        "Gemini key: AIzaSyD1234567890abcdef1234567890abcdef. "
        "Bot token: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ123456789. "
        "Bearer token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    )

    redacted = redact_sensitive_text(raw_log)

    assert "SuperSecretP@ss" not in redacted
    assert "[REDACTED_PASSWORD]" in redacted
    assert "sk-ant-api03-" not in redacted
    assert "[REDACTED_ANTHROPIC_KEY]" in redacted
    assert "sk-proj-1234567890" not in redacted
    assert "[REDACTED_OPENAI_KEY]" in redacted
    assert "AIzaSyD123456" not in redacted
    assert "[REDACTED_GEMINI_KEY]" in redacted
    assert "123456789:ABC" not in redacted
    assert "[REDACTED_TELEGRAM_TOKEN]" in redacted
    assert "eyJhbGciOiJIUzI1" not in redacted


def test_i1_service_container():
    """I1: ServiceContainer registers and resolves singleton services and lazy factories."""
    container = ServiceContainer()
    container.register("settings", {"app_name": "TradeAgent"})
    container.register_factory("double_val", lambda c: 21 * 2)

    assert container.settings == {"app_name": "TradeAgent"}
    assert container.get("double_val") == 42
    assert container.has("settings") is True
    assert container.has("nonexistent") is False


def test_i6_tool_spillover():
    """I6: Oversized tool output spills to disk and returns preview reference."""
    with tempfile.TemporaryDirectory() as tmpdir:
        huge_output = "Line of price history: open=1.08 close=1.09\n" * 200  # > 5000 chars
        spilled_text = spill_tool_output(
            huge_output,
            tool_name="get_price_history",
            threshold_chars=500,
            spill_dir=tmpdir
        )

        assert len(spilled_text) < len(huge_output)
        assert "Full raw output spilled to disk" in spilled_text
        assert tmpdir in spilled_text

        # Verify file exists and content matches
        spill_files = os.listdir(tmpdir)
        assert len(spill_files) == 1
        with open(os.path.join(tmpdir, spill_files[0]), "r", encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == huge_output


@pytest.mark.asyncio
async def test_m1_plugin_manager_lifecycle_hooks():
    """M1: PluginManager emits lifecycle hooks including PRE_ORDER, POST_ORDER, ON_STARTUP."""
    mgr = PluginManager()
    events_received = []

    def on_startup():
        events_received.append("started")

    async def pre_order(**kwargs):
        events_received.append(f"pre_order:{kwargs.get('symbol')}")

    mgr.register_hook(PluginHook.ON_STARTUP, on_startup)
    mgr.register_hook(PluginHook.PRE_ORDER, pre_order)

    await mgr.emit(PluginHook.ON_STARTUP)
    await mgr.emit(PluginHook.PRE_ORDER, symbol="EURUSD")

    assert events_received == ["started", "pre_order:EURUSD"]


def test_m2_credential_pool_rotation_and_cooldown():
    """M2: CredentialPool rotates active keys and respects cooldown on rate limits."""
    pool = CredentialPool()
    pool.add_key("test_provider", "key_A")
    pool.add_key("test_provider", "key_B")

    # Initial get selects first key
    k1 = pool.get_key("test_provider")
    assert k1 in ("key_A", "key_B")

    # Next get selects the other key (LRU)
    k2 = pool.get_key("test_provider")
    assert k2 in ("key_A", "key_B")
    assert k1 != k2

    # Put k2 into cooldown for 60 seconds
    pool.report_rate_limit("test_provider", k2, cooldown_seconds=60.0)

    # Next call must only return k1 (since k2 is in cooldown)
    k3 = pool.get_key("test_provider")
    assert k3 == k1
