# ==============================================================================
# File: tests/gateway/test_omnichannel_stream.py
# ==============================================================================

"""
Unit Test Suite for Stage 9:
Omni-Channel Gateway, LiveStreamConsumer, Code Fence Balancing,
and ChannelRouter Session Persistence.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
import pytest

from gateway.stream_consumer import ensure_closed_code_fences, LiveStreamConsumer
from gateway.channel_router import ChannelRouter
from gateway.platform_base import BasePlatformAdapter
from database.session_db_wal import SessionDbWal


# ==============================================================================
# 1. Code Fence Balancing Tests
# ==============================================================================

def test_ensure_closed_code_fences_clean():
    # Normal text without fences
    t1 = "EURUSD is breaking out above resistance."
    assert ensure_closed_code_fences(t1) == t1

    # Completely closed code block
    t2 = "Here is the code:\n```python\nprint('hello')\n```\nAll done."
    assert ensure_closed_code_fences(t2) == t2


def test_ensure_closed_code_fences_unclosed():
    # Unclosed python code block
    t1 = "Generating signal:\n```python\ndef buy():\n    return True"
    balanced = ensure_closed_code_fences(t1)
    assert balanced.endswith("\n```")
    # Total fences should now be even
    assert balanced.count("```") == 2


# ==============================================================================
# 2. LiveStreamConsumer Throttling Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_live_stream_consumer_accumulate_and_finish():
    flushed_updates = []

    async def _on_publish(text: str, is_final: bool):
        flushed_updates.append((text, is_final))

    consumer = LiveStreamConsumer(
        flush_interval_seconds=0.05,
        publisher_callback=_on_publish,
    )

    await consumer.feed_token("Calculating ")
    await consumer.feed_token("Kelly: ")
    await asyncio.sleep(0.06)

    await consumer.feed_token("f* = 0.12")
    final_text = await consumer.finish()

    assert "Calculating Kelly: f* = 0.12" in final_text
    assert len(flushed_updates) >= 1
    # Last update must be final
    assert flushed_updates[-1][1] is True


# ==============================================================================
# 3. ChannelRouter Integration Tests
# ==============================================================================

class MockPlatformAdapter(BasePlatformAdapter):
    def __init__(self, platform_name: str = "telegram"):
        super().__init__(platform_name)
        self.sent_messages = []

    async def start(self) -> None:
        self.is_connected = True

    async def stop(self) -> None:
        self.is_connected = False

    async def send_message(self, target_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        self.sent_messages.append((target_id, content, metadata))
        return True


@pytest.mark.asyncio
async def test_channel_router_dispatch_and_wal_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_gateway.sqlite"
        wal_db = SessionDbWal(db_path)

        router = ChannelRouter(wal_db)
        adapter = MockPlatformAdapter("telegram")
        await adapter.start()
        router.register_adapter(adapter)

        # Set custom agent pipeline echo logic
        async def _mock_pipeline(session_id: str, text: str, meta: Dict[str, Any]) -> str:
            return f"Processed: {text.upper()}"

        router.set_pipeline(_mock_pipeline)

        # Dispatch incoming message
        reply = await router.handle_incoming_message(
            sender_id="user_99",
            channel_id="chan_88",
            text="what is the current spread?",
            metadata={"platform": "telegram", "turn_ordinal": 1},
        )

        assert reply == "Processed: WHAT IS THE CURRENT SPREAD?"
        assert len(adapter.sent_messages) == 1
        assert adapter.sent_messages[0][0] == "chan_88"

        # Verify messages stored in SessionDbWal
        session_id = router.resolve_session_id("telegram", "chan_88")
        messages = wal_db.get_messages(session_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "what is the current spread?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Processed: WHAT IS THE CURRENT SPREAD?"

        wal_db.close()
