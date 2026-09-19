import re
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("TradingAgent.FailureTaxonomy")


class FailureCategory(str, Enum):
    """Systematic reasoning failure taxonomy categories."""
    REGIME_MISCLASSIFICATION = "regime_misclassification"
    FALSE_BREAKOUT = "false_breakout"
    TIMING_EARLY = "timing_early"
    TIMING_LATE = "timing_late"
    SL_TOO_TIGHT = "sl_too_tight"
    SL_TOO_WIDE = "sl_too_wide"
    CORRELATION_SHOCK = "correlation_shock"
    NEWS_SPIKE = "news_spike"
    EXECUTION_SLIPPAGE = "execution_slippage"
    RISK_MISSIZING = "risk_missizing"
    COUNTER_TREND_BLINDNESS = "counter_trend_blindness"
    VOLATILITY_UNDERESTIMATION = "volatility_underestimation"
    UNGROUNDED_CONFLUENCE = "ungrounded_confluence"
    UNKNOWN_FAILURE = "unknown_failure"


PREVENTATIVE_RULES: Dict[FailureCategory, str] = {
    FailureCategory.REGIME_MISCLASSIFICATION: (
        "Verify higher-timeframe structure (H4/D1) and ADX before declaring trend continuation. "
        "Do not apply breakout strategies in ranging or choppy markets."
    ),
    FailureCategory.FALSE_BREAKOUT: (
        "Require candle close confirmation outside the range boundary on at least M15/H1. "
        "Beware of liquidity sweeps beyond swing highs/lows without volume expansion."
    ),
    FailureCategory.TIMING_EARLY: (
        "Wait for pullback exhaustion / retest of key levels rather than entering on first impulse. "
        "Confirm lower-timeframe momentum shift (e.g. RSI divergence or rejection wick)."
    ),
    FailureCategory.TIMING_LATE: (
        "Do not chase extended moves when price is > 1.5x ATR away from the dynamic EMA20/50 mean. "
        "Wait for the next structural swing or abort setup."
    ),
    FailureCategory.SL_TOO_TIGHT: (
        "Enforce minimum Stop Loss distance >= 1.2x ATR from entry. "
        "Place SL beyond structural invalidation levels, never arbitrary tight pip distances."
    ),
    FailureCategory.SL_TOO_WIDE: (
        "Recalculate Risk-to-Reward ratio. If required SL distance exceeds 2.5x ATR, reduce position size "
        "or pass on the trade to maintain R:R >= 1.5."
    ),
    FailureCategory.CORRELATION_SHOCK: (
        "Check cross-currency basket exposure and DXY/US Dollar index momentum before committing capital. "
        "Avoid stacking correlated long/short positions across multiple pairs."
    ),
    FailureCategory.NEWS_SPIKE: (
        "Do not enter within 30 minutes before or after high-impact macroeconomic releases (CPI, NFP, FOMC). "
        "Widen SL or cancel pending orders during scheduled release windows."
    ),
    FailureCategory.EXECUTION_SLIPPAGE: (
        "Verify current spread against normal baseline. If spread exceeds 2.0x standard spread, "
        "refrain from market execution and use limit orders."
    ),
    FailureCategory.RISK_MISSIZING: (
        "Enforce strict portfolio heat constraints. In volatile or low-confidence regimes, "
        "cap risk multiplier at <= 0.50."
    ),
    FailureCategory.COUNTER_TREND_BLINDNESS: (
        "Trading against the primary H4/D1 trend requires at least 3 distinct confluence factors "
        "and a confirmed structural market break. Otherwise, enforce trend alignment."
    ),
    FailureCategory.VOLATILITY_UNDERESTIMATION: (
        "When ATR or VIX indicates expanding volatility, widen invalidation zones and reduce lot size "
        "proportionally to maintain invariant dollar risk."
    ),
    FailureCategory.UNGROUNDED_CONFLUENCE: (
        "Require concrete numerical indicators (ATR, EMA, Support/Resistance levels) rather than "
        "qualitative assertions in trade proposals."
    ),
    FailureCategory.UNKNOWN_FAILURE: (
        "Maintain disciplined risk management and strictly adhere to pre-defined invalidation points."
    )
}


@dataclass
class ReasoningFailureRecord:
    symbol: str
    failure_category: FailureCategory
    severity: int = 5  # 1 to 10
    root_cause: str = ""
    preventative_rule: str = ""
    market_regime: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.preventative_rule and self.failure_category in PREVENTATIVE_RULES:
            self.preventative_rule = PREVENTATIVE_RULES[self.failure_category]


