"""
Benchmark comparison tracker for backtesting.
Calculates institutional benchmark-relative metrics:
Alpha, Beta, Information Ratio, Tracking Error, Up/Down Capture Ratio.
"""
from dataclasses import dataclass, asdict
from typing import Sequence, Dict, Any
import numpy as np


@dataclass
class BenchmarkMetrics:
    benchmark_symbol: str
    strategy_return_ann_pct: float
    benchmark_return_ann_pct: float
    alpha_ann_pct: float
    beta: float
    tracking_error_pct: float
    information_ratio: float
    up_capture_pct: float
    down_capture_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BenchmarkTracker:
    """Tracks and evaluates backtest returns against a buy-and-hold benchmark."""

    def __init__(self, benchmark_symbol: str = "BENCHMARK", ann_factor: float = 252.0):
        self.benchmark_symbol = benchmark_symbol
        self.ann_factor = ann_factor

    def compute_metrics(
        self,
        strategy_returns: Sequence[float],
        benchmark_returns: Sequence[float],
        risk_free_rate: float = 0.0,
    ) -> BenchmarkMetrics:
        """
        Computes benchmark relative metrics given aligned daily returns.
        """
        n = min(len(strategy_returns), len(benchmark_returns))
        if n < 3:
            return BenchmarkMetrics(
                benchmark_symbol=self.benchmark_symbol,
                strategy_return_ann_pct=0.0,
                benchmark_return_ann_pct=0.0,
                alpha_ann_pct=0.0,
                beta=0.0,
                tracking_error_pct=0.0,
                information_ratio=0.0,
                up_capture_pct=0.0,
                down_capture_pct=0.0,
            )

        rs = np.array(strategy_returns[:n], dtype=float)
        rb = np.array(benchmark_returns[:n], dtype=float)

        mean_rs = float(np.mean(rs))
        mean_rb = float(np.mean(rb))
        strat_ann = mean_rs * self.ann_factor * 100.0
        bench_ann = mean_rb * self.ann_factor * 100.0

        var_b = float(np.var(rb, ddof=1))
        cov_sb = float(np.cov(rs, rb)[0, 1]) if var_b > 1e-12 else 0.0

        beta = round(cov_sb / var_b, 3) if var_b > 1e-12 else 1.0

        # Annualized Jensen's Alpha: (R_s - R_f) - beta * (R_b - R_f)
        rf_daily = risk_free_rate / self.ann_factor
        alpha_daily = (mean_rs - rf_daily) - beta * (mean_rb - rf_daily)
        alpha_ann = round(alpha_daily * self.ann_factor * 100.0, 2)

        # Tracking Error: std(rs - rb) * sqrt(ann_factor)
        diff = rs - rb
        te_daily = float(np.std(diff, ddof=1))
        tracking_error = round(te_daily * np.sqrt(self.ann_factor) * 100.0, 2)

        # Information Ratio: (strat_ann - bench_ann) / tracking_error
        info_ratio = round((strat_ann - bench_ann) / tracking_error, 2) if tracking_error > 1e-6 else 0.0

        # Up / Down Capture
        up_mask = rb > 0
        down_mask = rb < 0

        if np.any(up_mask) and np.mean(rb[up_mask]) > 1e-8:
            up_capture = round(float(np.mean(rs[up_mask]) / np.mean(rb[up_mask])) * 100.0, 1)
        else:
            up_capture = 100.0

        if np.any(down_mask) and abs(np.mean(rb[down_mask])) > 1e-8:
            down_capture = round(float(np.mean(rs[down_mask]) / np.mean(rb[down_mask])) * 100.0, 1)
        else:
            down_capture = 100.0

        return BenchmarkMetrics(
            benchmark_symbol=self.benchmark_symbol,
            strategy_return_ann_pct=round(strat_ann, 2),
            benchmark_return_ann_pct=round(bench_ann, 2),
            alpha_ann_pct=alpha_ann,
            beta=beta,
            tracking_error_pct=tracking_error,
            information_ratio=info_ratio,
            up_capture_pct=up_capture,
            down_capture_pct=down_capture,
        )
