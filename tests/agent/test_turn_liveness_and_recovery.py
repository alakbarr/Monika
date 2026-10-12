# ==============================================================================
# File: tests/agent/test_turn_liveness_and_recovery.py
# Description: Unit tests for TurnLivenessWatchdog, EmptyResponseGuard ladder, and StreamingThinkScrubber
# ==============================================================================

import asyncio
import pytest
from unittest.mock import MagicMock

from agent.turn_liveness import TurnLivenessWatchdog
from agent.empty_response_guard import EmptyResponseGuard, EmptyRecoveryAction
from analysis.providers.streaming_think_scrubber import StreamingThinkScrubber
from telegram_bot.command_router import DIRECT_COMMANDS, CommandType


@pytest.mark.asyncio
async def test_turn_liveness_watchdog_generation_and_stall():
    stalls = []
    def on_hang(msg):
        stalls.append(msg)

    watchdog = TurnLivenessWatchdog(
        turn_id="test_turn_1",
        timeout_seconds=5.0,
        stall_timeout_seconds=0.2,
        check_interval_seconds=0.05,
        on_hang_detected=on_hang,
    )

    async with watchdog:
        assert watchdog.generation == 0
        watchdog.record_activity("step_1", chunk_len=5)
        assert watchdog.generation == 5

        # Advance generation continuously
        for i in range(3):
            await asyncio.sleep(0.06)
            watchdog.advance_generation(2)
        assert watchdog.generation == 11
        assert len(stalls) == 0

        # Now simulate a stream stall
        await asyncio.sleep(0.35)
        assert len(stalls) > 0
        assert "generation stalled" in stalls[0]


def test_empty_response_guard_7_step_ladder():
    guard = EmptyResponseGuard()

    # Step 2 check: Dangling think tag
    act_tag = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=1, raw_response="<think>Evaluating trade setup...")
    assert act_tag.step == 2
    assert act_tag.action_type == "close_reasoning"

    # Step 1: First attempt empty
    act1 = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=1)
    assert act1.step == 1
    assert act1.action_type == "nudge"

    # Step 3: Second attempt -> adjust temperature
    act2 = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=2)
    assert act2.step == 3
    assert act2.action_type == "adjust_temp"
    assert act2.temperature_override == 0.2

    # Step 4: Third attempt -> prune tools
    act3 = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=3)
    assert act3.step == 4
    assert act3.action_type == "prune_tools"
    assert act3.prune_tools is True

    # Step 5: Fourth attempt -> clean retry
    act4 = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=4)
    assert act4.step == 5
    assert act4.action_type == "retry"

    # Step 6: Fifth attempt -> failover
    act5 = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=5)
    assert act5.step == 6
    assert act5.action_type == "failover"

    # Step 7: Terminal attempt -> terminal
    act6 = guard.get_recovery_ladder_action("nous", "deepseek-r1", attempt=6)
    assert act6.step == 7
    assert act6.action_type == "terminal"


def test_streaming_think_scrubber_multi_tags():
    scrubber = StreamingThinkScrubber()

    # Test feed across chunks with <thought>...</thought>
    c1, t1 = scrubber.feed_chunk("Price analysis: <thou")
    assert c1 == "Price analysis: "
    assert t1 == ""

    c2, t2 = scrubber.feed_chunk("ght>Calculating EMA-200</thought> Bullish structure.")
    assert "Calculating EMA-200" in t2
    assert "Bullish structure." in c2

    # Test one-shot scrub_text with <reasoning>
    content, thinking = StreamingThinkScrubber.scrub_text("<reasoning>Checking drawdown limits</reasoning>Action: BUY EURUSD")
    assert content == "Action: BUY EURUSD"
    assert thinking == "Checking drawdown limits"


def test_telegram_command_router_model_registered():
    assert "model" in DIRECT_COMMANDS
    assert DIRECT_COMMANDS["model"]["type"] == CommandType.ADMIN
