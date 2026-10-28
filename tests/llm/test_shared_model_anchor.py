"""
Tests for Shared Model Anchor System for Small-Prompt Roles (Commit 3).

Verifies:
1. Two different small roles produce byte-identical prefix through the anchor end (=== ROLE DIRECTIVE ===).
2. Roles in opt_out_roles do not receive anchor.
3. Disabled small_roles_anchor config disables anchor.
4. DeepSeek models/providers do not receive anchor.
5. Roles whose prompt already starts with CANONICAL_TIER0_ANCHOR or [GOVERNANCE_ANCHOR do not get duplicate anchor.
6. Pydantic schema validation for SmallRolesAnchorConfig in schemas.py and LLMConfig.
"""

from monika.core.config.schemas import LLMConfig, SmallRolesAnchorConfig
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager


def test_small_roles_anchor_config_schema():
    """Verify SmallRolesAnchorConfig default values and subscript access."""
    cfg = SmallRolesAnchorConfig()
    assert cfg.enabled is True
    assert cfg.opt_out_roles == []
    assert cfg["enabled"] is True
    assert cfg.get("opt_out_roles") == []

    cfg_custom = SmallRolesAnchorConfig(enabled=False, opt_out_roles=["stage2_prescreen"])
    assert cfg_custom.enabled is False
    assert cfg_custom.opt_out_roles == ["stage2_prescreen"]
    assert cfg_custom["opt_out_roles"] == ["stage2_prescreen"]

    llm_cfg = LLMConfig()
    assert llm_cfg.small_roles_anchor is not None
    assert llm_cfg.small_roles_anchor.enabled is True
    assert llm_cfg.small_roles_anchor.opt_out_roles == []


def test_shared_model_anchor_byte_identical_prefix_across_small_roles():
    """Two different small roles produce 100% byte-identical prefix through === ROLE DIRECTIVE ===."""
    prompt_verifier = "You are a fundamental verifier. Verify macro facts against source numbers."
    prompt_prescreen = "You are a stage2 prescreen classifier. Check asset structure."

    padded_verifier = CacheBreakpointManager.pad_system_prompt_to_threshold(
        prompt_verifier,
        model_name="gemini-3.5-flash-lite",
        provider_name="gemini",
        task_role="fundamental_verifier",
    )
    padded_prescreen = CacheBreakpointManager.pad_system_prompt_to_threshold(
        prompt_prescreen,
        model_name="gemini-3.5-flash-lite",
        provider_name="gemini",
        task_role="stage2_prescreen",
    )

    anchor = CacheBreakpointManager.get_canonical_debate_system_prompt(include_discipline=True)
    delimiter = "\n\n=== ROLE DIRECTIVE ===\n\n"
    expected_prefix = f"{anchor}{delimiter}"

    assert len(expected_prefix) > 21000  # Exceeds Gemini 3 threshold
    assert padded_verifier.startswith(expected_prefix)
    assert padded_prescreen.startswith(expected_prefix)

    # Prefix through delimiter is 100% byte-identical
    assert padded_verifier[: len(expected_prefix)] == padded_prescreen[: len(expected_prefix)]

    # Suffixes retain original distinct role directives cleanly
    assert padded_verifier.endswith(prompt_verifier)
    assert padded_prescreen.endswith(prompt_prescreen)
    assert padded_verifier != padded_prescreen


def test_opt_out_roles_does_not_receive_anchor():
    """Role listed in opt_out_roles does not receive anchor padding."""
    raw_prompt = "You are a fundamental verifier. Check inflation numbers."
    settings = {
        "llm": {
            "small_roles_anchor": {
                "enabled": True,
                "opt_out_roles": ["fundamental_verifier"],
            }
        }
    }
    result = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_prompt,
        model_name="gemini-3.5-flash-lite",
        provider_name="gemini",
        task_role="fundamental_verifier",
        settings=settings,
    )
    assert result == raw_prompt
    assert "=== CANONICAL SYSTEM GOVERNANCE" not in result


def test_disabled_small_roles_anchor_config_skips_anchor():
    """When small_roles_anchor.enabled is False, small roles do not receive anchor."""
    raw_prompt = "You are a stage2 prescreen classifier."
    settings = {
        "llm": {
            "small_roles_anchor": {
                "enabled": False,
                "opt_out_roles": [],
            }
        }
    }
    result = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_prompt,
        model_name="gemini-3.5-flash-lite",
        provider_name="gemini",
        task_role="stage2_prescreen",
        settings=settings,
    )
    assert result == raw_prompt
    assert "=== ROLE DIRECTIVE ===" not in result


def test_deepseek_model_does_not_receive_anchor():
    """DeepSeek models/providers (64-token disk cache unit) do not receive large anchor padding."""
    raw_prompt = "You are a summarizer. Extract key entities."

    # By model name
    res_mod = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_prompt,
        model_name="deepseek-v4.1-flash",
        provider_name="openrouter",
        task_role="summarizer",
    )
    assert res_mod == raw_prompt
    assert "=== ROLE DIRECTIVE ===" not in res_mod

    # By provider name
    res_prov = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_prompt,
        model_name="custom-model",
        provider_name="deepseek",
        task_role="summarizer",
    )
    assert res_prov == raw_prompt
    assert "=== ROLE DIRECTIVE ===" not in res_prov


def test_already_anchored_prompt_does_not_get_duplicate_anchor():
    """Prompt that already starts with CANONICAL_TIER0_ANCHOR or [GOVERNANCE_ANCHOR does not duplicate."""
    anchor_prefix = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
    raw_prompt = f"{anchor_prefix}\n\n=== ROLE DIRECTIVE ===\n\nSpecific directive content."

    result = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_prompt,
        model_name="gemini-3.5-flash-lite",
        provider_name="gemini",
        task_role="fundamental_verifier",
    )
    assert result == raw_prompt
    assert result.count("=== CANONICAL SYSTEM GOVERNANCE") == 1

    governance_prompt = "[GOVERNANCE_ANCHOR]: Tier 0 system rules apply.\nRole task here."
    result_gov = CacheBreakpointManager.pad_system_prompt_to_threshold(
        governance_prompt,
        model_name="gemini-3.5-flash-lite",
        provider_name="gemini",
        task_role="fundamental_verifier",
    )
    assert result_gov == governance_prompt
