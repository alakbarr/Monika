"""
Tests for Economic Prompt Cache Warmer Integration (Commit 10).

Verifies:
1. Pydantic schema validation for CacheWarmingConfig in schemas.py and LLMConfig.
2. CacheWarmer respects settings (enabled, min_savings_threshold_usd).
3. If enabled is False, schedule_warm immediately returns False and spawns 0 tasks.
4. If expected_savings < min_savings_threshold_usd, warming is skipped (returns False, spawns 0 tasks).
5. If economical and enabled, warming task is scheduled and executed.
6. cancel_all() cleanly cancels and removes all pending warming tasks.
7. is_replayable supports Minimax, GLM, Gemini, DeepSeek, and Anthropic.
8. CycleScheduler wiring:
   - Initialized with CacheWarmer.
   - schedule_cache_warm delegates to cache_warmer.
   - Kill-switch blocks warming.
   - Scheduler stop() triggers cache_warmer.cancel_all().
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.application.scheduler.cycle_scheduler import CycleScheduler
from monika.core.config.schemas import CacheWarmingConfig, LLMConfig
from monika.infrastructure.llm.cache_warmer import CacheWarmer, is_replayable


def test_cache_warming_config_schema():
    """Verify CacheWarmingConfig default values, constraints, and LLMConfig integration."""
    cfg = CacheWarmingConfig()
    assert cfg.enabled is True
    assert cfg.min_savings_threshold_usd == 0.05
    assert cfg["enabled"] is True
    assert cfg.get("min_savings_threshold_usd") == 0.05

    cfg_custom = CacheWarmingConfig(enabled=False, min_savings_threshold_usd=0.10)
    assert cfg_custom.enabled is False
    assert cfg_custom.min_savings_threshold_usd == 0.10
    assert cfg_custom["enabled"] is False

    llm_cfg = LLMConfig()
    assert llm_cfg.cache_warming is not None
    assert llm_cfg.cache_warming.enabled is True
    assert llm_cfg.cache_warming.min_savings_threshold_usd == 0.05


def test_cache_warmer_disabled_skips_and_spawns_zero_tasks():
    """When enabled: false, schedule_warm returns False and spawns zero background tasks."""
    settings = {
        "llm": {
            "cache_warming": {
                "enabled": False,
                "min_savings_threshold_usd": 0.05,
            }
        }
    }
    warmer = CacheWarmer(settings=settings)
    called = False

    async def dummy_coro():
        nonlocal called
        called = True

    result = warmer.schedule_warm(
        session_id="test_session_disabled",
        prompt_tokens=25000,
        warm_cost=0.01,
        miss_cost=0.50,  # $0.49 expected savings, but disabled
        warm_coro_fn=dummy_coro,
    )

    assert result is False
    assert len(warmer._active_tasks) == 0
    assert called is False


def test_cache_warmer_uneconomical_skips():
    """When expected_savings < min_savings_threshold_usd, warming is rejected."""
    settings = {
        "llm": {
            "cache_warming": {
                "enabled": True,
                "min_savings_threshold_usd": 0.05,
            }
        }
    }
    warmer = CacheWarmer(settings=settings)
    called = False

    async def dummy_coro():
        nonlocal called
        called = True

    # Expected savings = 1.0 * 0.03 - 0.01 = 0.02 < 0.05
    result = warmer.schedule_warm(
        session_id="test_session_uneconomical",
        prompt_tokens=25000,
        warm_cost=0.01,
        miss_cost=0.03,
        warm_coro_fn=dummy_coro,
        phase="active",
    )

    assert result is False
    assert len(warmer._active_tasks) == 0
    assert called is False


@pytest.mark.asyncio
async def test_cache_warmer_economical_schedules_and_executes():
    """When economical and enabled, background warming task executes successfully."""
    settings = {
        "llm": {
            "cache_warming": {
                "enabled": True,
                "min_savings_threshold_usd": 0.05,
            }
        }
    }
    warmer = CacheWarmer(settings=settings)
    warmed_event = asyncio.Event()

    async def dummy_coro():
        warmed_event.set()

    # With ttl_ms=20.0, delay = max(1.0, min(18.0, 10.0)) = 10.0 ms = 0.01s
    result = warmer.schedule_warm(
        session_id="test_session_active",
        prompt_tokens=25000,
        warm_cost=0.01,
        miss_cost=0.20,  # Savings = 0.19 >= 0.05
        warm_coro_fn=dummy_coro,
        phase="active",
        ttl_ms=20.0,
    )

    assert result is True
    assert "test_session_active" in warmer._active_tasks

    # Wait for completion
    await asyncio.wait_for(warmed_event.wait(), timeout=1.0)
    assert warmed_event.is_set()
    assert "test_session_active" in warmer._last_warmed_at


@pytest.mark.asyncio
async def test_cache_warmer_cancel_all():
    """cancel_all() properly cancels all active scheduled tasks."""
    settings = {"llm": {"cache_warming": {"enabled": True}}}
    warmer = CacheWarmer(settings=settings)

    async def dummy_coro():
        pass

    # Schedule multiple tasks with high TTL
    warmer.schedule_warm("s1", 20000, 0.01, 0.20, dummy_coro, ttl_ms=100_000.0)
    warmer.schedule_warm("s2", 20000, 0.01, 0.20, dummy_coro, ttl_ms=100_000.0)

    assert len(warmer._active_tasks) == 2

    warmer.cancel_all()
    assert len(warmer._active_tasks) == 0


def test_is_replayable_multiprovider_support():
    """Verify is_replayable correctly accepts Minimax, GLM, Gemini, DeepSeek, and Anthropic."""
    # Minimax
    assert is_replayable("openrouter:minimax-m3.1-flash") is True
    assert is_replayable("minimax-m3.1-flash") is True
    assert is_replayable("minimax/minimax-01") is True

    # GLM
    assert is_replayable("openrouter:glm-5.3-flash") is True
    assert is_replayable("glm-5.3-flash") is True
    assert is_replayable("zhipu/glm-4-plus") is True

    # Gemini
    assert is_replayable("gemini-3.5-flash-lite") is True
    assert is_replayable("openrouter:gemini-4-argon") is True

    # DeepSeek
    assert is_replayable("deepseek-v4.1-flash") is True
    assert is_replayable("deepseek-chat") is True

    # Anthropic / Claude
    assert is_replayable("claude-opus-5.5") is True
    assert is_replayable("anthropic/claude-3.5-sonnet") is True

    # Thinking models
    assert is_replayable("claude-3-7-sonnet", thinking_enabled=True, adaptive_thinking=True) is True
    assert is_replayable("claude-3-7-sonnet", thinking_enabled=True, adaptive_thinking=False) is True
    assert is_replayable("gemini-3.5-flash-lite", thinking_enabled=True, adaptive_thinking=False) is False

    # Stubs / Unknown
    assert is_replayable("dummy_local_model") is False
    assert is_replayable("mock_provider") is False
    assert is_replayable("unsupported_random_model_xyz") is False


@pytest.mark.asyncio
async def test_cycle_scheduler_wiring_and_killswitch():
    """Verify CycleScheduler wires CacheWarmer and blocks on kill switch."""
    settings = {
        "llm": {
            "cache_warming": {
                "enabled": True,
                "min_savings_threshold_usd": 0.05,
            }
        },
        "trading": {
            "kill_switch_active": False,
        },
    }
    sched = CycleScheduler(
        settings=settings,
        fundamental_stage=MagicMock(),
        per_asset_stage=MagicMock(),
    )
    assert hasattr(sched, "cache_warmer")
    assert isinstance(sched.cache_warmer, CacheWarmer)

    async def dummy_coro():
        pass

    # Normal schedule should succeed
    res = sched.schedule_cache_warm(
        session_id="sched_session",
        prompt_tokens=25000,
        warm_cost=0.01,
        miss_cost=0.20,
        warm_coro_fn=dummy_coro,
        ttl_ms=50_000.0,
    )
    assert res is True
    assert "sched_session" in sched.cache_warmer._active_tasks

    # Scheduler stop cancels tasks
    sched.stop()
    assert len(sched.cache_warmer._active_tasks) == 0

    # With kill switch active, schedule_cache_warm returns False
    settings["trading"]["kill_switch_active"] = True
    res_kill = sched.schedule_cache_warm(
        session_id="sched_kill",
        prompt_tokens=25000,
        warm_cost=0.01,
        miss_cost=0.20,
        warm_coro_fn=dummy_coro,
    )
    assert res_kill is False
