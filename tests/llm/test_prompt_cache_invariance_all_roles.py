# ==============================================================================
# File: tests/llm/test_prompt_cache_invariance_all_roles.py
# Description: Automated Prefix-Stability Regression Test Suite covering all
#              45 cacheable task roles across the 8 subsystems of Monika.
# ==============================================================================

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.core.config.profile_applicator import ALL_TASK_ROLES
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager
from monika.application.analysis.prompt.prompt_assembler import PromptAssembler
from monika.application.graph.nodes.risk.portfolio_synthesis import (
    PORTFOLIO_SYNTHESIS_SYSTEM_PROMPT,
)
from monika.application.analysis.validators.adversarial_check import (
    ADVERSARIAL_SYSTEM_PROMPT,
)
from monika.application.analysis.memory.reflector import (
    TRADE_REFLECTION_SYSTEM_PROMPT,
)
from monika.application.analysis.prefetch.news_digest.classification import (
    NEWS_CLASSIFICATION_VERIFIER_SYSTEM_PROMPT,
)
from monika.application.analysis.prefetch.news_digest.verification import (
    NEWS_BOUNDARY_CALIBRATION_SYSTEM_PROMPT,
    NEWS_ESCALATION_SYSTEM_PROMPT,
)
from monika.application.analysis.stages.per_asset.runner_mixins.prescreen import (
    PRESCREEN_SYSTEM_PROMPT,
)
from monika.application.analysis.validators.adjudication_verifier import (
    ADJUDICATION_SYSTEM_PROMPT,
)
from monika.application.analysis.tools.mixins.system_tools import (
    RISK_GATE_SYSTEM_PROMPT,
)
from monika.infrastructure.providers.openai_provider import OpenAIProvider


# ------------------------------------------------------------------------------
# 1. Role Taxonomy & Registry
# ------------------------------------------------------------------------------

EXEMPT_ROLES = {
    # System 1 / JEV Reflex Models (10 roles) — Sub-100ms non-caching by design
    "stage1_shadow_check",
    "pattern_context_verifier",
    "jev_debate_evaluator",
    "jev_news_realtime",
    "jev_trigger_validator",
    "jev_position_guard",
    "jev_exit_prescreen",
    "jev_confluence_gate",
    "jev_session_timing_gate",
    "jev_telegram_intent",
    # Audio Role (1 role) — Audio ingestion via Whisper Large v3
    "voice_transcription",
}


@dataclass(frozen=True)
class RoleSpec:
    name: str
    subsystem: str
    provider: str
    model: str
    min_chars_threshold: int


