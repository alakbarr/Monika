# ==============================================================================
# File: application/benchmark/task_specs/registry.py
# ==============================================================================

"""
Benchmark task specification registry mapping all task roles.
"""

from __future__ import annotations

from .base import TaskSpec
from .chat_cases import (
    _case_chat_interactive_balanced,
    _case_chat_interactive_fast,
    _case_chat_interactive_pro,
    _case_chat_interactive_reasoning,
    _case_chat_telegram,
    _case_chat_telegram_complex,
    _case_chat_telegram_medium,
    _case_jev_telegram_intent,
    _case_voice_transcription,
)
from .debate_cases import (
    _case_debate_bear,
    _case_debate_bull,
    _case_debate_judge,
    _case_jev_debate_evaluator,
    _case_stage2_adjudicator,
)
from .macro_cases import (
    _case_context_compaction,
    _case_deep_research,
    _case_strategy_discovery,
    _case_fundamental_verifier,
    _case_macro_analyst,
    _case_report_synthesizer,
    _case_stage1_escalation,
    _case_stage1_fundamental,
    _case_stage1_shadow_check,
    _case_summarizer,
)
from .news_cases import (
    _case_cot_precompute,
    _case_news_classification,
    _case_news_classification_escalation,
    _case_news_classification_verifier,
    _case_news_digest,
    _case_news_digest_macro_overview,
    _case_news_digest_verifier,
)
from .reflex_cases import (
    _case_harness_context_efficiency,
    _case_harness_hallucination_detect,
    _case_harness_self_correction,
    _case_jev_confluence_gate,
    _case_jev_exit_prescreen,
    _case_jev_news_realtime,
    _case_jev_position_guard,
    _case_jev_session_timing_gate,
    _case_jev_trigger_validator,
    _case_trade_reflection,
)
from .risk_cases import (
    _case_adversarial_check,
    _case_portfolio_manager_per_trade,
    _case_portfolio_synthesis,
    _case_risk_gate_aggressive,
    _case_risk_gate_conservative,
    _case_risk_gate_neutral,
    _case_risk_gate_task,
)
from .specialist_cases import (
    _case_pattern_context_verifier,
    _case_sentiment_analyst,
    _case_specialist_macro,
    _case_specialist_sentiment,
    _case_specialist_technical,
)
from .stage2_cases import (
    _case_stage2_prescreen,
    _case_stage2_primary,
    _case_stage2_secondary,
    _case_stage2_session_trigger,
)