class FailureClassifier:
    """Classifies trade failure causes into systematic taxonomy."""

    KEYWORD_MAPPING: Dict[FailureCategory, List[str]] = {
        FailureCategory.REGIME_MISCLASSIFICATION: [
            "regime", "ranging", "chop", "sideways", "trending wrong", "misread regime"
        ],
        FailureCategory.FALSE_BREAKOUT: [
            "fakeout", "false breakout", "bull trap", "bear trap", "liquidity grab", "sweep"
        ],
        FailureCategory.TIMING_EARLY: [
            "premature", "early entry", "too early", "before pullback", "missed pullback"
        ],
        FailureCategory.TIMING_LATE: [
            "chased", "late entry", "fomo", "extended", "overextended"
        ],
        FailureCategory.SL_TOO_TIGHT: [
            "sl too tight", "tight stop", "stopped out prematurely", "spread stopped", "noise"
        ],
        FailureCategory.SL_TOO_WIDE: [
            "sl too wide", "wide stop", "risk too big"
        ],
        FailureCategory.CORRELATION_SHOCK: [
            "correlation", "dxy", "basket", "cross pair", "currency shock"
        ],
        FailureCategory.NEWS_SPIKE: [
            "news", "cpi", "nfp", "fomc", "rate hike", "high impact", "spike"
        ],
        FailureCategory.EXECUTION_SLIPPAGE: [
            "slippage", "spread widening", "bad fill", "requote"
        ],
        FailureCategory.RISK_MISSIZING: [
            "oversized", "too large", "missizing", "multiplier too high"
        ],
        FailureCategory.COUNTER_TREND_BLINDNESS: [
            "counter trend", "against trend", "fought the trend", "htf trend"
        ],
        FailureCategory.VOLATILITY_UNDERESTIMATION: [
            "volatility spike", "vix", "atr expansion", "wild swing"
        ],
        FailureCategory.UNGROUNDED_CONFLUENCE: [
            "ungrounded", "hallucinated", "no real confluence", "weak confluence"
        ]
    }

    @classmethod
    def classify_from_text(cls, text: str) -> FailureCategory:
        """Classify failure mode from post-trade reflection text or lesson tags."""
        if not text:
            return FailureCategory.UNKNOWN_FAILURE

        raw = text.strip().lower()
        try:
            return FailureCategory(raw)
        except ValueError:
            pass

        cleaned = raw.replace("_", " ")
        for category, keywords in cls.KEYWORD_MAPPING.items():
            for kw in keywords:
                if kw in cleaned or kw in raw:
                    return category

        return FailureCategory.UNKNOWN_FAILURE

    @classmethod
    def classify_from_metrics(cls, metrics: Dict[str, Any]) -> FailureCategory:
        """Heuristic rule-based classification from objective trade telemetry."""
        pnl = float(metrics.get("pnl", 0.0))
        if pnl >= 0:
            return FailureCategory.UNKNOWN_FAILURE

        duration_sec = float(metrics.get("duration_seconds", 3600.0))
        spread_at_entry = float(metrics.get("spread_at_entry", 0.0))
        normal_spread = float(metrics.get("normal_spread", 1.0))
        sl_pips = float(metrics.get("sl_pips", 0.0))
        atr_pips = float(metrics.get("atr_pips", 0.0))
        news_distance_min = float(metrics.get("minutes_to_news", 999.0))
        is_counter_trend = bool(metrics.get("is_counter_trend", False))
        mfe_after_exit = float(metrics.get("mfe_after_exit_pips", 0.0))

        # Check 1: News event spike (stopped out within 15m of high impact news)
        if abs(news_distance_min) <= 15.0:
            return FailureCategory.NEWS_SPIKE

        # Check 2: Spread widening / execution slippage
        if normal_spread > 0 and spread_at_entry >= (2.5 * normal_spread):
            return FailureCategory.EXECUTION_SLIPPAGE

        # Check 3: Stop loss too tight (SL was < 0.8x ATR and stopped quickly)
        if atr_pips > 0 and sl_pips > 0 and sl_pips < (0.8 * atr_pips):
            return FailureCategory.SL_TOO_TIGHT

        # Check 4: Timing early (stopped out, but price later went toward original TP)
        if mfe_after_exit > (1.5 * sl_pips) if sl_pips > 0 else False:
            return FailureCategory.TIMING_EARLY

        # Check 5: Counter trend blindness
        if is_counter_trend and duration_sec < 1800:
            return FailureCategory.COUNTER_TREND_BLINDNESS

        return FailureCategory.UNKNOWN_FAILURE


def generate_negative_constraints(
    failures: List[Any],
    symbol: Optional[str] = None,
    current_regime: Optional[str] = None,
    max_constraints: int = 4
) -> List[str]:
    """Generate bulleted negative constraints for LLM prompt context based on historical failures.
    
    Prevents repeated reasoning failure patterns for the target asset and regime.
    """
    if not failures:
        return []

    categories_seen = set()
    constraints = []

    for item in failures:
        cat = None
        if isinstance(item, FailureCategory):
            cat = item
        elif isinstance(item, ReasoningFailureRecord):
            cat = item.failure_category
        elif isinstance(item, str):
            cat = FailureClassifier.classify_from_text(item)

        if cat and cat != FailureCategory.UNKNOWN_FAILURE and cat not in categories_seen:
            rule = PREVENTATIVE_RULES.get(cat)
            if rule:
                categories_seen.add(cat)
                prefix = f"[{cat.value.upper()}]"
                if symbol:
                    constraints.append(f"- {prefix} For {symbol}: {rule}")
                else:
                    constraints.append(f"- {prefix}: {rule}")

        if len(constraints) >= max_constraints:
            break

    return constraints


def get_negative_constraints_for_regime(symbol: str, regime: str, max_rules: int = 3) -> List[str]:
    """Retrieves relevant preventative rules based on market regime and symbol."""
    rules = []
    reg_lower = (regime or "").lower()
    if any(k in reg_lower for k in ("trend", "bull", "bear")):
        rules.extend([FailureCategory.TIMING_EARLY, FailureCategory.TIMING_LATE, FailureCategory.COUNTER_TREND_BLINDNESS])
    elif any(k in reg_lower for k in ("range", "chop")):
        rules.extend([FailureCategory.FALSE_BREAKOUT, FailureCategory.REGIME_MISCLASSIFICATION])
    elif any(k in reg_lower for k in ("volatil", "news")):
        rules.extend([FailureCategory.NEWS_SPIKE, FailureCategory.VOLATILITY_UNDERESTIMATION, FailureCategory.SL_TOO_TIGHT])
    else:
        rules.extend([FailureCategory.SL_TOO_TIGHT, FailureCategory.UNGROUNDED_CONFLUENCE])

    return generate_negative_constraints(rules[:max_rules], symbol=symbol, current_regime=regime, max_constraints=max_rules)
