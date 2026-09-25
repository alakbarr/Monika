"""
A/B Paired Strategy Evaluation Runner (Phase 5.3).
Executes Baseline vs Candidate strategy configurations across identical historical scenario matrices,
computing Win Rate Lift, Profit Factor Delta, Expectancy Delta, and Token Cost Delta.
"""

from dataclasses import dataclass, asdict
import inspect
import logging
import math
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("TradingAgent.PairedEvaluator")


def _t_distribution_p_value(t: float, df: int) -> float:
    """Pure-Python Student's t two-tailed p-value using regularized incomplete beta function."""
    if df <= 0 or not math.isfinite(t):
        return 1.0
    t2 = t * t
    x = df / (df + t2)
    a = 0.5 * df
    b = 0.5

    def betacf(a, b, x):
        MAXIT = 100
        EPS = 3e-7
        FPMIN = 1e-30
        qab = a + b
        qap = a + 1.0
        qam = a - 1.0
        c = 1.0
        d = 1.0 - qab * x / qap
        if abs(d) < FPMIN:
            d = FPMIN
        d = 1.0 / d
        h = d
        for m in range(1, MAXIT + 1):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1.0 + aa * d
            if abs(d) < FPMIN:
                d = FPMIN
            c = 1.0 + aa / c
            if abs(c) < FPMIN:
                c = FPMIN
            d = 1.0 / d
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1.0 + aa * d
            if abs(d) < FPMIN:
                d = FPMIN
            c = 1.0 + aa / c
            if abs(c) < FPMIN:
                c = FPMIN
            d = 1.0 / d
            del_val = d * c
            h *= del_val
            if abs(del_val - 1.0) < EPS:
                break
        return h

    if x <= 0.0:
        return 1.0
    if x >= 1.0:
        return 0.0

    try:
        bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    except (ValueError, OverflowError):
        bt = 0.0

    if x < (a + 1.0) / (a + b + 2.0):
        betai = bt * betacf(a, b, x) / a
    else:
        betai = 1.0 - bt * betacf(b, a, 1.0 - x) / b
    return min(1.0, max(0.0, float(betai)))


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
    p_value: float = 1.0
    is_statistically_significant: bool = False

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

        # Compute paired statistical significance across scenarios using Student's t-test
        p_val = 1.0
        is_sig = False
        if len(scenarios) >= 3 and len(baseline_trades) == len(candidate_trades) == len(scenarios):
            diffs = []
            for b_t, c_t in zip(baseline_trades, candidate_trades):
                b_pnl = float(b_t.get("pnl", b_t.get("profit", 0.0)))
                c_pnl = float(c_t.get("pnl", c_t.get("profit", 0.0)))
                diffs.append(c_pnl - b_pnl)

            n = len(diffs)
            mean_diff = sum(diffs) / n
            var_diff = sum((d - mean_diff) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
            std_diff = var_diff ** 0.5
            if std_diff > 1e-8:
                t_stat = mean_diff / (std_diff / (n ** 0.5))
                p_val = round(_t_distribution_p_value(abs(t_stat), df=n - 1), 4)
                is_sig = bool(p_val < 0.05 and mean_diff > 0)

        return PairedComparisonReport(
            baseline=b_metrics,
            candidate=c_metrics,
            win_rate_lift_pct=win_lift,
            profit_factor_delta=pf_delta,
            expectancy_delta=exp_delta,
            token_cost_delta_usd=cost_delta,
            is_candidate_superior=is_superior,
            p_value=p_val,
            is_statistically_significant=is_sig,
        )

    async def evaluate_pairwise_async(
        self,
        baseline_fn: Callable[[Dict[str, Any]], Any],
        candidate_fn: Callable[[Dict[str, Any]], Any],
        scenarios: List[Dict[str, Any]],
        baseline_name: str = "Baseline",
        candidate_name: str = "Candidate",
    ) -> PairedComparisonReport:
        """Asynchronous execution for native async strategy functions."""
        baseline_trades = []
        candidate_trades = []
        b_tokens = {"total_tokens": 0, "cost_usd": 0.0}
        c_tokens = {"total_tokens": 0, "cost_usd": 0.0}

        for scenario in scenarios:
            b_res = baseline_fn(scenario)
            b_out = (await b_res) if inspect.isawaitable(b_res) else b_res
            b_out = b_out or {}
            if "trade" in b_out:
                baseline_trades.append(b_out["trade"])
            elif "pnl" in b_out:
                baseline_trades.append(b_out)
            b_tokens["total_tokens"] += b_out.get("tokens", 0)
            b_tokens["cost_usd"] += b_out.get("cost_usd", 0.0)

            c_res = candidate_fn(scenario)
            c_out = (await c_res) if inspect.isawaitable(c_res) else c_res
            c_out = c_out or {}
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

        p_val = 1.0
        is_sig = False
        if len(scenarios) >= 3 and len(baseline_trades) == len(candidate_trades) == len(scenarios):
            diffs = []
            for b_t, c_t in zip(baseline_trades, candidate_trades):
                b_pnl = float(b_t.get("pnl", b_t.get("profit", 0.0)))
                c_pnl = float(c_t.get("pnl", c_t.get("profit", 0.0)))
                diffs.append(c_pnl - b_pnl)

            n = len(diffs)
            mean_diff = sum(diffs) / n
            var_diff = sum((d - mean_diff) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
            std_diff = var_diff ** 0.5
            if std_diff > 1e-8:
                t_stat = mean_diff / (std_diff / (n ** 0.5))
                p_val = round(_t_distribution_p_value(abs(t_stat), df=n - 1), 4)
                is_sig = bool(p_val < 0.05 and mean_diff > 0)

        return PairedComparisonReport(
            baseline=b_metrics,
            candidate=c_metrics,
            win_rate_lift_pct=win_lift,
            profit_factor_delta=pf_delta,
            expectancy_delta=exp_delta,
            token_cost_delta_usd=cost_delta,
            is_candidate_superior=is_superior,
            p_value=p_val,
            is_statistically_significant=is_sig,
        )