TASKS: dict[str, TaskSpec] = {
    # 1. Macro Analysis & Verification
    "stage1_fundamental": TaskSpec("stage1_fundamental", "macro", "agent", _case_stage1_fundamental),
    "stage1_escalation": TaskSpec("stage1_escalation", "macro", "agent", _case_stage1_escalation),
    "stage1_shadow_check": TaskSpec("stage1_shadow_check", "macro", "json", _case_stage1_shadow_check),
    "fundamental_verifier": TaskSpec("fundamental_verifier", "macro", "json", _case_fundamental_verifier),
    "macro_analyst": TaskSpec("macro_analyst", "macro", "agent", _case_macro_analyst),
    "deep_research": TaskSpec("deep_research", "macro", "agent", _case_deep_research),
    "strategy_discovery": TaskSpec("strategy_discovery", "macro", "agent", _case_strategy_discovery),
    "report_synthesizer": TaskSpec("report_synthesizer", "macro", "text", _case_report_synthesizer),
    "context_compaction": TaskSpec("context_compaction", "macro", "text", _case_context_compaction),
    "summarizer": TaskSpec("summarizer", "macro", "text", _case_summarizer),
    # 2. Stage 2 Per-Asset Decisions
    "stage2_per_asset_primary": TaskSpec("stage2_per_asset_primary", "trade_decision", "agent", _case_stage2_primary),
    "stage2_per_asset_secondary": TaskSpec(
        "stage2_per_asset_secondary", "trade_decision", "agent", _case_stage2_secondary
    ),
    "stage2_session_trigger": TaskSpec(
        "stage2_session_trigger", "trade_decision", "agent", _case_stage2_session_trigger
    ),
    "stage2_prescreen": TaskSpec("stage2_prescreen", "trade_decision", "json", _case_stage2_prescreen),
    # 3. Domain Specialists
    "specialist_technical": TaskSpec("specialist_technical", "specialist", "json", _case_specialist_technical),
    "specialist_sentiment": TaskSpec("specialist_sentiment", "specialist", "json", _case_specialist_sentiment),
    "specialist_macro": TaskSpec("specialist_macro", "specialist", "json", _case_specialist_macro),
    "sentiment_analyst": TaskSpec("sentiment_analyst", "specialist", "json", _case_sentiment_analyst),
    "pattern_context_verifier": TaskSpec(
        "pattern_context_verifier", "specialist", "json", _case_pattern_context_verifier
    ),
    # 4. Dialectical Debate & Arbitration
    "debate_bull": TaskSpec("debate_bull", "debate", "custom", _case_debate_bull),
    "debate_bear": TaskSpec("debate_bear", "debate", "custom", _case_debate_bear),
    "debate_judge": TaskSpec("debate_judge", "debate", "custom", _case_debate_judge),
    "stage2_adjudicator": TaskSpec("stage2_adjudicator", "debate", "json", _case_stage2_adjudicator),
    "jev_debate_evaluator": TaskSpec("jev_debate_evaluator", "debate", "system_one", _case_jev_debate_evaluator),
    # 5. Risk Fortress & Portfolio Management
    "risk_gate": TaskSpec("risk_gate", "risk", "json", _case_risk_gate_task),
    "risk_gate_conservative": TaskSpec("risk_gate_conservative", "risk", "custom", _case_risk_gate_conservative),
    "risk_gate_aggressive": TaskSpec("risk_gate_aggressive", "risk", "custom", _case_risk_gate_aggressive),
    "risk_gate_neutral": TaskSpec("risk_gate_neutral", "risk", "custom", _case_risk_gate_neutral),
    "portfolio_manager_per_trade": TaskSpec(
        "portfolio_manager_per_trade", "risk", "custom", _case_portfolio_manager_per_trade
    ),
    "portfolio_synthesis": TaskSpec("portfolio_synthesis", "risk", "json", _case_portfolio_synthesis),
    "adversarial_check": TaskSpec("adversarial_check", "risk", "json", _case_adversarial_check),
    "trade_reflection": TaskSpec("trade_reflection", "reflection", "json", _case_trade_reflection),
    # 6. News Ingestion & Processing
    "news_classification": TaskSpec("news_classification", "news", "json", _case_news_classification),
    "news_classification_escalation": TaskSpec(
        "news_classification_escalation", "news", "json", _case_news_classification_escalation
    ),
    "news_classification_verifier": TaskSpec(
        "news_classification_verifier", "news", "json", _case_news_classification_verifier
    ),
    "news_digest": TaskSpec("news_digest", "news", "text", _case_news_digest),
    "news_digest_macro_overview": TaskSpec(
        "news_digest_macro_overview", "news", "text", _case_news_digest_macro_overview
    ),
    "news_digest_verifier": TaskSpec("news_digest_verifier", "news", "json", _case_news_digest_verifier),
    "cot_precompute": TaskSpec("cot_precompute", "news", "text", _case_cot_precompute),
    # 7. System One High-Speed Reflexes
    "jev_news_realtime": TaskSpec("jev_news_realtime", "news", "system_one", _case_jev_news_realtime),
    "jev_trigger_validator": TaskSpec(
        "jev_trigger_validator", "trade_decision", "system_one", _case_jev_trigger_validator
    ),
    "jev_position_guard": TaskSpec("jev_position_guard", "risk", "system_one", _case_jev_position_guard),
    "jev_exit_prescreen": TaskSpec("jev_exit_prescreen", "risk", "system_one", _case_jev_exit_prescreen),
    "jev_confluence_gate": TaskSpec("jev_confluence_gate", "trade_decision", "system_one", _case_jev_confluence_gate),
    "jev_session_timing_gate": TaskSpec("jev_session_timing_gate", "risk", "system_one", _case_jev_session_timing_gate),
    "jev_telegram_intent": TaskSpec("jev_telegram_intent", "chat", "json", _case_jev_telegram_intent),
    # 8. Interactive Assistants & Omnichannel
    "chat_telegram": TaskSpec("chat_telegram", "chat", "chat", _case_chat_telegram),
    "chat_telegram_medium": TaskSpec("chat_telegram_medium", "chat", "chat", _case_chat_telegram_medium),
    "chat_telegram_complex": TaskSpec("chat_telegram_complex", "chat", "chat", _case_chat_telegram_complex),
    "chat_interactive_fast": TaskSpec("chat_interactive_fast", "chat", "chat", _case_chat_interactive_fast),
    "chat_interactive_balanced": TaskSpec("chat_interactive_balanced", "chat", "chat", _case_chat_interactive_balanced),
    "chat_interactive_reasoning": TaskSpec(
        "chat_interactive_reasoning", "chat", "chat", _case_chat_interactive_reasoning
    ),
    "chat_interactive_pro": TaskSpec("chat_interactive_pro", "chat", "chat", _case_chat_interactive_pro),
    "voice_transcription": TaskSpec("voice_transcription", "chat", "json", _case_voice_transcription),
    # 9. Harness Auditing Probes
    "harness_hallucination_detect": TaskSpec(
        "harness_hallucination_detect", "macro", "json", _case_harness_hallucination_detect
    ),
    "harness_context_efficiency": TaskSpec(
        "harness_context_efficiency", "macro", "text", _case_harness_context_efficiency
    ),
    "harness_self_correction": TaskSpec(
        "harness_self_correction", "trade_decision", "json", _case_harness_self_correction
    ),
}
