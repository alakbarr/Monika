# ==============================================================================
# File: backtest/monte_carlo_engine.py
# ==============================================================================

"""
Institutional Monte Carlo Stress Tester & Scenario Shock Engine.
Menyediakan simulasi bootstrap permutasi trade, stress-test lonjakan slippage & spread,
analisis klaster drawdown, serta estimasi probabilitas kebangkrutan (Probability of Ruin).
"""

from typing import Any, Dict, List, Optional

import numpy as np


class MonteCarloStressTester:
    """Engine pengujian ketahanan statistik tingkat institusional."""

    def __init__(self, seed: Optional[int] = 42):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def simulate_trade_sequence(
        self,
        trade_returns: List[float],
        num_simulations: int = 1000,
        initial_equity: float = 10000.0,
        ruin_drawdown_pct: float = 0.50,
        mode: str = "permutation",
    ) -> Dict[str, Any]:
        """
        Melakukan simulasi Monte Carlo berbasis permutasi urutan (tanpa pengembalian)
        atau bootstrap resampling (dengan pengembalian) untuk menguji Maximum Drawdown
        dan distribusi ekuitas akhir.
        """
        if not trade_returns or len(trade_returns) < 5:
            return {
                "is_valid": False,
                "num_simulations": 0,
                "var_95_drawdown_pct": 0.0,
                "var_99_drawdown_pct": 0.0,
                "max_simulated_dd_pct": 0.0,
                "median_drawdown_pct": 0.0,
                "ruin_probability_pct": 0.0,
                "percentiles": {},
                "final_equity_distribution": {
                    "p5": initial_equity,
                    "median_p50": initial_equity,
                    "p95": initial_equity,
                },
            }

        if self.seed is not None:
            self.rng = np.random.default_rng(self.seed)

        # Normalize ruin_drawdown_pct if passed as percentage (e.g. 50.0 -> 0.50)
        if ruin_drawdown_pct > 1.0:
            ruin_drawdown_pct = ruin_drawdown_pct / 100.0

        returns_arr = np.array(trade_returns, dtype=float)
        ruin_barrier = initial_equity * (1.0 - ruin_drawdown_pct)
        use_replacement = mode.lower() == "bootstrap"
        is_block = mode.lower() in ("block_bootstrap", "cbb")
        n = len(returns_arr)
        block_size = max(2, int(np.sqrt(n))) if is_block else 1

        if is_block:
            n_blocks = (n + block_size - 1) // block_size
            starts = self.rng.integers(0, n, size=(num_simulations, n_blocks))
            offsets = np.arange(block_size)
            idx_mat = ((starts[:, :, None] + offsets) % n).reshape(num_simulations, -1)[:, :n]
            sampled_matrix = returns_arr[idx_mat]
        elif use_replacement:
            sampled_matrix = self.rng.choice(returns_arr, size=(num_simulations, n), replace=True)
        else:
            sampled_matrix = self.rng.permuted(np.broadcast_to(returns_arr, (num_simulations, n)), axis=1)

        from monika.core.native.rust_bridge import eval_equity_paths_f64

        fast_res = eval_equity_paths_f64(sampled_matrix, float(initial_equity), float(ruin_drawdown_pct))
        if fast_res is not None:
            simulated_max_dds, final_equities, ruin_count = fast_res
        else:
            mult_matrix = np.maximum(0.0, 1.0 + sampled_matrix)
            equity_curves = initial_equity * np.cumprod(mult_matrix, axis=1)
            init_col = np.full((num_simulations, 1), initial_equity, dtype=np.float64)
            full_curves = np.hstack([init_col, equity_curves])
            final_equities = full_curves[:, -1]

            running_max = np.maximum.accumulate(full_curves, axis=1)
            drawdowns = (running_max - full_curves) / running_max
            max_sim_dds = np.max(drawdowns, axis=1)
            simulated_max_dds = max_sim_dds * 100.0

            min_equities = np.min(full_curves, axis=1)
            ruin_mask = (max_sim_dds >= ruin_drawdown_pct) | (min_equities < ruin_barrier)
            ruin_count = int(np.sum(ruin_mask))

        simulated_max_dds = np.sort(simulated_max_dds)
        final_equities = np.sort(final_equities)

        p5_dd = np.percentile(simulated_max_dds, 5)
        p50_dd = np.percentile(simulated_max_dds, 50)
        p95_dd = np.percentile(simulated_max_dds, 95)
        p99_dd = np.percentile(simulated_max_dds, 99)
        max_dd = simulated_max_dds[-1]

        ruin_prob = (ruin_count / num_simulations) * 100.0

        return {
            "is_valid": True,
            "num_simulations": num_simulations,
            "var_95_drawdown_pct": round(float(p95_dd), 2),
            "var_99_drawdown_pct": round(float(p99_dd), 2),
            "median_drawdown_pct": round(float(p50_dd), 2),
            "max_simulated_dd_pct": round(float(max_dd), 2),
            "ruin_probability_pct": round(ruin_prob, 2),
            "final_equity_distribution": {
                "p5": round(float(np.percentile(final_equities, 5)), 2),
                "median_p50": round(float(np.percentile(final_equities, 50)), 2),
                "p95": round(float(np.percentile(final_equities, 95)), 2),
            },
        }

    def run_slippage_spread_shock_test(
        self,
        trade_returns: List[float],
        slippage_multipliers: Optional[List[float]] = None,
        base_friction_pct: float = 0.0003,  # 3 pips/bps
        num_simulations: int = 2000,
        initial_equity: float = 10000.0,
    ) -> Dict[str, Dict[str, float]]:
        """
        Menguji ketahanan strategi terhadap lonjakan slippage dan pelebaran spread.
        """
        mults = slippage_multipliers if slippage_multipliers is not None else [1.0, 2.0, 3.0, 5.0]
        returns_arr = np.array(trade_returns, dtype=float)
        results = {}

        for mult in mults:
            penalty = base_friction_pct * (mult - 1.0)
            shocked_returns = returns_arr - penalty

            res = self.run_permutation_drawdown_test(
                trade_returns=shocked_returns.tolist(), num_simulations=num_simulations, initial_equity=initial_equity
            )
            key = f"shock_{int(mult)}x_slippage"
            results[key] = {
                "var_95_drawdown_pct": res.get("var_95_drawdown_pct", 0.0),
                "var_99_drawdown_pct": res.get("var_99_drawdown_pct", 0.0),
                "ruin_probability_pct": res.get("ruin_probability_pct", 0.0),
                "median_final_equity": res.get("final_equity_distribution", {}).get("median_p50", initial_equity),
            }

        return results

    # Backward-compatible alias
    run_permutation_drawdown_test = simulate_trade_sequence
