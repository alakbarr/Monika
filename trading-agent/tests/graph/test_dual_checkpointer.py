import pytest
from unittest.mock import MagicMock
from graph.checkpointers.dual_checkpointer import DualCheckpointSaver


def test_dual_checkpointer_dual_write():
    primary_mock = MagicMock()
    secondary_mock = MagicMock()
    saver = DualCheckpointSaver(primary=primary_mock, secondary=secondary_mock)

    config = {"configurable": {"thread_id": "t1", "checkpoint_ns": "ns1"}}
    checkpoint = {"id": "c1", "channel_values": {"x": 10}}
    metadata = {"step": 1}

    saver.put(config, checkpoint, metadata)

    # Assert both primary and secondary received the write
    primary_mock.put.assert_called_once_with(config, checkpoint, metadata, new_versions=None)
    secondary_mock.put.assert_called_once_with(config, checkpoint, metadata, new_versions=None)


def test_dual_checkpointer_failover_read():
    primary_mock = MagicMock()
    # Primary raises a network/connection exception
    primary_mock.get_tuple.side_effect = ConnectionError("PostgreSQL connection refused")

    secondary_mock = MagicMock()
    expected_tuple = MagicMock()
    secondary_mock.get_tuple.return_value = expected_tuple

    saver = DualCheckpointSaver(primary=primary_mock, secondary=secondary_mock)

    config = {"configurable": {"thread_id": "t1"}}
    result = saver.get_tuple(config)

    assert result == expected_tuple
    primary_mock.get_tuple.assert_called_once_with(config)
    secondary_mock.get_tuple.assert_called_once_with(config)


def test_dual_checkpointer_primary_success_skips_secondary_read():
    primary_mock = MagicMock()
    expected_tuple = MagicMock()
    primary_mock.get_tuple.return_value = expected_tuple

    secondary_mock = MagicMock()

    saver = DualCheckpointSaver(primary=primary_mock, secondary=secondary_mock)

    config = {"configurable": {"thread_id": "t1"}}
    result = saver.get_tuple(config)

    assert result == expected_tuple
    primary_mock.get_tuple.assert_called_once_with(config)
    secondary_mock.get_tuple.assert_not_called()
