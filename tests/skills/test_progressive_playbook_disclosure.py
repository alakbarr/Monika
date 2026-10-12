"""
Tests for PR-20: Progressive Playbook Disclosure.
Verifies list-then-load pattern, token budget savings, setup-specific expansion, and Ledger demotion pruning.
"""

import pytest
from unittest.mock import MagicMock, patch

from skills.loader import (
    compose_system_prompt,
    get_progressive_playbook_index,
    is_playbook_eligible,
)


def test_progressive_playbook_index_content():
    idx = get_progressive_playbook_index(symbol="EURUSD")
    assert "PLAYBOOK" in idx.upper() or "INDEX" in idx.upper()
    assert len(idx) < 1000  # Stays lightweight


def test_progressive_disclosure_replaces_bulky_playbook_with_index():
    # When progressive=True and no setup matching smc_ict is specified,
    # smc_ict_playbook is not dumped in its multi-kilobyte entirety; Level 0 index is used instead.
    prompt_progressive = compose_system_prompt(
        "adjudication_framework",
        "smc_ict_playbook",
        progressive=True,
        context={"symbol": "EURUSD"},
    )

    prompt_standard = compose_system_prompt(
        "adjudication_framework",
        "smc_ict_playbook",
        progressive=False,
    )

    assert len(prompt_progressive) < len(prompt_standard)
    assert "[AVAILABLE_PLAYBOOKS" in prompt_progressive or "PLAYBOOK" in prompt_progressive.upper()


def test_progressive_disclosure_discloses_full_when_setup_matches():
    # When progressive=True and setup indicates 'smc_ict', it expands the full playbook
    prompt_matched = compose_system_prompt(
        "adjudication_framework",
        "smc_ict_playbook",
        progressive=True,
        context={"symbol": "EURUSD", "setup": "smc_ict"},
    )
    assert len(prompt_matched) > 2000
    assert "smc" in prompt_matched.lower()


def test_demoted_playbook_pruned_via_ledger():
    mock_meta = MagicMock()
    mock_meta.status = "demoted"

    with patch("analysis.memory.playbook_lifecycle.PlaybookLifecycleManager") as MockMgr:
        instance = MockMgr.return_value
        instance.get_metadata.return_value = mock_meta

        assert is_playbook_eligible("failing_bad_strategy_playbook") is False

        # Verify pruned in compose_system_prompt
        prompt = compose_system_prompt("failing_bad_strategy_playbook", "adjudication_framework")
        assert "failing_bad_strategy_playbook" not in prompt


def test_backward_compatibility_when_progressive_false():
    # By default, progressive is False and backward compatibility is preserved
    prompt = compose_system_prompt("adjudication_framework", "risk_management_principles")
    assert "adjudication" in prompt.lower()
    assert "risk" in prompt.lower()
