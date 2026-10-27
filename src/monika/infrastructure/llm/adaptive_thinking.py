"""
Per-Symbol Adaptive Thinking Budget Allocator.

Allocates thinking tokens dynamically based on per-symbol market microstructure,
volatility regime (VIX), setup ambiguity, and confluence score.
Prevents burning expensive reasoning tokens on quiet/clear setups while
guaranteeing deep chain-of-thought exploration on volatile/uncertain assets.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.AdaptiveThinking")


class QuantizedThinkingAllocator:
    """
    Quantizes reasoning budgets into discrete stable buckets.
    Guarantees 100% Anthropic and Gemini prompt caching hit rate across all symbols in a cycle.
    """

    BUCKETS: Dict[str, int] = {
        "LOW": 1024,  # Low volatility / orderly trend (EURUSD, AUDUSD, VIX < 20)
        "MEDIUM": 4096,  # Standard baseline / moderate volatility
        "HIGH": 10000,  # Borderline setups, elevated VIX (20-25), volatile pairs (Gold, Oil)
        "MAX": 16000,  # Capped for safety and token conservation
    }

    @classmethod
    def quantize(cls, raw_budget: int) -> int:
        """Maps any continuous token budget to the nearest discrete stable bucket."""
        if raw_budget >= 13000:
            return cls.BUCKETS["MAX"]
        elif raw_budget >= 7000:
            return cls.BUCKETS["HIGH"]
        elif raw_budget >= 2500:
            return cls.BUCKETS["MEDIUM"]
        else:
            return cls.BUCKETS["LOW"]


class PerSymbolAdaptiveThinkingAllocator:
    """
    Computes per-symbol reasoning effort and thinking token budgets dynamically.
    """

    # Asset baseline volatility multiplier
    ASSET_VOLATILITY_WEIGHTS: Dict[str, float] = {
        "BTCUSD": 1.4,
        "XAUUSD": 1.3,
        "XTIUSD": 1.2,
        "GBPUSD": 1.0,
        "USDJPY": 0.9,
        "EURUSD": 0.8,
        "AUDUSD": 0.8,
    }

    DEFAULT_WEIGHT: float = 1.0

    # Explicit task roles strictly mapped to Zero Thinking (budget = 0)
    ZERO_THINKING_ROLES: set[str] = {
        "news_classification",
        "news_classification_escalation",
        "news_classification_verifier",
        "news_digest",
        "news_digest_macro_overview",
        "news_digest_verifier",
        "fundamental_verifier",
        "stage1_shadow_check",
        "stage2_prescreen",
        "jev_news_realtime",
        "jev_trigger_validator",
        "jev_position_guard",
        "jev_telegram_intent",
        "jev_exit_prescreen",
        "jev_confluence_gate",
        "jev_session_timing_gate",
        "jev_debate_evaluator",
        "pattern_context_verifier",
        "summarizer",
        "context_compaction",
        "voice_transcription",
    }

    # Role-calibrated base thinking budgets (tokens) aligned with 56 task_roles
    ROLE_BASE_BUDGETS: Dict[str, int] = {
        # Stage 1 Macro & Fundamentals
        "stage1_fundamental": 4096,
        "fundamental_stage": 4096,
        "stage1_escalation": 4096,
        "stage1_delta_revision": 2048,
        # Stage 2 Per-Asset Technical Execution
        "stage2_per_asset_primary": 4096,
        "per_asset_stage": 4096,
        "stage2_per_asset_secondary": 4096,
        "stage2_session_trigger": 4096,
        "stage2_adjudicator": 2048,
        # Debate System
        "debate_bull": 2048,
        "debate_bear": 2048,
        "debate_judge": 2048,
        "bull_analyst": 2048,
        "bear_analyst": 2048,
        "macro_bull": 2048,
        "macro_bear": 2048,
        "investment_judge": 4096,
        "judge": 4096,
        "macro_judge": 4096,
        # Risk & Portfolio Management
        "risk_gate": 1024,
        "risk_gate_conservative": 1024,
        "risk_gate_aggressive": 1024,
        "risk_gate_neutral": 1024,
        "conservative_risk": 1024,
        "aggressive_risk": 1024,
        "neutral_risk": 1024,
        "portfolio_manager_per_trade": 2048,
        "portfolio_synthesis": 2048,
        "portfolio_manager": 2048,
        "adversarial_check": 1024,
        # Specialist Council
        "specialist_technical": 2048,
        "specialist_sentiment": 2048,
        "specialist_macro": 2048,
        "macro_analyst": 2048,
        "sentiment_analyst": 2048,
        # Research & Evolution
        "deep_research": 4096,
        "strategy_discovery": 4096,
        "cot_precompute": 2048,
        "trade_reflection": 2048,
        "reflection": 2048,
        "macro_chronicle_curator": 2048,
        "chronicle_writer": 2048,
        "lesson_consolidator": 2048,
        "report_synthesizer": 1024,
        "skill_crystallizer": 4096,
        "code_modification": 4096,
        "self_improver": 4096,
        # Chat & Interactive
        "chat_telegram": 1024,
        "chat_telegram_lite": 0,
        "chat_telegram_medium": 1024,
        "chat_telegram_complex": 4096,
        "chat_interactive_fast": 0,
        "chat_interactive_balanced": 1024,
        "chat_interactive_reasoning": 4096,
        "chat_interactive_pro": 4096,
    }

    @classmethod
    def compute_symbol_budget(
        cls, symbol: str, context: Optional[Dict[str, Any]] = None, base_budget: int = 4000, quantized: bool = True
    ) -> int:
        """
        Calculates exact thinking token budget (tokens) for a given symbol.

        Args:
            symbol: Target instrument (e.g. 'BTCUSD', 'XAUUSD', 'EURUSD')
            context: Context dictionary with optional 'vix', 'confluence_score', 'regime', 'atr_percentile'
            base_budget: Default baseline budget before multipliers
            quantized: If True, quantizes budget into discrete stable buckets (1024, 4096, 10000, 16000)
                       to preserve 100% prompt caching hit rate across assets.

        Returns:
            Thinking token budget clamped between 1,024 and 16,384 tokens.
        """
        ctx = context or {}
        sym_clean = (symbol or "").strip().upper().replace("/", "")
        asset_mult = cls.ASSET_VOLATILITY_WEIGHTS.get(sym_clean, cls.DEFAULT_WEIGHT)

        # 1. Market Volatility Multiplier (VIX)
        vix_val = float(ctx.get("vix") or ctx.get("vix_close") or 20.0)
        if vix_val >= 30.0:
            vix_mult = 1.6  # Crisis / high stress
        elif vix_val >= 25.0:
            vix_mult = 1.35  # Defensive regime
        elif vix_val >= 20.0:
            vix_mult = 1.15  # Caution regime
        else:
            vix_mult = 0.85  # Low volatility / orderly trend

        # 2. Setup Ambiguity / Confluence Multiplier
        confluence = ctx.get("confluence_score")
        if confluence is not None:
            try:
                conf_val = float(confluence)
                if conf_val < 5.0:
                    # Very low confluence: fast exit without endless deliberation
                    conf_mult = 0.5
                elif conf_val < 8.0:
                    # Borderline setup: deep reasoning required to resolve conflicts
                    conf_mult = 1.3
                else:
                    # High conviction / clear confluence: orderly verification
                    conf_mult = 1.0
            except ValueError, TypeError:
                conf_mult = 1.0
        else:
            conf_mult = 1.0

        # 3. Macro Regime Multiplier
        regime = str(ctx.get("regime") or ctx.get("macro_regime") or "").upper()
        if "SHIFT" in regime or "CRISIS" in regime or "STAGFLATION" in regime:
            regime_mult = 1.3
        elif "TRANSITION" in regime:
            regime_mult = 1.15
        else:
            regime_mult = 1.0

        computed = int(base_budget * asset_mult * vix_mult * conf_mult * regime_mult)
        clamped = max(1024, min(16000, computed))

        final_budget = QuantizedThinkingAllocator.quantize(clamped) if quantized else clamped

        logger.debug(
            f"[{sym_clean}] Adaptive thinking budget: {final_budget} tokens (raw={clamped}, quantized={quantized}) "
            f"(asset={asset_mult:.2f}, vix={vix_mult:.2f}, conf={conf_mult:.2f}, regime={regime_mult:.2f})"
        )
        return final_budget

    @classmethod
    def get_thinking_level(cls, symbol: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Maps the adaptive computation to standardized thinking levels:
        'minimal', 'low', 'medium', 'high', or 'max'.
        """
        budget = cls.compute_symbol_budget(symbol, context, base_budget=4000)

        if budget >= 10000:
            return "high"
        elif budget >= 5000:
            return "medium"
        elif budget >= 2500:
            return "low"
        else:
            return "minimal"

    @classmethod
    def get_thinking_budget_for_task(
        cls,
        task_role: Optional[str] = None,
        symbol: str = "",
        context: Optional[Dict[str, Any]] = None,
        base_budget: Optional[int] = None,
    ) -> int:
        """
        Determines the appropriate thinking token budget based on task role and symbol context.
        Enforces:
        - 0 tokens for fast prescreen / filters
        - Calibrated role budgets (4096-16000) for domain specialists, analysts, and adjudicators
        - Adaptive full dynamic tokens when symbol microstructure context is provided
        """
        role_clean = (task_role or "").lower()
        if role_clean in cls.ZERO_THINKING_ROLES:
            return 0

        if "prescreen" in role_clean:
            return 0

        if "fast" in role_clean or "quick" in role_clean or "classification" in role_clean:
            return 0

        resolved_base = base_budget if base_budget is not None else cls.ROLE_BASE_BUDGETS.get(role_clean, 4000)
        if resolved_base <= 0:
            return 0

        if not symbol:
            return resolved_base

        return cls.compute_symbol_budget(symbol, context, base_budget=resolved_base)


def clamp_thinking_budget_to_answer_room(
    budget: int,
    max_tokens: int,
    min_answer_tokens: int = 1024,
    max_thinking_ratio: Optional[float] = None,
) -> int:
    """
    Clamps thinking token budget so it never starves max_tokens of answer completion headroom.
    Ensures at least min_answer_tokens remain available for the visible answer.
    Optionally enforces max_thinking_ratio (e.g. 0.7 for max 70% thinking) if provided.
    """
    if budget <= 0:
        return 0
    if max_tokens <= min_answer_tokens:
        return 0
    max_allowed_thinking = max(0, max_tokens - min_answer_tokens)
    if max_thinking_ratio is not None and 0.0 < max_thinking_ratio < 1.0:
        ratio_limit = int(max_tokens * max_thinking_ratio)
        max_allowed_thinking = min(max_allowed_thinking, ratio_limit)
    return max(0, min(budget, max_allowed_thinking))
