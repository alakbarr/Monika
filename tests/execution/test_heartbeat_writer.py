import pytest
import asyncio
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from execution.ea_bridge.heartbeat_writer import HeartbeatManager, HEARTBEAT_INTERVAL_SECONDS, EA_STALE_THRESHOLD_SECONDS

class TestHeartbeatManager:
    @pytest.fixture
    def mock_path(self, tmp_path):
        return str(tmp_path)
        
    def test_init(self, mock_path):
        manager = HeartbeatManager(mock_path)
        assert manager.common_path == Path(mock_path)
        assert manager.heartbeat_file == Path(mock_path) / "ai_agent_heartbeat.txt"
        assert manager.legacy_heartbeat_file == Path(mock_path) / "claude_agent_heartbeat.txt"
        assert manager.ea_heartbeat_file == Path(mock_path) / "ea_heartbeat.txt"
        assert not manager._running

    def test_write_heartbeat(self, mock_path):
        manager = HeartbeatManager(mock_path)
        with patch("time.time", return_value=1234567890.0):
            manager._write_heartbeat()
        
        assert manager.heartbeat_file.exists()
        assert manager.heartbeat_file.read_text(encoding="utf-8") == "1234567890"
        
    def test_write_heartbeat_error(self, mock_path):
        manager = HeartbeatManager(mock_path)
        with patch.object(Path, "mkdir", side_effect=Exception("Failed to make dir")):
            manager._write_heartbeat()
        assert not manager.heartbeat_file.exists()

    def test_check_ea_alive_no_file(self, mock_path):
        manager = HeartbeatManager(mock_path)
        is_alive, stale = manager.check_ea_alive()
        assert not is_alive
        assert stale == -1

    def test_check_ea_alive_valid(self, mock_path):
        manager = HeartbeatManager(mock_path)
        current_time = int(time.time())
        manager.ea_heartbeat_file.write_text(str(current_time - 10), encoding="utf-16-le")
        
        is_alive, stale = manager.check_ea_alive()
        assert is_alive
        assert 0 <= stale <= 11

    def test_check_ea_alive_stale(self, mock_path):
        manager = HeartbeatManager(mock_path)
        current_time = int(time.time())
        manager.ea_heartbeat_file.write_text(str(current_time - EA_STALE_THRESHOLD_SECONDS - 10), encoding="utf-16-le")
        
        is_alive, stale = manager.check_ea_alive()
        assert not is_alive
        assert stale >= EA_STALE_THRESHOLD_SECONDS + 10

    def test_check_ea_alive_error(self, mock_path):
        manager = HeartbeatManager(mock_path)
        manager.ea_heartbeat_file.write_text("invalid_int")
        
        is_alive, stale = manager.check_ea_alive()
        assert not is_alive
        assert stale == -1

    @pytest.mark.asyncio
    async def test_run_forever_and_stop(self, mock_path):
        manager = HeartbeatManager(mock_path)
        
        # Override write heartbeat to track calls
        manager._write_heartbeat = MagicMock()
        
        # Run in background
        task = asyncio.create_task(manager.run_forever())
        
        # Yield to let it start
        await asyncio.sleep(0.01)
        
        assert manager._running
        manager._write_heartbeat.assert_called_once()
        
        # Stop the manager
        manager.stop()
        
        # Wait for task to finish (sleep time will be patched out)
        # But wait, run_forever sleeps for HEARTBEAT_INTERVAL_SECONDS. 
        # We need to cancel the sleep or wait for it.
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
            
        assert not manager._running
