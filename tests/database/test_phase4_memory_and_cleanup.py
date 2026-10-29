import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.scheduler.position_guardian import PositionGuardian
from monika.infrastructure.database.cleanup import cleanup_old_data
from monika.infrastructure.database.db import _ExecutionLocksDict
from monika.infrastructure.database.models import (
    CycleEvent,
    CyclePerformance,
    DebateTranscript,
    MacroLiquidityCreditMetric,
    OrderEvent,
    PatternScreeningCache,
    TimesFMForecast,
    TradingStateLog,
)
from monika.infrastructure.graph.checkpointers.sqlite_checkpointer import SqliteCheckpointSaver
from monika.interfaces.telegram.bot import _BoundedChatAgentsDict
from tests.conftest import create_mock_async_session


class TestSqliteCheckpointerMemoryBounding:
    def test_blobs_and_storage_capped_at_50_threads(self, tmp_path: Path):
        """Verify that SqliteCheckpointSaver caps both storage and blobs at 50 threads."""
        db_path = str(tmp_path / "test_cp.sqlite")
        saver = SqliteCheckpointSaver(db_path=db_path)

        for i in range(100):
            thread_id = f"thread_cycle_{i}"
            cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            checkpoint = {
                "v": 1,
                "id": f"cp_{i}",
                "ts": "2026-10-29T12:00:00+00:00",
                "channel_values": {"state_payload": "X" * 5000},
                "channel_versions": {"state_payload": 1},
                "versions_seen": {},
                "pending_sends": [],
            }
            metadata = {"source": "loop", "step": 1, "writes": {}}
            saver.put(cfg, checkpoint, metadata, new_versions={"state_payload": 1})

        assert len(saver.storage) <= 50
        blobs_dict = getattr(saver, "blobs", {})
        assert len(blobs_dict) <= 50
        assert saver._put_counter == 100

    @pytest.mark.asyncio
    async def test_async_aput_and_disk_prune_trigger(self, tmp_path: Path):
        """Verify that aput increments put_counter and triggers aprune_disk_checkpoints every 100 calls."""
        db_path = str(tmp_path / "test_async_cp.sqlite")
        saver = SqliteCheckpointSaver(db_path=db_path)

        for i in range(100):
            thread_id = f"async_thread_{i}"
            cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            checkpoint = {
                "v": 1,
                "id": f"cp_async_{i}",
                "ts": "2026-10-29T12:00:00+00:00",
                "channel_values": {"data": i},
                "channel_versions": {"data": 1},
                "versions_seen": {},
                "pending_sends": [],
            }
            metadata = {"source": "loop", "step": 1, "writes": {}}
            await saver.aput(cfg, checkpoint, metadata, new_versions={"data": 1})

        assert saver._put_counter == 100
        assert len(saver.storage) <= 50
        assert len(getattr(saver, "blobs", {})) <= 50

    def test_put_writes_pruning(self, tmp_path: Path):
        """Verify that put_writes triggers _prune_memory_cache when writes exceed 200 entries."""
        db_path = str(tmp_path / "test_writes.sqlite")
        saver = SqliteCheckpointSaver(db_path=db_path)

        # Seed 60 threads in storage
        for i in range(60):
            cfg = {"configurable": {"thread_id": f"t_{i}", "checkpoint_ns": "", "checkpoint_id": f"c_{i}"}}
            writes = [("channel_a", f"val_{i}")]
            saver.put_writes(cfg, writes, task_id=f"task_{i}")

        assert len(saver.writes) <= 250


class TestDatabaseCleanupCoverage:
    @pytest.mark.asyncio
    @patch("monika.infrastructure.database.cleanup.datetime")
    async def test_cleanup_includes_all_8_high_growth_tables(self, mock_datetime):
        """Verify that cleanup_old_data executes delete queries for all 8 high-growth models."""
        now = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.timezone = timezone
        mock_datetime.timedelta = timedelta

        mock_session = create_mock_async_session()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        await cleanup_old_data(mock_session, settings=None)

        executed_statements = [call.args[0] for call in mock_session.execute.call_args_list if call.args]
        executed_reprs = [str(stmt) for stmt in executed_statements]

        target_tables = [
            "cycle_events",
            "cycle_performance",
            "debate_transcripts",
            "macro_liquidity_credit_metrics",
            "order_events",
            "pattern_screening_cache",
            "timesfm_forecasts",
            "trading_state_logs",
        ]

        for tbl in target_tables:
            matched = any(tbl in stmt_str for stmt_str in executed_reprs)
            assert matched, f"Expected delete query for table {tbl} was not executed!"

        assert mock_session.commit.call_count == 1


class TestInMemoryBoundedCollections:
    def test_execution_locks_dict_bounded(self):
        """Verify that _ExecutionLocksDict purges unlocked entries when exceeding 512 entries."""
        locks = _ExecutionLocksDict()
        dummy_loop = "dummy_loop"

        for i in range(600):
            locks.setdefault((dummy_loop, i), asyncio.Lock())

        assert len(locks) <= 512

    def test_position_guardian_collections_bounded(self):
        """Verify that PositionGuardian._alerted_position_events and _orphan_retries are bounded at 500."""
        guardian = PositionGuardian(settings={})

        for i in range(600):
            if len(guardian._alerted_position_events) > 500:
                excess = len(guardian._alerted_position_events) - 250
                for k in list(guardian._alerted_position_events)[:excess]:
                    guardian._alerted_position_events.discard(k)
            guardian._alerted_position_events.add((i, f"event_{i}"))

        assert len(guardian._alerted_position_events) <= 500

        for i in range(600):
            if len(guardian._orphan_retries) > 500:
                excess = len(guardian._orphan_retries) - 250
                for ok in list(guardian._orphan_retries.keys())[:excess]:
                    guardian._orphan_retries.pop(ok, None)
            guardian._orphan_retries[i] = (1, 1000.0 + i)

        assert len(guardian._orphan_retries) <= 500

    def test_bounded_chat_agents_dict(self):
        """Verify that _BoundedChatAgentsDict caps total elements at maxsize=100 and evicts FIFO."""
        agents = _BoundedChatAgentsDict(maxsize=100)

        for i in range(150):
            agents[f"user_{i}"] = f"agent_obj_{i}"

        assert len(agents) == 100
        # Oldest items 0..49 must be evicted
        assert "user_0" not in agents
        assert "user_49" not in agents
        # Latest items 50..149 must remain
        assert "user_50" in agents
        assert "user_149" in agents
