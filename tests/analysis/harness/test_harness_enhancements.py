"""
Comprehensive Unit Tests for Agent Harness Quality & Efficiency Enhancements.
Tests:
1. Tool Argument Canonicalization & Recursive Anti-Oscillation Signatures (Pillar 2)
2. Fail-Closed Truncation Interception across heterogeneous provider schemas (Pillar 1 & 2)
3. Generalized Verification & Empirical Evidence Ledger (Pillar 3)
4. Physical Deliverable Probing & Anti-Hallucination Gate (Pillar 4)
5. Zero-Cost Lossless Structural Tool Pruner (Pillar 6)
6. Multibyte Instruction Budgeting & Hierarchical Pruning (Pillar 5)
7. End-to-End Agent Harness Integration
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from monika.application.agent.harness.agent_harness import AgentHarness
from monika.application.agent.harness.general_tool_pruner import GeneralToolPruner
from monika.application.agent.harness.physical_deliverable_gate import (
    DeliverableVerdict,
    PhysicalDeliverableGate,
)
from monika.application.agent.harness.tool_repair import (
    canonicalize_tool_arguments,
    compute_canonical_tool_signature,
)
from monika.application.agent.harness.verification_evidence_ledger import (
    GeneralizedEvidenceRecord,
    VerificationEvidenceLedger,
)
from monika.infrastructure.llm.instruction_budgeter import (
    BudgetedInstructionFile,
    InstructionBudgeter,
)


# ==============================================================================
# Pillar 2: Canonicalization & Anti-Oscillation Tool Signatures
# ==============================================================================
class TestToolArgumentCanonicalization:
    def test_nested_dict_key_sorting(self):
        input_data = {
            "zebra": 1,
            "apple": {"z": 100, "a": 200, "m": {"nested_b": 2, "nested_a": 1}},
            "banana": [3, 2, 1],
        }
        canonical = canonicalize_tool_arguments(input_data)
        # Top-level keys must be sorted
        assert list(canonical.keys()) == ["apple", "banana", "zebra"]
        # Nested dict keys must be sorted
        assert list(canonical["apple"].keys()) == ["a", "m", "z"]
        assert list(canonical["apple"]["m"].keys()) == ["nested_a", "nested_b"]
        # List items preserve order
        assert canonical["banana"] == [3, 2, 1]

    def test_list_of_dicts_canonicalization(self):
        input_data = [
            {"k2": "v2", "k1": "v1"},
            {"b": 2, "a": 1},
        ]
        canonical = canonicalize_tool_arguments(input_data)
        assert list(canonical[0].keys()) == ["k1", "k2"]
        assert list(canonical[1].keys()) == ["a", "b"]

    def test_primitive_passthrough(self):
        assert canonicalize_tool_arguments(123) == 123
        assert canonicalize_tool_arguments("test") == "test"
        assert canonicalize_tool_arguments(None) is None
        assert canonicalize_tool_arguments(True) is True

    def test_compute_canonical_tool_signature_invariance(self):
        tool_name = "place_order"
        args_1 = {"symbol": "EURUSD", "volume": 0.5, "extra": {"sl": 1.05, "tp": 1.10}}
        args_2 = {"extra": {"tp": 1.10, "sl": 1.05}, "volume": 0.5, "symbol": "EURUSD"}

        sig_1 = compute_canonical_tool_signature(tool_name, args_1)
        sig_2 = compute_canonical_tool_signature(tool_name, args_2)

        # Different dictionary key ordering must produce an identical signature
        assert sig_1 == sig_2
        assert sig_1.startswith(f"{tool_name}:")
        assert len(sig_1) == len(tool_name) + 1 + 32  # Valid MD5 hex digest with tool prefix

        # Different value produces different signature
        args_3 = {"symbol": "EURUSD", "volume": 0.6, "extra": {"sl": 1.05, "tp": 1.10}}
        assert compute_canonical_tool_signature(tool_name, args_3) != sig_1


# ==============================================================================
# Pillar 1 & 2: Fail-Closed Truncation Interception
# ==============================================================================
class TestTruncationInterception:
    def test_fail_truncated_tool_calls_openai_format(self):
        harness = AgentHarness(llm_client=MagicMock())
        blocks = [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "propose_trade",
                    "arguments": '{"symbol": "EURUSD", "volume": 1.0, "sl":',  # truncated json
                },
            }
        ]

        results = harness._fail_truncated_tool_calls(blocks)
        assert len(results) == 1
        call = results[0]
        assert call["type"] == "tool_result"
        assert call["name"] == "propose_trade"
        assert call["is_error"] is True
        content = json.loads(call["content"])
        assert content["status"] == "refused_truncated_response"
        assert "[SYSTEM ERROR]" in content["error"]

    def test_fail_truncated_tool_calls_anthropic_format(self):
        harness = AgentHarness(llm_client=MagicMock())
        blocks = [
            {
                "type": "tool_use",
                "id": "toolu_456",
                "name": "calculate_risk",
                "input": {"symbol": "GBPUSD"},
            }
        ]

        results = harness._fail_truncated_tool_calls(blocks)
        assert len(results) == 1
        call = results[0]
        assert call["name"] == "calculate_risk"
        assert call["is_error"] is True
        content = json.loads(call["content"])
        assert content["status"] == "refused_truncated_response"

    def test_fail_truncated_empty_blocks(self):
        harness = AgentHarness(llm_client=MagicMock())
        results = harness._fail_truncated_tool_calls([])
        assert results == []


# ==============================================================================
# Pillar 3: Generalized Verification & Evidence Ledger
# ==============================================================================
class TestGeneralizedVerificationLedger:
    def test_record_and_query_general_evidence(self):
        ledger = VerificationEvidenceLedger()
        assert not ledger.has_general_evidence(category="command", target="pytest")

        ledger.record_general_evidence(
            category="command",
            target="pytest",
            status="passed",
            details={"stdout": "3 passed in 0.12s", "exit_code": 0},
        )

        assert ledger.has_general_evidence(category="command", target="pytest")
        assert ledger.has_general_evidence(target="pytest")
        assert not ledger.has_general_evidence(target="flake8")

        records = ledger.get_general_records()
        assert len(records) == 1
        rec = records[0]
        assert isinstance(rec, GeneralizedEvidenceRecord)
        assert rec.status == "passed"
        assert rec.category == "command"
        assert rec.target == "pytest"

    def test_general_evidence_failure_record(self):
        ledger = VerificationEvidenceLedger()
        ledger.record_general_evidence(
            category="command",
            target="mypy",
            status="failed",
            details={"exit_code": 1, "stderr": "Found 2 errors"},
        )

        assert not ledger.has_general_evidence(target="mypy", required_status="passed")
        assert ledger.has_general_evidence(target="mypy", required_status="failed")
        records = ledger.get_general_records()
        assert len(records) == 1
        assert records[0].status == "failed"

    def test_reset_turn_clears_records(self):
        ledger = VerificationEvidenceLedger()
        ledger.record_general_evidence("tool", "cmd_a", "passed", {})
        assert ledger.has_general_evidence(target="cmd_a")

        ledger.reset_turn()
        assert not ledger.has_general_evidence(target="cmd_a")


# ==============================================================================
# Pillar 4: Physical Deliverables Gate (Ground-Truth File Probing)
# ==============================================================================
class TestPhysicalDeliverableGate:
    def test_verify_file_deliverable(self, tmp_path: Path):
        gate = PhysicalDeliverableGate(workspace_root=str(tmp_path))

        # 1. Non-existent file
        v_missing = gate.verify_file_deliverable("missing.py")
        assert not v_missing.is_valid
        assert v_missing.status == "missing_deliverable"

        # 2. Empty file (0 bytes)
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("", encoding="utf-8")
        v_empty = gate.verify_file_deliverable("empty.py")
        assert not v_empty.is_valid
        assert v_empty.status == "empty_file"

        # 3. Valid file with content
        valid_file = tmp_path / "valid.py"
        valid_file.write_text("print('hello')", encoding="utf-8")
        v_valid = gate.verify_file_deliverable("valid.py")
        assert v_valid.is_valid
        assert v_valid.status == "verified"
        assert len(v_valid.verified_paths) == 1

    def test_audit_claimed_completion(self, tmp_path: Path):
        gate = PhysicalDeliverableGate(workspace_root=str(tmp_path))

        # Narrative claims creation of non-existent file
        response_text = "Task completed! I have created `script.py` and saved it."
        verdict = gate.audit_claimed_completion(response_text)
        assert not verdict.is_valid
        assert "[PHYSICAL DELIVERABLE GATE]" in (verdict.message or "")

        # Now actually write the file
        (tmp_path / "script.py").write_text("import os", encoding="utf-8")
        verdict_ok = gate.audit_claimed_completion(response_text)
        assert verdict_ok.is_valid

    def test_audit_claimed_completion_no_deliverables(self):
        gate = PhysicalDeliverableGate()
        verdict = gate.audit_claimed_completion("Analysis complete: market is in an uptrend.")
        assert verdict.is_valid
        assert verdict.status == "verified"


# ==============================================================================
# Pillar 6: General Tool Pruner (Lossless Structural Tool Output Pruning)
# ==============================================================================
class TestGeneralToolPruner:
    def test_prune_text_within_limits(self):
        text = "Hello world\nLine 2"
        pruned = GeneralToolPruner.prune_text(text, max_chars=100)
        assert pruned == text

    def test_prune_text_exceeding_limits(self):
        text = "START_HEAD" + ("x" * 500) + "END_TAIL"
        pruned = GeneralToolPruner.prune_text(text, max_chars=50, tool_name="terminal")

        assert "START_HEAD" in pruned
        assert "END_TAIL" in pruned
        assert "GeneralToolPruner from tool 'terminal'" in pruned
        assert "characters" in pruned

    def test_prune_json_list(self):
        items = [{"id": i, "val": f"item_{i}"} for i in range(50)]
        pruned_str = GeneralToolPruner.prune_json(items, max_chars=300, tool_name="list_items")

        parsed = json.loads(pruned_str)
        assert parsed["_pruned_status"] == "truncated_list"
        assert parsed["total_items"] == 50
        assert len(parsed["head_items"]) in (2, 4)
        assert len(parsed["tail_items"]) in (1, 3)

    def test_prune_json_dict(self):
        data = {f"key_{i}": f"val_{i}" * 10 for i in range(30)}
        pruned_str = GeneralToolPruner.prune_json(data, max_chars=400, tool_name="get_stats")

        parsed = json.loads(pruned_str)
        assert "_pruned_notice" in parsed
        assert "key_0" in parsed

    def test_safe_unicode_slice(self):
        emoji_text = "🚀" * 20
        sliced = GeneralToolPruner.safe_unicode_slice(emoji_text, 0, 5)
        assert len(sliced) == 5
        assert sliced == "🚀" * 5


# ==============================================================================
# Pillar 5: Multibyte Instruction Budgeter
# ==============================================================================
class TestInstructionBudgeter:
    def test_truncate_to_byte_budget_utf8_ascii(self):
        text = "abcdefghij" * 10  # 100 bytes
        truncated, was_trunc = InstructionBudgeter.truncate_to_byte_budget_utf8(text, max_bytes=50)
        assert was_trunc is True
        assert len(truncated.encode("utf-8")) <= 150  # includes notice
        assert "abcdefghij" in truncated

    def test_truncate_to_byte_budget_utf8_multibyte(self):
        # 4-byte characters: 🌍 (earth globe)
        text = "🌍" * 50  # 200 bytes
        truncated, was_trunc = InstructionBudgeter.truncate_to_byte_budget_utf8(text, max_bytes=25)
        assert was_trunc is True
        raw_bytes = truncated.encode("utf-8")
        # Must be valid unicode decode with exact character boundaries
        assert raw_bytes.decode("utf-8") == truncated

    def test_hierarchical_instruction_budgeting(self):
        files = [
            {"path": "ancestor.md", "content": "BROAD ANCESTOR POLICY " * 100},
            {"path": "subfolder.md", "content": "INTERMEDIATE GUIDELINE " * 50},
            {"path": "task.md", "content": "TASK SPECIFIC DIRECTIVE"},
        ]
        # Set max_bytes to only comfortably fit the task-specific file and part of intermediate
        budget = len("TASK SPECIFIC DIRECTIVE".encode("utf-8")) + 200
        budgeted = InstructionBudgeter.budget_instruction_files(files, max_bytes=budget)

        assert len(budgeted) == 3
        # In reverse allocation: task.md (most specific) is preserved completely
        task_file = next(f for f in budgeted if f.path == "task.md")
        assert not task_file.is_omitted
        assert task_file.content == "TASK SPECIFIC DIRECTIVE"

        # Broadest ancestor should be omitted or heavily truncated
        ancestor_file = next(f for f in budgeted if f.path == "ancestor.md")
        assert ancestor_file.is_omitted is True or ancestor_file.is_truncated is True


# ==============================================================================
# Pillar 7: Agent Harness Integration Tests
# ==============================================================================
class TestAgentHarnessIntegration:
    def test_harness_initializes_new_components(self):
        harness = AgentHarness(llm_client=MagicMock())
        assert hasattr(harness, "physical_deliverable_gate")
        assert isinstance(harness.physical_deliverable_gate, PhysicalDeliverableGate)
        assert hasattr(harness, "general_tool_pruner")
        assert isinstance(harness.general_tool_pruner, GeneralToolPruner)
        assert hasattr(harness, "verification_ledger")
        assert isinstance(harness.verification_ledger, VerificationEvidenceLedger)