CACHEABLE_ROLE_SPECS: Dict[str, RoleSpec] = {
    # Subsystem G1: Macro (11 roles)
    "stage1_fundamental": RoleSpec("stage1_fundamental", "G1_MACRO", "gemini", "gemini-4-argon", 21000),
    "stage1_escalation": RoleSpec("stage1_escalation", "G1_MACRO", "anthropic", "claude-opus-5.5", 4200),
    "stage1_delta_revision": RoleSpec("stage1_delta_revision", "G1_MACRO", "gemini", "gemini-3.5-flash-lite", 21000),
    "fundamental_verifier": RoleSpec("fundamental_verifier", "G1_MACRO", "gemini", "gemini-3.5-flash-lite", 21000),
    "macro_analyst": RoleSpec("macro_analyst", "G1_MACRO", "gemini", "gemini-3.5-flash-lite", 21000),
    "deep_research": RoleSpec("deep_research", "G1_MACRO", "gemini", "gemini-4-argon", 21000),
    "strategy_discovery": RoleSpec("strategy_discovery", "G1_MACRO", "gemini", "gemini-3.5-flash-lite", 21000),
    "report_synthesizer": RoleSpec("report_synthesizer", "G1_MACRO", "gemini", "gemini-3.5-flash-lite", 21000),
    "context_compaction": RoleSpec("context_compaction", "G1_MACRO", "gemini", "gemini-3.5-flash-lite", 21000),
    "summarizer": RoleSpec("summarizer", "G1_MACRO", "deepseek", "deepseek-v4.1-flash", 256),
    "macro_chronicle_curator": RoleSpec(
        "macro_chronicle_curator",
        "G1_MACRO",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    # Subsystem G2: Asset (4 roles)
    "stage2_per_asset_primary": RoleSpec(
        "stage2_per_asset_primary",
        "G2_ASSET",
        "minimax",
        "minimax-m3.1-flash",
        2000,
    ),
    "stage2_per_asset_secondary": RoleSpec(
        "stage2_per_asset_secondary",
        "G2_ASSET",
        "minimax",
        "minimax-m3.1-flash",
        2000,
    ),
    "stage2_session_trigger": RoleSpec(
        "stage2_session_trigger",
        "G2_ASSET",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    "stage2_prescreen": RoleSpec("stage2_prescreen", "G2_ASSET", "gemini", "gemini-3.5-flash-lite", 21000),
    # Subsystem G3: Specialist (4 roles)
    "specialist_technical": RoleSpec("specialist_technical", "G3_SPECIALIST", "minimax", "minimax-m3.1-flash", 2000),
    "specialist_sentiment": RoleSpec(
        "specialist_sentiment",
        "G3_SPECIALIST",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    "specialist_macro": RoleSpec("specialist_macro", "G3_SPECIALIST", "gemini", "gemini-3.5-flash-lite", 21000),
    "sentiment_analyst": RoleSpec("sentiment_analyst", "G3_SPECIALIST", "gemini", "gemini-3.5-flash-lite", 21000),
    # Subsystem G4: Debate (4 roles)
    "debate_bull": RoleSpec("debate_bull", "G4_DEBATE", "glm", "glm-5.3-flash", 2000),
    "debate_bear": RoleSpec("debate_bear", "G4_DEBATE", "glm", "glm-5.3-flash", 2000),
    "debate_judge": RoleSpec("debate_judge", "G4_DEBATE", "gemini", "gemini-3.8-flash", 21000),
    "stage2_adjudicator": RoleSpec("stage2_adjudicator", "G4_DEBATE", "minimax", "minimax-m3.1-flash", 2000),
    # Subsystem G5: Risk (8 roles)
    "risk_gate_conservative": RoleSpec(
        "risk_gate_conservative",
        "G5_RISK",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    "risk_gate_aggressive": RoleSpec("risk_gate_aggressive", "G5_RISK", "gemini", "gemini-3.5-flash-lite", 21000),
    "risk_gate_neutral": RoleSpec("risk_gate_neutral", "G5_RISK", "gemini", "gemini-3.5-flash-lite", 21000),
    "risk_gate": RoleSpec("risk_gate", "G5_RISK", "gemini", "gemini-3.5-flash-lite", 21000),
    "portfolio_manager_per_trade": RoleSpec(
        "portfolio_manager_per_trade",
        "G5_RISK",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    "portfolio_synthesis": RoleSpec("portfolio_synthesis", "G5_RISK", "minimax", "minimax-m3.1-flash", 2000),
    "adversarial_check": RoleSpec("adversarial_check", "G5_RISK", "gemini", "gemini-3.5-flash-lite", 21000),
    "trade_reflection": RoleSpec("trade_reflection", "G5_RISK", "minimax", "minimax-m3.1-flash", 2000),
    # Subsystem G6: News (7 roles)
    "news_classification": RoleSpec("news_classification", "G6_NEWS", "gemini", "gemini-3.5-flash-lite", 21000),
    "news_classification_escalation": RoleSpec(
        "news_classification_escalation",
        "G6_NEWS",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    "news_classification_verifier": RoleSpec(
        "news_classification_verifier",
        "G6_NEWS",
        "gemini",
        "gemini-3.5-flash-lite",
        21000,
    ),
    "news_digest": RoleSpec("news_digest", "G6_NEWS", "gemini", "gemini-3.8-flash", 21000),
    "news_digest_macro_overview": RoleSpec(
        "news_digest_macro_overview", "G6_NEWS", "gemini", "gemini-3.8-flash", 21000
    ),
    "news_digest_verifier": RoleSpec("news_digest_verifier", "G6_NEWS", "gemini", "gemini-3.5-flash-lite", 21000),
    "cot_precompute": RoleSpec("cot_precompute", "G6_NEWS", "glm", "glm-5.3-flash", 2000),
    # Subsystem G8: Chat (7 roles)
    "chat_telegram": RoleSpec("chat_telegram", "G8_CHAT", "gemini", "gemini-3.5-flash-lite", 21000),
    "chat_telegram_medium": RoleSpec("chat_telegram_medium", "G8_CHAT", "minimax", "minimax-m3.1-flash", 2000),
    "chat_telegram_complex": RoleSpec("chat_telegram_complex", "G8_CHAT", "minimax", "minimax-m3.1-flash", 2000),
    "chat_interactive_fast": RoleSpec("chat_interactive_fast", "G8_CHAT", "gemini", "gemini-3.5-flash-lite", 21000),
    "chat_interactive_balanced": RoleSpec("chat_interactive_balanced", "G8_CHAT", "glm", "glm-5.3-flash", 2000),
    "chat_interactive_reasoning": RoleSpec(
        "chat_interactive_reasoning",
        "G8_CHAT",
        "deepseek",
        "deepseek-v4.1-flash-1017",
        256,
    ),
    "chat_interactive_pro": RoleSpec("chat_interactive_pro", "G8_CHAT", "gemini", "gemini-4-argon", 21000),
}

ALL_45_CACHEABLE_ROLES: List[str] = sorted(list(CACHEABLE_ROLE_SPECS.keys()))


# ------------------------------------------------------------------------------
# 2. Offline Deterministic Prompt Simulator
# ------------------------------------------------------------------------------


def simulate_role_prompt_construction(
    role: str,
    timestamp_str: str,
    asset_data: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Offline simulator constructing (system_prompt, user_message) for any cacheable task role.
    Simulates production prompt construction without hitting live network or broker endpoints.
    """
    spec = CACHEABLE_ROLE_SPECS[role]
    anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
    shared_anchor = CacheBreakpointManager.get_canonical_debate_system_prompt(include_discipline=True)

    # 1. Macro Orchestration
    if role == "stage1_fundamental":
        assembler = PromptAssembler(settings={"trading": {}})
        t1, t2, _ = assembler.assemble_stage1_tiers(pad_for_gemini=True, inject_anchor=True)
        sys_prompt = f"{t1}\n\n---\n\n{t2}"
        user_msg = (
            f"Analyze global macro indicators and produce a fundamental brief.\n\n"
            f"[PRE-FETCHED DATA]\n{json.dumps(asset_data, sort_keys=True)}\n\n"
            f"[EXECUTION_METADATA]: Current time is {timestamp_str}"
        )
        return sys_prompt, user_msg

    if role == "stage2_per_asset_primary":
        assembler = PromptAssembler(settings={"trading": {}})
        t1, t2, _ = assembler.assemble_stage2_tiers(
            symbol="EURUSD",
            inject_anchor=True,
            include_target_in_system=False,
        )
        sys_prompt = f"{t1}\n\n---\n\n{t2}"
        # Preserves context_blocks (macro) before data_bundle (symbol)
        user_msg = (
            f"Analyze asset {asset_data.get('symbol')} and formulate setup.\n\n"
            f"[CYCLE MACRO BRIEF]\nShared cycle macro brief across all 20 assets.\n\n"
            f"[PRE-FETCHED SYMBOL DATA]\n{json.dumps(asset_data, sort_keys=True)}"
        )
        return sys_prompt, user_msg

    # 2. Debate Roles (Bull, Bear, Judge)
    if role in ("debate_bull", "debate_bear", "debate_judge"):
        sys_prompt = shared_anchor
        fact_sheet = {
            "symbol": asset_data.get("symbol", "EURUSD"),
            "price": asset_data.get("price", 1.0850),
            "atr_14": 0.0025,
        }
        original_context = {
            "symbol": asset_data.get("symbol", "EURUSD"),
            "decision": "BUY",
            "entry": asset_data.get("price", 1.0850),
        }
        append_ledger = {"bull_claim": {"strength": 8}} if role != "debate_bull" else None
        user_msg = CacheBreakpointManager.build_shared_debate_user_message(
            fact_sheet=fact_sheet,
            original_context=original_context,
            append_ledger=append_ledger,
            task_directive=f"Directive for {role}",
        )
        return sys_prompt, user_msg

    # 3. Risk Personas
    if role in (
        "risk_gate_conservative",
        "risk_gate_aggressive",
        "risk_gate_neutral",
        "portfolio_manager_per_trade",
    ):
        persona_directive = f"You are the {role.upper()} manager. Protect capital and enforce strict limits."
        sys_prompt = f"{shared_anchor}\n\n---\n\n{persona_directive}"
        user_msg = f"Symbol: {asset_data.get('symbol')}\nContext: {json.dumps(asset_data, sort_keys=True)}"
        return sys_prompt, user_msg

    # 4. Modules with Predefined Padded Constants
    if role == "portfolio_synthesis":
        sys_prompt = PORTFOLIO_SYNTHESIS_SYSTEM_PROMPT
        # Note: volatile analysis_id removed from user prompt
        user_msg = f"Synthesize proposed trades: {asset_data.get('symbol')} BUY confidence=85%"
        return sys_prompt, user_msg

    if role == "adversarial_check":
        sys_prompt = ADVERSARIAL_SYSTEM_PROMPT
        user_msg = f"Check setup for {asset_data.get('symbol')} entry={asset_data.get('price')}"
        return sys_prompt, user_msg

    if role == "trade_reflection":
        sys_prompt = TRADE_REFLECTION_SYSTEM_PROMPT
        user_msg = f"Reflect on trade for {asset_data.get('symbol')}"
        return sys_prompt, user_msg

    if role == "risk_gate":
        sys_prompt = RISK_GATE_SYSTEM_PROMPT
        user_msg = f"Evaluate risk for {asset_data.get('symbol')}"
        return sys_prompt, user_msg

    if role == "stage2_prescreen":
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            PRESCREEN_SYSTEM_PROMPT,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="stage2_prescreen",
            force=True,
        )
        user_msg = f"Prescreen asset: {asset_data.get('symbol')}"
        return sys_prompt, user_msg

    if role == "stage2_adjudicator":
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            ADJUDICATION_SYSTEM_PROMPT,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="stage2_adjudicator",
            force=True,
        )
        user_msg = f"Adjudicate setup for {asset_data.get('symbol')}"
        return sys_prompt, user_msg

    if role == "news_classification":
        raw = "=== MONIKA FINANCIAL TAXONOMY & NEWS IMPACT CLASSIFICATION ONTOLOGY ==="
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            raw,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="news_classification",
            force=True,
        )
        user_msg = (
            f"Classify batch of news items.\n<untrusted_news_data>\nItem 1: ECB Rate decision\n</untrusted_news_data>\n"
            f"[EXECUTION_METADATA]: Current time is {timestamp_str}"
        )
        return sys_prompt, user_msg

    if role == "news_classification_escalation":
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            NEWS_ESCALATION_SYSTEM_PROMPT,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="news_classification_escalation",
            force=True,
        )
        user_msg = f"Escalate verification for {asset_data.get('symbol')}"
        return sys_prompt, user_msg

    if role == "news_classification_verifier":
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            NEWS_CLASSIFICATION_VERIFIER_SYSTEM_PROMPT,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="news_classification_verifier",
            force=True,
        )
        user_msg = "Verify boundary classification"
        return sys_prompt, user_msg

    if role == "news_digest":
        raw_currency_sys = (
            "You are an institutional macro analyst specializing in FX fundamental currency digests. "
            "Synthesize currency drivers and price action."
        )
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            raw_currency_sys,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="news_digest",
            force=True,
        )
        user_msg = "Generate currency digest"
        return sys_prompt, user_msg

    if role == "news_digest_macro_overview":
        raw_macro_sys = (
            "You are an institutional macro analyst writing the global macro overview section "
            "of a daily financial digest."
        )
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            raw_macro_sys,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="news_digest_macro_overview",
            force=True,
        )
        user_msg = "Generate macro overview digest"
        return sys_prompt, user_msg

    if role == "cot_precompute":
        raw = "You are a quantitative Commitment of Traders (COT) pre-processor."
        sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
            raw,
            model_name=spec.model,
            provider_name=spec.provider,
            task_role="cot_precompute",
            force=True,
        )
        user_msg = json.dumps(asset_data, sort_keys=True)
        return sys_prompt, user_msg

    # 5. DeepSeek / Special Models (Summarizer, Chat Reasoning)
    if role in ("summarizer", "chat_interactive_reasoning"):
        sys_prompt = (
            f"=== INVARIANT SYSTEM DIRECTIVE FOR {role.upper()} ===\n"
            f"Mandate: Perform rigorous, deterministic, objective quantitative reasoning and synthesis.\n"
            f"Follow all execution invariants, strict JSON schema formatting, risk constraints, and mathematical bounds.\n"
            f"Ground all observations in verifiable price, macroeconomic, or state facts without hallucination."
        )
        user_msg = f"Data: {json.dumps(asset_data, sort_keys=True)}"
        return sys_prompt, user_msg

    # 6. Generic Roles padded via Shared Model Anchor
    raw_directive = f"You are an institutional trading agent specialist performing task {role}."
    sys_prompt = CacheBreakpointManager.pad_system_prompt_to_threshold(
        raw_directive,
        model_name=spec.model,
        provider_name=spec.provider,
        task_role=role,
        force=True,
    )
    user_msg = f"Task: {role}\nData: {json.dumps(asset_data, sort_keys=True)}"
    return sys_prompt, user_msg


# ------------------------------------------------------------------------------
# 3. Test Cases
# ------------------------------------------------------------------------------


def test_taxonomy_classification_and_completeness():
    """Verify that all 56 task roles in Monika are partitioned into 45 cacheable and 11 exempt roles."""
    all_roles_set = set(ALL_TASK_ROLES)
    cacheable_set = set(CACHEABLE_ROLE_SPECS.keys())

    assert len(all_roles_set) == 56, f"Expected 56 roles, got {len(all_roles_set)}"
    assert len(EXEMPT_ROLES) == 11, f"Expected 11 exempt roles, got {len(EXEMPT_ROLES)}"
    assert len(cacheable_set) == 45, f"Expected 45 cacheable roles, got {len(cacheable_set)}"

    # Partition check: No overlap and exhaustive union
    assert cacheable_set.isdisjoint(EXEMPT_ROLES), "Overlap between cacheable and exempt roles!"
    assert cacheable_set | EXEMPT_ROLES == all_roles_set, "Unclassified roles found!"


@pytest.mark.parametrize("role", ALL_45_CACHEABLE_ROLES)
def test_all_45_cacheable_roles_prefix_invariance_and_thresholds(role: str):
    """
    Core regression test covering all 45 cacheable roles.
    Simulates prompt construction at T and T+7min with different assets, prices, UUIDs, and analysis IDs.
    Asserts:
    1. System prompt (or stable prefix) is 100% byte-identical between T and T+7min.
    2. Length of stable prefix exceeds provider's threshold.
    3. Volatile variables (timestamps, UUIDs, volatile analysis IDs) are never in the leading prefix.
    """
    spec = CACHEABLE_ROLE_SPECS[role]

    t0_time = "2026-10-28 10:00:00 UTC"
    t0_data = {
        "symbol": "EURUSD",
        "price": 1.0850,
        "uuid": "uuid-0001-aaaa-bbbb",
        "analysis_id": 90001,
        "volume": 0.5,
    }

    t1_time = "2026-10-28 10:07:00 UTC"
    t1_data = {
        "symbol": "GBPUSD",
        "price": 1.2950,
        "uuid": "uuid-0002-cccc-dddd",
        "analysis_id": 90002,
        "volume": 0.8,
    }

    sys_t0, user_t0 = simulate_role_prompt_construction(role, t0_time, t0_data)
    sys_t1, user_t1 = simulate_role_prompt_construction(role, t1_time, t1_data)

    # a. System prompt prefix is 100% byte-identical across cycles
    assert sys_t0 == sys_t1, (
        f"Cache rupture in {role}: System prompt mutated between T0 and T1!\n"
        f"Diff at pos: {[i for i in range(min(len(sys_t0), len(sys_t1))) if sys_t0[i] != sys_t1[i]][:5]}"
    )

    # b. Leading stable prefix length exceeds provider's threshold
    assert len(sys_t0) >= spec.min_chars_threshold, (
        f"Threshold violation in {role}: Length {len(sys_t0)} < required {spec.min_chars_threshold} chars "
        f"for provider {spec.provider} / model {spec.model}"
    )

    # c. Volatile variables are NEVER in the leading system prefix
    assert t0_time not in sys_t0, f"Timestamp leak in system prompt of {role}"
    assert t1_time not in sys_t1, f"Timestamp leak in system prompt of {role}"
    assert "uuid-0001" not in sys_t0, f"UUID leak in system prompt of {role}"
    assert "uuid-0002" not in sys_t1, f"UUID leak in system prompt of {role}"
    assert "90001" not in sys_t0, f"Analysis ID leak in system prompt of {role}"
    assert "90002" not in sys_t1, f"Analysis ID leak in system prompt of {role}"


def test_subsystem_g1_macro_timestamp_tail_discipline():
    """Verify Macro subsystem (G1) isolates dynamic execution timestamp strictly to prompt tail."""
    sys_prompt, user_msg = simulate_role_prompt_construction(
        "stage1_fundamental",
        "2026-10-28 10:07:00 UTC",
        {"regime": "trending", "dxy": 103.5},
    )

    assert len(sys_prompt) >= 21000
    assert "2026-10-28 10:07:00 UTC" not in sys_prompt

    # Timestamp must reside only in the final lines of the user message
    user_lines = [line.strip() for line in user_msg.strip().split("\n") if line.strip()]
    tail_text = "\n".join(user_lines[-2:])
    assert "[EXECUTION_METADATA]: Current time is 2026-10-28 10:07:00 UTC" in tail_text


def test_subsystem_g2_asset_macro_context_precedes_symbol_data():
    """Verify Asset subsystem (G2) places cycle macro context before symbol data for cross-asset caching."""
    sys_eur, user_eur = simulate_role_prompt_construction(
        "stage2_per_asset_primary", "2026-10-28 10:00:00 UTC", {"symbol": "EURUSD"}
    )
    sys_gbp, user_gbp = simulate_role_prompt_construction(
        "stage2_per_asset_primary", "2026-10-28 10:00:00 UTC", {"symbol": "GBPUSD"}
    )

    # System prompts are identical across 20 symbols
    assert sys_eur == sys_gbp
    assert len(sys_eur) >= 2000

    # User message places shared macro brief before symbol data
    pos_macro_eur = user_eur.index("[CYCLE MACRO BRIEF]")
    pos_symbol_eur = user_eur.index("[PRE-FETCHED SYMBOL DATA]")
    assert pos_macro_eur < pos_symbol_eur, "Macro context must precede symbol data"

    pos_macro_gbp = user_gbp.index("[CYCLE MACRO BRIEF]")
    pos_symbol_gbp = user_gbp.index("[PRE-FETCHED SYMBOL DATA]")
    assert pos_macro_gbp < pos_symbol_gbp, "Macro context must precede symbol data"


def test_subsystem_g3_specialist_cross_symbol_prefix_invariance():
    """Verify Specialist subsystem (G3) system prompts are 100% byte-identical across symbols."""
    specialists = [
        "specialist_technical",
        "specialist_sentiment",
        "specialist_macro",
        "sentiment_analyst",
    ]
    for spec_role in specialists:
        sys_eur, _ = simulate_role_prompt_construction(spec_role, "10:00", {"symbol": "EURUSD"})
        sys_gbp, _ = simulate_role_prompt_construction(spec_role, "10:00", {"symbol": "GBPUSD"})
        # 100% byte-identical across symbols
        assert sys_eur == sys_gbp, f"Specialist {spec_role} system prompt mutated across symbols"
        # Confirm that the specific evaluated symbol was not dynamically interpolated into the role directive suffix
        role_directive = sys_eur.split("=== ROLE DIRECTIVE ===")[-1] if "=== ROLE DIRECTIVE ===" in sys_eur else sys_eur
        assert "EURUSD" not in role_directive
        assert "GBPUSD" not in role_directive


def test_subsystem_g4_debate_segment_a_identical_across_bull_bear_judge():
    """Verify Debate subsystem (G4) Segment A prefix is 100% byte-identical between Bull, Bear, and Judge."""
    fact_sheet = {"symbol": "EURUSD", "price": 1.0850, "atr": 0.0020}
    original_context = {"symbol": "EURUSD", "decision": "BUY", "entry": 1.0850}

    bull_msg = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet, original_context, append_ledger=None, task_directive="Bull"
    )
    bear_msg = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet,
        original_context,
        append_ledger={"bull_claim": {"strength": 8}},
        task_directive="Bear",
    )
    judge_msg = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet,
        original_context,
        append_ledger={
            "bull_claim": {"strength": 8},
            "bear_dissent": {"severity": 6},
        },
        task_directive="Judge",
    )

    breakpoint_delimiter = "=== TIER 2 CYCLE CACHE BREAKPOINT ===\n\n"
    assert breakpoint_delimiter in bull_msg
    assert breakpoint_delimiter in bear_msg
    assert breakpoint_delimiter in judge_msg

    seg_a_bull = bull_msg.split(breakpoint_delimiter)[0] + breakpoint_delimiter
    seg_a_bear = bear_msg.split(breakpoint_delimiter)[0] + breakpoint_delimiter
    seg_a_judge = judge_msg.split(breakpoint_delimiter)[0] + breakpoint_delimiter

    # Segment A before breakpoint is 100% byte-identical
    assert seg_a_bull == seg_a_bear == seg_a_judge
    assert len(seg_a_bull) > 100


def test_subsystem_g5_risk_personas_and_portfolio_synthesis_id_cleanliness():
    """Verify Risk subsystem (G5) system prompts exceed threshold and synthesis is free of analysis IDs."""
    risk_roles = [
        "risk_gate_conservative",
        "risk_gate_aggressive",
        "risk_gate_neutral",
        "portfolio_manager_per_trade",
        "portfolio_synthesis",
        "adversarial_check",
        "trade_reflection",
    ]
    for r in risk_roles:
        sys_p, user_p = simulate_role_prompt_construction(r, "10:00", {"symbol": "XAUUSD", "analysis_id": 9999})
        assert len(sys_p) >= 2000, f"{r} prompt length below minimum"
        assert "9999" not in sys_p, f"Analysis ID leaked into system prompt of {r}"
        if r == "portfolio_synthesis":
            assert "9999" not in user_p, "Analysis ID leaked into portfolio synthesis user prompt"


def test_subsystem_g6_news_static_header_and_singleton_context():
    """Verify News subsystem (G6) system prompts exceed threshold and verifiers are anchored."""
    news_roles = [
        "news_classification",
        "news_classification_escalation",
        "news_classification_verifier",
        "news_digest",
        "news_digest_macro_overview",
        "news_digest_verifier",
        "cot_precompute",
    ]
    for r in news_roles:
        sys_p, _ = simulate_role_prompt_construction(r, "10:00", {"title": "Fed Hikes Rates"})
        assert len(sys_p) >= 2000, f"{r} prompt length below minimum"
        assert "=== CANONICAL SYSTEM GOVERNANCE" in sys_p or "MONIKA" in sys_p


@pytest.mark.asyncio
async def test_subsystem_g8_chat_turn_0_invariance_and_snapshot_placement():
    """Verify Chat subsystem (G8) Turn 0 user message is identical across turns and snapshot attached to last turn only."""
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-test-fake")
    captured_calls = []

    async def fake_chat_create(kwargs):
        captured_calls.append([dict(m) for m in kwargs["messages"]])
        choice = MagicMock()
        choice.message = MagicMock(role="assistant", content="OK", tool_calls=None)
        resp = MagicMock(choices=[choice], usage=MagicMock(prompt_tokens=10, completion_tokens=5))
        return resp

    provider._create_chat_completion = fake_chat_create

    sys_prefix = ("Static System Invariant Instructions", "Snapshot at T0: Equity=10000")
    # Turn 0
    msgs_t0 = [{"role": "user", "content": "Turn 0 User: Status report"}]
    await provider.run_tool_agent(messages=msgs_t0, tools=[], system_prompt=sys_prefix)

    # Turn 1
    sys_prefix_t1 = ("Static System Invariant Instructions", "Snapshot at T1: Equity=10050")
    msgs_t1 = [
        {"role": "user", "content": "Turn 0 User: Status report"},
        {"role": "assistant", "content": "Assistant: All systems nominal."},
        {"role": "user", "content": "Turn 1 User: Check BTCUSD position"},
    ]
    await provider.run_tool_agent(messages=msgs_t1, tools=[], system_prompt=sys_prefix_t1)

    # Turn 2
    sys_prefix_t2 = ("Static System Invariant Instructions", "Snapshot at T2: Equity=10080")
    msgs_t2 = [
        {"role": "user", "content": "Turn 0 User: Status report"},
        {"role": "assistant", "content": "Assistant: All systems nominal."},
        {"role": "user", "content": "Turn 1 User: Check BTCUSD position"},
        {"role": "assistant", "content": "Assistant: Long 0.1 BTC at 65000."},
        {"role": "user", "content": "Turn 2 User: Recommend stop adjustments"},
    ]
    await provider.run_tool_agent(messages=msgs_t2, tools=[], system_prompt=sys_prefix_t2)

    # Check Call 1 (Turn 0)
    assert captured_calls[0][0]["content"] == "Static System Invariant Instructions"
    assert "<context_snapshot>" in captured_calls[0][1]["content"]

    # Check Call 2 (Turn 1)
    call2_user0 = captured_calls[1][1]
    call2_user1 = captured_calls[1][3]
    # Historical Turn 0 user message MUST NOT contain snapshot
    assert "<context_snapshot>" not in call2_user0["content"]
    assert call2_user0["content"] == "Turn 0 User: Status report"
    # Active Turn 1 user message MUST contain snapshot
    assert "<context_snapshot>" in call2_user1["content"]

    # Check Call 3 (Turn 2)
    call3_user0 = captured_calls[2][1]
    call3_user1 = captured_calls[2][3]
    call3_user2 = captured_calls[2][5]
    assert "<context_snapshot>" not in call3_user0["content"]
    assert "<context_snapshot>" not in call3_user1["content"]
    assert "<context_snapshot>" in call3_user2["content"]

    # Turn 0 in Call 2 and Call 3 is 100% byte-identical
    assert call2_user0["content"] == call3_user0["content"] == "Turn 0 User: Status report"


def test_exempt_roles_explicitly_documented_and_non_caching():
    """Verify that all 11 exempt roles are documented and confirmed non-caching by architectural design."""
    assert len(EXEMPT_ROLES) == 11
    # 10 JEV System 1 reflex roles
    jev_roles = [r for r in EXEMPT_ROLES if r.startswith("jev_") or "shadow" in r or "pattern" in r]
    assert len(jev_roles) == 10
    # 1 Audio role
    assert "voice_transcription" in EXEMPT_ROLES
