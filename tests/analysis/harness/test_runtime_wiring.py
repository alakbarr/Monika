"""
Unit and integration tests verifying that the Harness system is actively wired
into Monika's primary runtime (TradingAgent, Container, PromptSectionRegistry, PlaybookCurator).
"""

from unittest.mock import MagicMock, patch
import pytest

from monika.application.analysis.harness.library import DomainExperienceLibrary
from monika.application.analysis.harness.service import RecursiveHarnessService
from monika.application.analysis.harness.tree import HarnessTree
from monika.application.analysis.prompt_sections import get_prompt_section_registry
from monika.application.orchestrator.agent import TradingAgent


def test_trading_agent_builder_wires_harness_service():
    """Verify TradingAgent builder initializes harness_service and registers prompt sections."""
    agent = TradingAgent(settings={})
    agent._init_components()

    # 1. Assert harness_service is instantiated and assigned
    assert agent.harness_service is not None
    assert isinstance(agent.harness_service, RecursiveHarnessService)

    # 2. Assert harness_service is registered in the DI container
    assert agent.container is not None
    assert agent.container.get("harness_service") is agent.harness_service

    # 3. Assert prompt section registry contains harness_domain_lessons
    psr = get_prompt_section_registry()
    assert "harness_domain_lessons" in psr._sections


def test_prompt_section_renders_domain_lessons_in_runtime(tmp_path):
    """Verify that when the LLM formats prompts, domain lessons from the Harness Library are injected."""
    agent = TradingAgent(settings={})
    agent._init_components()

    # Point library to tmp_path for test hermeticity
    test_lib = DomainExperienceLibrary(root_dir=tmp_path)
    agent.harness_service.library = test_lib

    # Record a test lesson in EURUSD_TREND
    tree = HarnessTree.build_baseline_tree()
    test_lib.record_experience(
        domain="EURUSD_TREND",
        run_id="run_eur_test",
        tree=tree,
        cue="London breakout setup",
        lesson="Require M15 displacement before trading the breakout.",
        evidence={"win_rate": 0.85},
    )

    psr = get_prompt_section_registry()
    formatted = psr.format_full_prompt(
        base_prompt="Analyze EURUSD market structure.",
        context={"domain": "EURUSD_TREND"},
    )

    # Assert the domain lesson was rendered into the prompt
    assert "Historical Domain Lessons (EURUSD_TREND)" in formatted
    assert "Require M15 displacement" in formatted
    assert "Analyze EURUSD market structure." in formatted
