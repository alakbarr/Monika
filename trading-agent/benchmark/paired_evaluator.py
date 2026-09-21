"""
A/B Paired Strategy Evaluation Runner (Phase 5.3).
Executes Baseline vs Candidate strategy configurations across identical historical scenario matrices,
computing Win Rate Lift, Profit Factor Delta, Expectancy Delta, and Token Cost Delta.
"""

from dataclasses import dataclass, field, asdict
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("TradingAgent.PairedEvaluator")


@dataclass
class StrategyMetrics:
    strategy_name: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PairedComparisonReport:
    baseline: StrategyMetrics
    candidate: StrategyMetrics
    win_rate_lift_pct: float
    profit_factor_delta: float
    expectancy_delta: float
    token_cost_delta_usd: float
    is_candidate_superior: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PairedStrategyEvaluator:
    """Runs statistical pairwise evaluation between baseline and candidate strategies."""

    @staticmethod
    def _compute_metrics(name: str, trades: List[Dict[str, Any]], token_usage: Optional[Dict[str, Any]] = None) -> StrategyMetrics:
        """Calculate quantitative performance metrics for a trade set."""
        m = StrategyMetrics(strategy_name=name)
        m.total_trades = len(trades)
        if not trades:
            return m

        profits = []
        losses = []
        for t in trades:
            pnl = float(t.get("pnl", t.get("profit", 0.0)))
            if pnl > 0:
                m.winning_trades += 1
                profits.append(pnl)
            elif pnl < 0:
                m.losing_trades += 1
                losses.append(abs(pnl))

        m.win_rate = round((m.winning_trades / m.total_trades) * 100.0, 2)
        m.gross_profit = sum(profits)
        m.gross_loss = sum(losses)
        m.profit_factor = round(m.gross_profit / m.gross_loss, 3) if m.gross_loss > 0 else (99.0 if m.gross_profit > 0 else 0.0)

        avg_win = (m.gross_profit / m.winning_trades) if m.winning_trades > 0 else 0.0
        avg_loss = (m.gross_loss / m.losing_trades) if m.losing_trades > 0 else 0.0
        p_win = m.winning_trades / m.total_trades
        p_loss = m.losing_trades / m.total_trades
        m.expectancy = round((p_win * avg_win) - (p_loss * avg_loss), 2)

        if token_usage:
            m.total_tokens = int(token_usage.get("total_tokens", 0))
            m.total_cost_usd = float(token_usage.get("cost_usd", 0.0))

        return m

    def evaluate_pairwise(
        self,
        baseline_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        candidate_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        scenarios: List[Dict[str, Any]],
        baseline_name: str = "Baseline",
        candidate_name: str = "Candidate",
    ) -> PairedComparisonReport:
        """Run identical scenarios through both functions and compute lift deltas."""
        baseline_trades = []
        candidate_trades = []
        b_tokens = {"total_tokens": 0, "cost_usd": 0.0}
        c_tokens = {"total_tokens": 0, "cost_usd": 0.0}

        for scenario in scenarios:
            # Execute baseline
            b_out = baseline_fn(scenario) or {}
            if "trade" in b_out:
                baseline_trades.append(b_out["trade"])
            elif "pnl" in b_out:
                baseline_trades.append(b_out)
            b_tokens["total_tokens"] += b_out.get("tokens", 0)
            b_tokens["cost_usd"] += b_out.get("cost_usd", 0.0)

            # Execute candidate
            c_out = candidate_fn(scenario) or {}
            if "trade" in c_out:
                candidate_trades.append(c_out["trade"])
            elif "pnl" in c_out:
                candidate_trades.append(c_out)
            c_tokens["total_tokens"] += c_out.get("tokens", 0)
            c_tokens["cost_usd"] += c_out.get("cost_usd", 0.0)

        b_metrics = self._compute_metrics(baseline_name, baseline_trades, b_tokens)
        c_metrics = self._compute_metrics(candidate_name, candidate_trades, c_tokens)

        win_lift = round(c_metrics.win_rate - b_metrics.win_rate, 2)
        pf_delta = round(c_metrics.profit_factor - b_metrics.profit_factor, 3)
        exp_delta = round(c_metrics.expectancy - b_metrics.expectancy, 2)
        cost_delta = round(c_metrics.total_cost_usd - b_metrics.total_cost_usd, 6)

        is_superior = (
            (c_metrics.win_rate >= b_metrics.win_rate)
            and (c_metrics.expectancy >= b_metrics.expectancy)
            and (c_metrics.profit_factor >= b_metrics.profit_factor)
        )

        return PairedComparisonReport(
            baseline=b_metrics,
            candidate=c_metrics,
            win_rate_lift_pct=win_lift,
            profit_factor_delta=pf_delta,
            expectancy_delta=exp_delta,
            token_cost_delta_usd=cost_delta,
            is_candidate_superior=is_superior,
        )
