# ==============================================================================
# File: tests/gateway/test_universal_ecosystem.py
# ==============================================================================

import json
import os
import tempfile
import pytest
from skills.skills_hub import SkillsHub
from scheduler.universal_cron_scheduler import UniversalCronScheduler, CronJob
from gateway.acp_server import AcpServer
from gateway.omnichannel_router import (
    OmnichannelRouter,
    MessageEvent,
    SessionSource,
    MessageType,
    build_session_key,
    ensure_closed_code_fences,
)


def test_skills_hub():
    with tempfile.TemporaryDirectory() as td:
        skill_dir = os.path.join(td, "test-skill")
        os.makedirs(skill_dir, exist_ok=True)
        skill_file = os.path.join(skill_dir, "SKILL.md")

        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "name: test-skill\n"
                "description: A test skill for validation.\n"
                "category: TESTING\n"
                "---\n"
                "# Test Skill\n"
                "Execute procedure accurately.\n"
            )

        hub = SkillsHub(search_directories=[td])
        skills = hub.list_skills()
        assert len(skills) >= 1
        assert skills[0]["name"] == "test-skill"

        ok, content = hub.view_skill("test-skill")
        assert ok is True
        assert "Execute procedure accurately" in content


def test_universal_cron_scheduler():
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "test_cron.db")
        scheduler = UniversalCronScheduler(db_path=db_path)

        # Test duration parser
        now = 100000.0
        assert scheduler.parse_schedule_expression("30m", from_timestamp=now) == now + 1800.0
        assert scheduler.parse_schedule_expression("2h", from_timestamp=now) == now + 7200.0
        assert scheduler.parse_schedule_expression("every 5m", from_timestamp=now) == now + 300.0

        # Register job
        job = scheduler.register_job(
            job_id="job_test_1",
            schedule_expression="10m",
            prompt="Analyze daily portfolio performance",
        )
        assert job.job_id == "job_test_1"
        assert job.is_active is True
        scheduler.close()


def test_omnichannel_session_key_and_code_fence():
    src_dm = SessionSource(platform="telegram", chat_id="12345", chat_type="dm", user_id="u99")
    key_dm = build_session_key(src_dm)
    assert "telegram:dm:chat_12345:user_u99" in key_dm

    src_thread = SessionSource(
        platform="discord", chat_id="c1", chat_type="channel", thread_id="t99", scope_id="guild1"
    )
    key_thread = build_session_key(src_thread)
    assert "discord:channel:scope_guild1:chat_c1:thread_t99" in key_thread

    # Test code fence closure
    unclosed = "Here is some code:\n```python\nx = 10"
    closed = ensure_closed_code_fences(unclosed)
    assert closed.endswith("\n```")

    already_closed = "Here is some code:\n```python\nx = 10\n```"
    assert ensure_closed_code_fences(already_closed) == already_closed


def test_acp_server_initialize():
    server = AcpServer()
    # Test JSON-RPC initialize response
    received_msgs = []

    def mock_write(s):
        received_msgs.append(s)

    orig_write = server.send_response
    server.send_response = lambda req_id, result=None, error=None: received_msgs.append((req_id, result))

    server.handle_message(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
    assert len(received_msgs) == 1
    req_id, result = received_msgs[0]
    assert req_id == 1
    assert result["protocol_version"] == "1.0.0"
    assert result["agent"]["name"] == "Monika"
