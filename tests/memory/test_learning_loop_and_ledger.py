# ==============================================================================
# File: tests/memory/test_phase3_learning_loop_and_ledger.py
# ==============================================================================

"""
Unit Test Suite for Phase 3:
Skill AST Security Audit, Cryptographic SHA-256 Chained Ledger, and
Background Review Fork with Counterfactual Analysis.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest

from analysis.memory.skill_ast_audit import SkillAstAuditor
from analysis.memory.skill_ledger_sha import ShaSkillLedger, ShaLedgerBlock
from analysis.memory.background_review_fork import BackgroundReviewFork


# ==============================================================================
# 1. Skill AST Audit Tests
# ==============================================================================

def test_ast_audit_valid_clean_code():
    clean_code = """
def calculate_bollinger_bands(prices, period=20, std_dev=2.0):
    import math
    if len(prices) < period:
        return None
    sma = sum(prices[-period:]) / period
    variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
    std = math.sqrt(variance)
    return {"upper": sma + std_dev * std, "lower": sma - std_dev * std, "sma": sma}
"""
    auditor = SkillAstAuditor()
    report = auditor.audit_code(clean_code)
    assert report.is_clean
    assert not report.has_critical_violations
    assert report.complexity_score > 1
    assert report.max_nesting_depth >= 1


def test_ast_audit_detects_dangerous_imports():
    malicious_code = """
import subprocess
import os

def exploit():
    subprocess.run(["cmd.exe", "/c", "dir"])
"""
    auditor = SkillAstAuditor()
    report = auditor.audit_code(malicious_code)
    assert not report.is_clean
    assert report.has_critical_violations
    rule_ids = {v.rule_id for v in report.violations}
    assert "SEC_001_DANGEROUS_IMPORT" in rule_ids


def test_ast_audit_detects_eval_and_exec():
    eval_code = """
def evaluate_expression(user_input):
    return eval(user_input)
"""
    auditor = SkillAstAuditor()
    report = auditor.audit_code(eval_code)
    assert not report.is_clean
    assert report.has_critical_violations
    rule_ids = {v.rule_id for v in report.violations}
    assert "SEC_002_DANGEROUS_CALL" in rule_ids


# ==============================================================================
# 2. SHA-256 Chained Ledger Tests
# ==============================================================================

def test_sha_ledger_chaining_and_tamper_detection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "test_ledger.jsonl"
        ledger = ShaSkillLedger(ledger_path)

        # 1. Commit multiple blocks
        b0 = ledger.append_mutation(
            skill_id="playbook_eurusd_trend",
            content_text="v1.0: Enter on 4H EMA pullback.",
            mutation_type="CREATE",
            author_role="quant_specialist",
        )
        assert b0.index == 0
        assert b0.prev_hash == "0" * 64

        b1 = ledger.append_mutation(
            skill_id="playbook_eurusd_trend",
            content_text="v1.1: Added 15m liquidity sweep requirement.",
            mutation_type="UPDATE",
            author_role="learning_loop",
        )
        assert b1.index == 1
        assert b1.prev_hash == b0.block_hash

        b2 = ledger.append_mutation(
            skill_id="playbook_xauusd_breakout",
            content_text="v1.0: New York open breakout filter.",
            mutation_type="CREATE",
            author_role="macro_judge",
        )
        assert b2.index == 2
        assert b2.prev_hash == b1.block_hash

        # 2. Verify clean integrity
        is_valid, err = ledger.verify_integrity()
        assert is_valid
        assert err is None

        # 3. Lookup by hash
        retrieved = ledger.get_version_by_hash(b1.block_hash[:12])
        assert retrieved is not None
        assert retrieved.content_text == b1.content_text

        # 4. Tamper with block 0 on disk
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        tampered_b0_dict = json_loads = [line for line in lines]
        # Mutate block 0 content without updating hash
        b0_obj = eval(lines[0].replace("true", "True").replace("false", "False"))
        b0_obj["content_text"] = "HACKED_CONTENT"
        import json
        lines[0] = json.dumps(b0_obj)
        ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Reload ledger and verify tamper detection
        reloaded_ledger = ShaSkillLedger(ledger_path)
        is_valid_after_hack, hack_err = reloaded_ledger.verify_integrity()
        assert not is_valid_after_hack
        assert "Content tampering detected" in hack_err


# ==============================================================================
# 3. Background Review Fork Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_background_review_fork_execution():
    fork = BackgroundReviewFork()
    await fork.start()
    try:
        # Enqueue winning trade
        trade1 = {
            "trade_id": "trade_win_101",
            "symbol": "EURUSD",
            "pnl": 450.0,
            "requested_price": 1.08500,
            "fill_price": 1.08502,
            "latency_ms": 12.0,
            "exit_reason": "tp_reached",
        }
        assert fork.enqueue_for_review(trade1)

        # Enqueue losing trade with high slippage
        trade2 = {
            "trade_id": "trade_loss_102",
            "symbol": "XAUUSD",
            "pnl": -320.0,
            "requested_price": 2650.00,
            "fill_price": 2650.50,  # 50 pips slippage
            "latency_ms": 48.0,
            "exit_reason": "sl_reached",
            "tags": ["news"],
        }
        assert fork.enqueue_for_review(trade2)

        # Wait for queue to drain
        await fork.queue.join()

        assert len(fork.completed_reviews) == 2
        rev_win = [r for r in fork.completed_reviews if r.trade_id == "trade_win_101"][0]
        rev_loss = [r for r in fork.completed_reviews if r.trade_id == "trade_loss_102"][0]

        assert rev_win.thesis_validated
        assert not rev_loss.thesis_validated
        assert rev_loss.slippage_pips >= 5.0
        assert len(rev_loss.negative_constraints) >= 1
        assert any("DO NOT enter market orders on XAUUSD" in c for c in rev_loss.negative_constraints)

    finally:
        await fork.stop()
