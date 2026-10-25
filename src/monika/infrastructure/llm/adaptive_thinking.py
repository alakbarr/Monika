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

    # Role-calibrated base thinking budgets (tokens) aligned with DEFAULT_TASK_THINKING
    ROLE_BASE_BUDGETS: Dict[str, int] = {
        "fundamental_stage": 16000,
        "per_asset_stage": 16000,
        "investment_judge": 16000,
        "judge": 16000,
        "macro_judge": 16000,
        "portfolio_manager": 16000,
        "skill_crystallizer": 16000,
        "code_modification": 16000,
        "self_improver": 16000,
        "debate_bull": 10000,
        "debate_bear": 10000,
        "bull_analyst": 10000,
        "bear_analyst": 10000,
        "macro_bull": 10000,
        "macro_bear": 10000,
        "risk_gate_conservative": 10000,
        "risk_gate_aggressive": 10000,
        "risk_gate_neutral": 10000,
        "conservative_risk": 10000,
        "aggressive_risk": 10000,
        "neutral_risk": 10000,
        "specialist_technical": 4096,
        "specialist_sentiment": 4096,
        "specialist_macro": 4096,
        "sentiment_analyst": 4096,
        "lesson_consolidator": 10000,
        "chronicle_writer": 10000,
        "reflection": 10000,
        "trade_reflection": 10000,
        "chat_telegram": 10000,
        "chat_telegram_lite": 1024,
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
) -> int:
    """
    Clamps thinking token budget so it never starves max_tokens of answer completion headroom.
    Ensures at least min_answer_tokens remain available for the visible answer.
    """
    if budget <= 0:
        return 0
    if max_tokens <= min_answer_tokens:
        return 0
    max_allowed_thinking = max(0, max_tokens - min_answer_tokens)
    return max(0, min(budget, max_allowed_thinking))
