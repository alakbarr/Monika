# ==============================================================================
# File: indicators/pattern_similarity/models.py
# ==============================================================================

"""
Data models and dataclasses for multi-timeframe pattern similarity screening.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


@dataclass
class PatternMatch:
    """Represents a matched historical pattern segment."""
    start_index: int
    end_index: int
    similarity: float           # 0.0 - 1.0 (shape similarity)
    start_time: float           # Unix epoch timestamp
    end_time: float             # Unix epoch timestamp
    method: str = "euclidean"
    # Context metrics
    context_score: float = 0.5  # 0.0 - 1.0 (macro context match)
    context_coverage: float = 1.0  # Proportion of context dimensions available (0.0-1.0)
    context_label: str = "UNKNOWN" # HIGH, MEDIUM, LOW, UNVERIFIED
    # Cross-symbol metrics
    is_cross_symbol: bool = False
    source_symbol: str = ""
    weight: float = 1.0         # 1.0 for same-symbol, 0.5 for cross-symbol


@dataclass
class MarketContext:
    """Snapshot of macroeconomic and market environment at a specific point in time."""
    vix_level: float
    vix_category: str           # low, normal, elevated, crisis
    dxy_trend: str              # bullish, bearish, flat, unknown
    market_regime: str          # trend, range, volatile_chop, squeeze
    rate_cycle: str             # hiking, cutting, pause, neutral, unknown
    asset_trend: str            # above_ema200, below_ema200, neutral
    data_sources: Dict[str, str] = field(default_factory=dict)

    def to_summary(self) -> str:
        return (
            f"VIX: {self.vix_level:.1f} ({self.vix_category}), "
            f"DXY Trend: {self.dxy_trend}, "
            f"Regime: {self.market_regime}, "
            f"Rate Cycle: {self.rate_cycle}, "
            f"Asset Trend: {self.asset_trend}"
        )


@dataclass
class ContextAnnotation:
    """Historical narrative annotation for a match date."""
    match: PatternMatch
    chronicle_events: List[str] = field(default_factory=list)
    calendar_events: List[str] = field(default_factory=list)
    context_label: str = "UNKNOWN"
    context_score: float = 0.5


@dataclass
class ContextVerdict:
    """Verdict from LLM deep verification of pattern context."""
    match: PatternMatch
    relevance: str              # high, medium, low
    reason: str
    adjustment_factor: float    # 0.0 - 1.0


@dataclass
class PatternOutcome:
    """Forward price trajectory after a matched historical pattern."""
    match: PatternMatch
    forward_returns: Dict[str, float]  # horizon -> return in ATR units
    mfe_atr: float                     # Max Favorable Excursion (in ATR units)
    mae_atr: float                     # Max Adverse Excursion (in ATR units)
    direction: str                     # bullish, bearish, neutral
    entry_price: float
    atr_at_entry: float


@dataclass
class OutcomeStatistics:
    """Aggregated statistical outcome across multiple historical matches."""
    is_significant: bool = False
    match_count: int = 0
    bullish_pct: float = 0.5
    bearish_pct: float = 0.5
    neutral_pct: float = 0.0
    avg_return_1d_atr: float = 0.0
    std_return_1d_atr: float = 0.0
    median_return_1d_atr: float = 0.0
    avg_mfe_atr: float = 0.0
    avg_mae_atr: float = 0.0
    implied_rr: float = 0.0
    win_rate_1r: float = 0.0
    win_rate_2r: float = 0.0
    win_rate_3r: float = 0.0
    p_value: float = 1.0
    directional_bias: str = "neutral"
    reason: str = ""


@dataclass
class SingleTimeframeResult:
    """Screening outcome for one specific timeframe."""
    timeframe: str
    statistics: OutcomeStatistics
    top_matches: List[PatternMatch] = field(default_factory=list)
    avg_similarity: float = 0.0
    cross_symbol_matches: List[PatternMatch] = field(default_factory=list)

    @property
    def match_count(self) -> int:
        return self.statistics.match_count

    def add_cross_symbol_matches(self, matches: List[PatternMatch]) -> None:
        self.cross_symbol_matches.extend(matches)

    @classmethod
    def empty(cls, timeframe: str) -> "SingleTimeframeResult":
        return cls(
            timeframe=timeframe,
            statistics=OutcomeStatistics(is_significant=False, reason="no_data"),
            top_matches=[],
            avg_similarity=0.0,
        )


@dataclass
class MultiTimeframeScreeningResult:
    """Comprehensive multi-timeframe pattern similarity screening consensus."""
    symbol: str
    overall_bias: str                  # bullish, bearish, neutral
    confidence: str                    # high, medium, low, none
    consensus_bullish_pct: float
    consensus_bearish_pct: float
    has_timeframe_conflict: bool
    significant_timeframes: List[str]
    per_timeframe: Dict[str, SingleTimeframeResult]
    screening_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context_verdicts: List[ContextVerdict] = field(default_factory=list)

    def has_significant_results(self) -> bool:
        return len(self.significant_timeframes) > 0

    def get_top_matches_across_timeframes(self, limit: int = 3) -> List[tuple[PatternMatch, str]]:
        candidates = []
        for tf, res in self.per_timeframe.items():
            for m in res.top_matches:
                candidates.append((m, tf))
        candidates.sort(key=lambda x: x[0].similarity, reverse=True)
        return candidates[:limit]

    @classmethod
    def empty(cls, symbol: str) -> "MultiTimeframeScreeningResult":
        return cls(
            symbol=symbol,
            overall_bias="neutral",
            confidence="none",
            consensus_bullish_pct=0.5,
            consensus_bearish_pct=0.5,
            has_timeframe_conflict=False,
            significant_timeframes=[],
            per_timeframe={},
            screening_timestamp=datetime.now(timezone.utc),
        )

    def format_for_prompt(self) -> str:
        """Format screening output as tight markdown for LLM prompt injection."""
        lines = ["### Historical Pattern Similarity (Multi-Timeframe)\n"]

        for tf in ["D1", "H4", "H1"]:
            if tf not in self.per_timeframe:
                continue
            res = self.per_timeframe[tf]
            stats = res.statistics
            if stats.match_count == 0:
                continue

            lines.append(
                f"**{tf} ({stats.match_count} matches, "
                f"avg sim: {res.avg_similarity:.1%})**"
            )

            if stats.is_significant:
                lines.append(
                    f"- Directional bias: {stats.directional_bias.upper()} "
                    f"({stats.bullish_pct:.0%} bull vs {stats.bearish_pct:.0%} bear, p={stats.p_value:.3f})"
                )
                lines.append(
                    f"- Avg 1d return: {stats.avg_return_1d_atr:+.2f} ATR | "
                    f"MFE: {stats.avg_mfe_atr:+.1f} ATR | MAE: {stats.avg_mae_atr:+.1f} ATR | "
                    f"Implied R:R: {stats.implied_rr:.1f}"
                )
                lines.append(
                    f"- Win rate: 1R={stats.win_rate_1r:.0%}, 2R={stats.win_rate_2r:.0%}, 3R={stats.win_rate_3r:.0%}"
                )
            else:
                lines.append(f"- Directional sample not statistically significant (p={stats.p_value:.2f})")

            # Top matches list
            if res.top_matches:
                lines.append("| Date | Sim | Context | Source |")
                lines.append("|---|---|---|---|")
                for m in res.top_matches[:3]:
                    dt_str = datetime.fromtimestamp(m.end_time, tz=timezone.utc).strftime("%Y-%m-%d")
                    src = f"{m.source_symbol} (0.5x)" if m.is_cross_symbol else "Same-Asset"
                    lines.append(f"| {dt_str} | {m.similarity:.1%} | {m.context_label} | {src} |")
            lines.append("")

        if self.context_verdicts:
            lines.append("**Top Matches Macro Context Verdicts:**")
            for v in self.context_verdicts:
                dt_str = datetime.fromtimestamp(v.match.end_time, tz=timezone.utc).strftime("%Y-%m-%d")
                lines.append(f"- **{dt_str}** [{v.relevance.upper()}]: {v.reason}")
            lines.append("")

        lines.append(
            f"**Multi-TF Consensus: {self.overall_bias.upper()} "
            f"(Confidence: {self.confidence.upper()}, "
            f"Significant TFs: {', '.join(self.significant_timeframes) if self.significant_timeframes else 'None'})**"
        )
        return "\n".join(lines).strip()
