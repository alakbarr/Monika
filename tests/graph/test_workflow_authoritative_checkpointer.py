from unittest.mock import MagicMock, patch
import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from graph.workflow import build_trading_graph
from graph.checkpointers.dual_checkpointer import DualCheckpointSaver


def test_build_trading_graph_memory_saver_when_no_db():
    """Verify that build_trading_graph without db_url uses MemorySaver without SQLite overhead."""
    graph = build_trading_graph(db_url=None)
    # The compiled graph checkpointer should not be DualCheckpointSaver
    assert not isinstance(getattr(graph, "checkpointer", None), DualCheckpointSaver)


def test_build_trading_graph_authoritative_postgres():
    """Verify that build_trading_graph with postgres url attaches direct postgres checkpointer."""
    with patch("psycopg_pool.AsyncConnectionPool") as mock_pool, \
         patch("langgraph.checkpoint.postgres.aio.AsyncPostgresSaver") as mock_saver:
        mock_pg_instance = MagicMock(spec=BaseCheckpointSaver)
        mock_saver.return_value = mock_pg_instance

        graph = build_trading_graph(db_url="postgresql+asyncpg://user:pass@localhost:5432/trading")
        # Should be direct postgres checkpointer, not DualCheckpointSaver
        assert not isinstance(getattr(graph, "checkpointer", None), DualCheckpointSaver)
        assert getattr(graph, "checkpointer", None) is mock_pg_instance
        assert getattr(mock_pg_instance, "_needs_setup", False) is True


def test_dual_checkpointer_conn_proxy():
    """Verify DualCheckpointSaver proxies conn from primary checkpointer."""
    primary_mock = MagicMock()
    primary_mock.conn = "mock_pool_conn"
    secondary_mock = MagicMock()
    saver = DualCheckpointSaver(primary=primary_mock, secondary=secondary_mock)

    assert saver.conn == "mock_pool_conn"
