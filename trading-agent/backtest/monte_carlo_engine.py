# ==============================================================================
# File: backtest/monte_carlo_engine.py
# ==============================================================================

"""
Institutional Monte Carlo Stress Tester & Scenario Shock Engine.
Menyediakan simulasi bootstrap permutasi trade, stress-test lonjakan slippage & spread,
analisis klaster drawdown, serta estimasi probabilitas kebangkrutan (Probability of Ruin).
"""

import numpy as np
from typing import List, Dict, Any, Optional

class MonteCarloStressTester:
    """Engine pengujian ketahanan statistik tingkat institusional."""

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def simulate_trade_sequence(
        self,
        trade_returns: List[float],
        num_simulations: int = 1000,
        initial_equity: float = 10000.0,
        ruin_drawdown_pct: float = 0.50,
        mode: str = "permutation"
    ) -> Dict[str, Any]:
        """
        Melakukan simulasi Monte Carlo berbasis permutasi urutan (tanpa pengembalian)
        atau bootstrap resampling (dengan pengembalian) untuk menguji Maximum Drawdown
        dan distribusi ekuitas akhir.
        """
        if not trade_returns or len(trade_returns) < 5:
            return {
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

        returns_arr = np.array(trade_returns, dtype=float)
        simulated_max_dds = []
        final_equities = []

        ruin_barrier = initial_equity * (1.0 - ruin_drawdown_pct)
        ruin_count = 0
        use_replacement = (mode.lower() == "bootstrap")
        is_block = mode.lower() in ("block_bootstrap", "cbb")
        n = len(returns_arr)
        block_size = max(2, int(np.sqrt(n))) if is_block else 1

        for _ in range(num_simulations):
            if is_block:
                # Circular Block Bootstrap (Politis & Romano 1994) to preserve dependency structures
                sampled_list = []
                while len(sampled_list) < n:
                    start_idx = self.rng.integers(0, n)
                    indices = [(start_idx + i) % n for i in range(block_size)]
                    sampled_list.extend(returns_arr[indices])
                sampled = np.array(sampled_list[:n])
            else:
                # Permutation (replace=False) atau Bootstrap (replace=True)
                sampled = self.rng.choice(returns_arr, size=n, replace=use_replacement)

            # Hitung kurva ekuitas dengan t=0 initial equity, clamp ke 0.0 untuk proteksi ruin
            equity_curve = initial_equity * np.cumprod(np.maximum(0.0, 1.0 + sampled))
            full_curve = np.insert(equity_curve, 0, initial_equity)
            final_equities.append(float(full_curve[-1]))
            
            # Hitung drawdown
            running_max = np.maximum.accumulate(full_curve)
            drawdowns = (running_max - full_curve) / running_max
            max_sim_dd = float(np.max(drawdowns))
            simulated_max_dds.append(max_sim_dd * 100.0)

            # Path ruin check (ruin if drawdown from peak exceeds ruin_drawdown_pct or equity breaches initial barrier)
            if max_sim_dd >= ruin_drawdown_pct or np.min(full_curve) < ruin_barrier:
                ruin_count += 1

        simulated_max_dds.sort()
        final_equities.sort()

        p5_dd = np.percentile(simulated_max_dds, 5)
        p50_dd = np.percentile(simulated_max_dds, 50)
        p95_dd = np.percentile(simulated_max_dds, 95)
        p99_dd = np.percentile(simulated_max_dds, 99)
        max_dd = simulated_max_dds[-1]

        ruin_prob = (ruin_count / num_simulations) * 100.0

        return {
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
            }
        }

    def run_slippage_spread_shock_test(
        self,
        trade_returns: List[float],
        slippage_multipliers: List[float] = [1.0, 2.0, 3.0, 5.0],
        base_friction_pct: float = 0.0003,  # 3 pips/bps
        num_simulations: int = 2000,
        initial_equity: float = 10000.0
    ) -> Dict[str, Dict[str, float]]:
        """
        Menguji ketahanan strategi terhadap lonjakan slippage dan pelebaran spread.
        """
        returns_arr = np.array(trade_returns, dtype=float)
        results = {}

        for mult in slippage_multipliers:
            penalty = base_friction_pct * (mult - 1.0)
            shocked_returns = returns_arr - penalty
            
            res = self.run_permutation_drawdown_test(
                trade_returns=shocked_returns.tolist(),
                num_simulations=num_simulations,
                initial_equity=initial_equity
            )
            key = f"shock_{int(mult)}x_slippage"
            results[key] = {
                "var_95_drawdown_pct": res.get("var_95_drawdown_pct", 0.0),
                "var_99_drawdown_pct": res.get("var_99_drawdown_pct", 0.0),
                "ruin_probability_pct": res.get("ruin_probability_pct", 0.0),
                "median_final_equity": res.get("final_equity_distribution", {}).get("median_p50", initial_equity)
            }

        return results

    # Backward-compatible alias
    run_permutation_drawdown_test = simulate_trade_sequence
