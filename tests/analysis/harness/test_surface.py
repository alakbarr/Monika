"""
Tests for Monika Harness Surface specification and safety invariants.
"""

import pytest

from monika.domain.harness.models import ComponentType, HarnessViolationError
from monika.application.analysis.harness.surface import (
    MONIKA_SURFACE,
    classify_component,
    is_path_reserved,
    normalize_rel_path,
    validate_tree_invariants,
)


def test_normalize_rel_path():
    assert normalize_rel_path("systemprompt.md") == "systemprompt.md"
    assert normalize_rel_path("./guardrails.md") == "guardrails.md"
    assert normalize_rel_path("skills\\trading\\playbooks\\trend.md") == "skills/trading/playbooks/trend.md"

    with pytest.raises(HarnessViolationError, match="escapes"):
        normalize_rel_path("../outside.md")

    with pytest.raises(HarnessViolationError, match="escapes"):
        normalize_rel_path("/absolute/path.md")

    with pytest.raises(HarnessViolationError, match="escapes"):
        normalize_rel_path("skills/../../etc/passwd")


def test_classify_all_8_components():
    assert classify_component("systemprompt.md") == ComponentType.SYSTEM_PROMPT
    assert classify_component("guardrails.md") == ComponentType.GUARDRAIL
    assert classify_component("LongTermMEMORY.md") == ComponentType.MEMORY
    assert classify_component("tool_guidance.md") == ComponentType.TOOL_GUIDANCE
    assert classify_component("sub_agents/macro/AGENT.md") == ComponentType.SUBAGENT
    assert classify_component("skills/trading/playbooks/momentum.md") == ComponentType.SKILL
    assert classify_component("scripts/calculate_atr.py") == ComponentType.SCRIPT
    assert classify_component("plugins/execution_guard.py") == ComponentType.PLUGIN


def test_reserved_paths_rejection():
    # Mechanical Fortress invariant: Risk paths are strictly protected
    assert is_path_reserved("src/monika/domain/risk/risk_gate.py") is True
    assert is_path_reserved(".env") is True
    assert is_path_reserved(".env.production") is True
    assert is_path_reserved("src/monika/infrastructure/brokers/ea_bridge/bridge.py") is True
    assert is_path_reserved("src/monika/infrastructure/database/migrations/versions/123.py") is True

    with pytest.raises(HarnessViolationError, match="reserved immutable path"):
        classify_component("src/monika/domain/risk/risk_gate.py")


def test_always_on_max_chars_budget():
    valid_tree = {
        "systemprompt.md": "A" * 1000,
        "guardrails.md": "B" * 1000,
        "LongTermMEMORY.md": "C" * 1000,
        "tool_guidance.md": "D" * 1000,
    }
    # Should pass comfortably within 32,000 char budget
    validate_tree_invariants(valid_tree, MONIKA_SURFACE)

    # Exceeding budget should fail closed
    oversized_tree = {
        "systemprompt.md": "A" * 35000,
        "guardrails.md": "B" * 1000,
    }
    with pytest.raises(HarnessViolationError, match="exceed maximum character cap"):
        validate_tree_invariants(oversized_tree, MONIKA_SURFACE)


def test_empty_core_guardrails_rejected():
    empty_guardrails_tree = {
        "systemprompt.md": "Valid prompt",
        "guardrails.md": "   ",  # empty
    }
    with pytest.raises(HarnessViolationError, match="cannot be empty"):
        validate_tree_invariants(empty_guardrails_tree, MONIKA_SURFACE)
