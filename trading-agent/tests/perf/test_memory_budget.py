"""
Memory Budget Performance Gate (Phase 5.4).
Verifies that agent turn loops and context maintenance operate strictly under 256MB cap.
"""

import tracemalloc
import pytest
from utils.llm.context_compaction import ContextCompactionEngine


def test_agent_context_memory_budget():
    """Agent loop context compaction across 25 turns must not exceed 256MB peak memory."""
    tracemalloc.start()
    try:
        engine = ContextCompactionEngine(settings={})
        messages = [
            {"role": "system", "content": "You are a quantitative trading assistant." * 50},
            {"role": "user", "content": "Analyze XAUUSD market regime and order blocks." * 20},
        ]

        # Simulate 25 turns of conversation growth with tool observations
        for i in range(25):
            messages.append({
                "role": "assistant",
                "content": f"Analyzing turn {i}..." + ("\nPrice action confirms liquidity sweep." * 30),
            })
            messages.append({
                "role": "user",
                "content": f"[Observation {i}]: " + ("Candle data row with OHLCV metrics " * 50),
            })
            # Run compaction pass
            messages = engine.check_and_compact(messages, context_window=64000)

        current, peak = tracemalloc.get_traced_memory()
        peak_mb = peak / (1024 * 1024)

        # 256 MB ceiling limit
        assert peak_mb < 256.0, f"Memory peak was {peak_mb:.2f} MB, exceeding 256 MB limit"
    finally:
        tracemalloc.stop()
