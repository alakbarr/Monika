"""
Unit tests for FallbackClientWrapper slot cooldowns, exponential backoff, and fast failover.
"""

import time
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.providers.llm_factory import FallbackClientWrapper


@pytest.mark.asyncio
async def test_slot_cooldown_and_skipping():
    mock_factory = MagicMock()
    mock_client_primary = MagicMock()
    mock_client_primary.generate = AsyncMock(side_effect=Exception("Model not found: gpt-mock 404"))

    mock_client_fallback = MagicMock()
    mock_client_fallback.generate = AsyncMock(return_value="Success from fallback_1")

    def create_client(model, role_config, slot_name=None):
        if slot_name == "primary":
            return mock_client_primary
        return mock_client_fallback

    mock_factory._create_client_instance = create_client
    mock_factory._resolve_provider = MagicMock(return_value="gemini")
    mock_factory._resolve_thinking_level = MagicMock(return_value="none")
    mock_factory._settings = {}

    wrapper = FallbackClientWrapper(
        factory=mock_factory,
        primary="model-primary",
        fallbacks=["model-fallback"],
        role_config={"max_tokens": 1000},
        task_role="stage2_per_asset_primary"
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        # First execution: primary fails, fallback succeeds
        res = await wrapper._execute_with_fallback("generate", "test prompt")
        assert res == "Success from fallback_1"
        assert "primary" in wrapper._slot_cooldowns
        assert wrapper._slot_cooldowns["primary"] > time.time()
        assert wrapper._slot_backoff_count["primary"] == 1

        # Second execution: primary is skipped immediately (0 delay), directly calls fallback
        mock_client_primary.generate.reset_mock()
        res2 = await wrapper._execute_with_fallback("generate", "test prompt 2")
        assert res2 == "Success from fallback_1"
        # Primary should NOT have been called because it is in active cooldown
        mock_client_primary.generate.assert_not_called()
