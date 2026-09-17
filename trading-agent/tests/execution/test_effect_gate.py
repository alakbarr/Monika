# ==============================================================================
# File: tests/execution/test_effect_gate.py
# ==============================================================================

import asyncio
import pytest
from execution.effect_gate import EffectGate, AbortRequested


@pytest.mark.asyncio
async def test_effect_gate_normal_admission():
    gate = EffectGate()
    executed = False

    async def sample_effect():
        nonlocal executed
        executed = True
        return "order_placed"

    result = await gate.admit(sample_effect, context_name="test_order")
    assert result == "order_placed"
    assert executed is True
    assert not gate.is_aborted


@pytest.mark.asyncio
async def test_effect_gate_blocks_when_aborted():
    gate = EffectGate()
    gate.request_abort("Kill switch activated")
    assert gate.is_aborted

    executed = False

    async def sample_effect():
        nonlocal executed
        executed = True
        return "should_not_run"

    with pytest.raises(AbortRequested) as exc_info:
        await gate.admit(sample_effect, context_name="test_order")

    assert "Kill switch activated" in str(exc_info.value)
    assert executed is False


@pytest.mark.asyncio
async def test_effect_gate_blocks_on_external_abort_signal():
    gate = EffectGate()
    external_signal = asyncio.Event()
    external_signal.set()

    executed = False

    async def sample_effect():
        nonlocal executed
        executed = True
        return "should_not_run"

    with pytest.raises(AbortRequested):
        await gate.admit(sample_effect, abort_signal=external_signal)

    assert executed is False
    assert gate.is_aborted


@pytest.mark.asyncio
async def test_effect_gate_reset():
    gate = EffectGate()
    gate.request_abort("Temporary pause")
    assert gate.is_aborted

    gate.reset()
    assert not gate.is_aborted

    executed = False

    async def sample_effect():
        nonlocal executed
        executed = True
        return "resumed"

    result = await gate.admit(sample_effect)
    assert result == "resumed"
    assert executed is True
