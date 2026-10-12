import os
import time
import pytest
import asyncio
from datetime import datetime
from execution.ea_bridge.heartbeat_writer import HeartbeatManager, HEARTBEAT_INTERVAL_SECONDS

class TestHeartbeatManager:
    def test_heartbeat_initialization(self, tmp_path):
        writer = HeartbeatManager(mt5_common_path=str(tmp_path))
        assert writer.common_path == tmp_path
        
    @pytest.mark.asyncio
    async def test_heartbeat_write_and_timeout(self, tmp_path):
        writer = HeartbeatManager(mt5_common_path=str(tmp_path))
        
        # Test write manually
        writer._write_heartbeat()
        
        hb_file = tmp_path / "claude_agent_heartbeat.txt"
        assert os.path.exists(hb_file)
        with open(hb_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            
        assert content.isdigit()
