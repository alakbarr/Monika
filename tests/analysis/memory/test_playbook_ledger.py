import pytest
import os
import tempfile
from analysis.memory.playbook_ledger import PlaybookLedger


def test_playbook_ledger_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = PlaybookLedger(playbooks_dir=tmpdir)

        # 1. Record v1
        v1_content = "# EURUSD London Breakout\nRule: Wait for 15-pip sweep."
        hash1 = ledger.record_mutation("eurusd_breakout", v1_content, action="create", reason="Initial synthesis")
        assert len(hash1) == 64

        history = ledger.list_history("eurusd_breakout")
        assert len(history) == 1
        assert history[0]["action"] == "create"

        # 2. Record v2
        v2_content = "# EURUSD London Breakout\nRule: Wait for 20-pip sweep."
        hash2 = ledger.record_mutation("eurusd_breakout", v2_content, action="update", reason="Widened buffer")
        assert hash2 != hash1

        history = ledger.list_history("eurusd_breakout")
        assert len(history) == 2

        # 3. Rollback to v1
        ok = ledger.rollback("eurusd_breakout")
        assert ok

        # Verify restored content in file
        playbook_path = os.path.join(tmpdir, "eurusd_breakout.md")
        assert os.path.exists(playbook_path)
        with open(playbook_path, "r", encoding="utf-8") as f:
            restored = f.read()
        assert restored == v1_content

        # Verify rollback recorded in ledger
        history_after = ledger.list_history("eurusd_breakout")
        assert len(history_after) == 3
        assert history_after[-1]["action"] == "rollback"
