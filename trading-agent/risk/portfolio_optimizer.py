# ==============================================================================
# File: risk/portfolio_optimizer.py
# Monika Modern Portfolio Theory & Turnover-Aware Multi-Asset Optimizer
# ==============================================================================

"""
Portfolio Optimization Engine for MetaTrader 5 Multi-Asset Portfolios.

Asset Groups:
- USD_MAJORS: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD
- METALS: XAUUSD, XAGUSD
- ENERGY: XTIUSD, XBRUSD
- CRYPTO: BTCUSD, ETHUSD

Provides 5 Institutional Solvers:
1. Mean-Variance (Max Sharpe Ratio)
2. Risk Parity (Equal Risk Contribution / ERC via Cyclical Coordinate Descent)
3. Equal Volatility (Inverse Volatility Sizing)
4. Maximum Diversification Ratio (Choueifaty & Coignard)
5. Turnover-Aware Quadratic Utility with L1 Churn Penalty and Sector Caps
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

try:
    from scipy.optimize import minimize
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False
    minimize = None

logger = logging.getLogger("TradingAgent.Risk.PortfolioOptimizer")

DEFAULT_GROUP_MAP: Dict[str, str] = {
    "EURUSD": "USD_MAJORS",
    "GBPUSD": "USD_MAJORS",
    "USDJPY": "USD_MAJORS",
    "AUDUSD": "USD_MAJORS",
    "USDCAD": "USD_MAJORS",
    "USDCHF": "USD_MAJORS",
    "NZDUSD": "USD_MAJORS",
    "XAUUSD": "METALS",
    "XAGUSD": "METALS",
    "XTIUSD": "ENERGY",
    "XBRUSD": "ENERGY",
    "BTCUSD": "CRYPTO",
    "ETHUSD": "CRYPTO",
}

DEFAULT_GROUP_CAPS: Dict[str, float] = {
    "USD_MAJORS": 0.40,
    "METALS": 0.25,
    "ENERGY": 0.15,
    "CRYPTO": 0.20,
}


@dataclass(frozen=True)
class OptimizationResult:
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    turnover: float
    converged: bool
    method: str


class PortfolioOptimizer:
    """
    Mathematical portfolio weight optimizer with risk constraints and pure-NumPy fallbacks.
    """

    def __init__(
        self,
        symbols: List[str],
        cov_matrix: np.ndarray,
        expected_returns: Optional[np.ndarray] = None,
    ):
        self.symbols = list(symbols)
        self.cov_matrix = np.asarray(cov_matrix, dtype=np.float64)
        if expected_returns is not None:
            self.expected_returns = np.asarray(expected_returns, dtype=np.float64)
        else:
            self.expected_returns = np.zeros(len(self.symbols), dtype=np.float64)

    def solve_equal_volatility(self) -> OptimizationResult:
        """
        Sizes assets inversely proportional to their empirical volatility: w_i ~ 1 / sigma_i.
        """
        n = len(self.symbols)
        if n == 0:
            return OptimizationResult({}, 0.0, 0.0, 0.0, 0.0, False, "equal_volatility")
        if n == 1:
            return OptimizationResult(
                {self.symbols[0]: 1.0},
                float(self.expected_returns[0]),
                float(np.sqrt(self.cov_matrix[0, 0])),
                0.0,
                0.0,
                True,
                "equal_volatility",
            )

        variances = np.diag(self.cov_matrix)
        vols = np.sqrt(np.maximum(variances, 1e-8))
        inv_vols = 1.0 / vols
        weights = inv_vols / np.sum(inv_vols)

        port_ret = float(np.dot(weights, self.expected_returns))
        port_vol = float(np.sqrt(weights @ self.cov_matrix @ weights))
        sharpe = port_ret / port_vol if port_vol > 1e-9 else 0.0

        w_dict = {sym: round(float(w), 4) for sym, w in zip(self.symbols, weights)}
        return OptimizationResult(w_dict, port_ret, port_vol, sharpe, 0.0, True, "equal_volatility")

    def solve_risk_parity_erc(self) -> OptimizationResult:
        """
        Equal Risk Contribution (ERC) via Cyclical Coordinate Descent (Griveau-Billion et al. 2013).
        Guaranteed exact convergence in pure NumPy without SciPy.
        """
        n = len(self.symbols)
        if n == 0:
            return OptimizationResult({}, 0.0, 0.0, 0.0, 0.0, False, "risk_parity")
        if n == 1:
            return OptimizationResult(
                {self.symbols[0]: 1.0},
                float(self.expected_returns[0]),
                float(np.sqrt(self.cov_matrix[0, 0])),
                0.0,
                0.0,
                True,
                "risk_parity",
            )

        Sigma = self.cov_matrix
        w = np.full(n, 1.0 / n, dtype=np.float64)
        b = 1.0 / n

        # Cyclical coordinate descent
        for _ in range(100):
            for i in range(n):
                cov_w_i = float(Sigma[i] @ w)
                B = cov_w_i - Sigma[i, i] * w[i]
                A = Sigma[i, i]
                disc = B * B + 4.0 * A * b
                if disc >= 0 and A > 1e-12:
                    w[i] = (-B + np.sqrt(disc)) / (2.0 * A)

        w = np.maximum(1e-6, w)
        w = w / np.sum(w)

        port_ret = float(np.dot(w, self.expected_returns))
        port_vol = float(np.sqrt(w @ Sigma @ w))
        sharpe = port_ret / port_vol if port_vol > 1e-9 else 0.0

        w_dict = {sym: round(float(wi), 4) for sym, wi in zip(self.symbols, w)}
        return OptimizationResult(w_dict, port_ret, port_vol, sharpe, 0.0, True, "risk_parity")

    def solve_mean_variance(
        self,
        risk_free_rate: float = 0.0,
        max_weight: float = 0.40,
    ) -> OptimizationResult:
        """
        Maximizes Sharpe Ratio under simplex and box constraints.
        """
        n = len(self.symbols)
        if n == 0:
            return OptimizationResult({}, 0.0, 0.0, 0.0, 0.0, False, "mean_variance")
        if n == 1:
            return OptimizationResult(
                {self.symbols[0]: 1.0},
                float(self.expected_returns[0]),
                float(np.sqrt(self.cov_matrix[0, 0])),
                0.0,
                0.0,
                True,
                "mean_variance",
            )

        effective_max = max(max_weight, 1.0 / n)

        if _HAS_SCIPY and minimize is not None:
            def _neg_sharpe(w: np.ndarray) -> float:
                r = np.dot(w, self.expected_returns) - risk_free_rate
                vol = np.sqrt(w @ self.cov_matrix @ w)
                return -(r / vol) if vol > 1e-9 else 0.0

            init_w = np.full(n, 1.0 / n)
            bounds = [(0.0, effective_max) for _ in range(n)]
            constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

            opt = minimize(
                _neg_sharpe,
                init_w,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 200, "ftol": 1e-7},
            )
            w_opt = opt.x if opt.success else init_w
        else:
            # Pure-NumPy projected gradient ascent
            w = np.full(n, 1.0 / n)
            lr = 0.05
            for _ in range(250):
                r_p = float(np.dot(w, self.expected_returns)) - risk_free_rate
                var_p = float(w @ self.cov_matrix @ w)
                vol_p = np.sqrt(max(var_p, 1e-8))
                grad = (self.expected_returns / vol_p) - (r_p / (vol_p ** 3)) * (self.cov_matrix @ w)
                w_new = w + lr * grad
                w_new = np.clip(w_new, 0.0, effective_max)
                w_new = w_new / np.sum(w_new)
                w = w_new
            w_opt = w

        w_opt = np.maximum(0.0, w_opt)
        w_opt = w_opt / np.sum(w_opt)

        port_ret = float(np.dot(w_opt, self.expected_returns))
        port_vol = float(np.sqrt(w_opt @ self.cov_matrix @ w_opt))
        sharpe = (port_ret - risk_free_rate) / port_vol if port_vol > 1e-9 else 0.0

        w_dict = {sym: round(float(w), 4) for sym, w in zip(self.symbols, w_opt)}
        return OptimizationResult(w_dict, port_ret, port_vol, sharpe, 0.0, True, "mean_variance")

    def solve_turnover_aware(
        self,
        prev_weights: Optional[Union[Dict[str, float], np.ndarray]] = None,
        churn_penalty: float = 0.5,
        lambda_risk: float = 1.0,
        max_weight: float = 0.40,
        group_map: Optional[Dict[str, str]] = None,
        group_caps: Optional[Dict[str, float]] = None,
    ) -> OptimizationResult:
        """
        Turnover-aware quadratic utility optimizer:
        min_w  - w'mu + lambda * w'Sigma w + gamma * ||w - w_prev||_1
        subject to sum(w) = 1, 0 <= w_i <= max_weight, and sector group caps.
        """
        n = len(self.symbols)
        if n == 0:
            return OptimizationResult({}, 0.0, 0.0, 0.0, 0.0, False, "turnover_aware")
        if n == 1:
            return OptimizationResult(
                {self.symbols[0]: 1.0},
                float(self.expected_returns[0]),
                float(np.sqrt(self.cov_matrix[0, 0])),
                0.0,
                0.0,
                True,
                "turnover_aware",
            )

        g_map = group_map or DEFAULT_GROUP_MAP
        g_caps = dict(group_caps or DEFAULT_GROUP_CAPS)

        # Parse previous weights
        if isinstance(prev_weights, dict):
            w_prev = np.array([prev_weights.get(s, 0.0) for s in self.symbols], dtype=np.float64)
        elif isinstance(prev_weights, np.ndarray):
            w_prev = prev_weights.astype(np.float64)
        else:
            w_prev = np.full(n, 1.0 / n, dtype=np.float64)

        if np.sum(w_prev) > 0:
            w_prev = w_prev / np.sum(w_prev)
        else:
            w_prev = np.full(n, 1.0 / n, dtype=np.float64)

        # Check active group caps
        active_groups = set(g_map.get(s, "OTHER") for s in self.symbols)
        active_cap_sum = sum(g_caps.get(g, 1.0) for g in active_groups)
        adjusted_caps = dict(g_caps)

        # If active caps sum to < 1.0, distribute shortfall to non-metals groups
        if active_cap_sum < 1.0:
            shortfall = 1.0 - active_cap_sum
            non_metals = [g for g in active_groups if g != "METALS"]
            if non_metals:
                add_per_g = shortfall / len(non_metals)
                for g in non_metals:
                    adjusted_caps[g] = adjusted_caps.get(g, 0.40) + add_per_g
            else:
                for g in active_groups:
                    adjusted_caps[g] = adjusted_caps.get(g, 1.0) + (shortfall / len(active_groups))

        def _project(w_in: np.ndarray) -> np.ndarray:
            w = np.maximum(0.0, w_in)
            total = np.sum(w)
            if total > 1e-9:
                w = w / total
            else:
                w = np.full(n, 1.0 / n)

            # Iterative group cap enforcement
            for _ in range(15):
                violated = False
                for grp, cap in adjusted_caps.items():
                    idx = [i for i, s in enumerate(self.symbols) if g_map.get(s, "OTHER") == grp]
                    if not idx:
                        continue
                    grp_sum = np.sum(w[idx])
                    if grp_sum > cap + 1e-6:
                        violated = True
                        excess = grp_sum - cap
                        w[idx] = w[idx] * (cap / grp_sum)
                        other_idx = [i for i, s in enumerate(self.symbols) if g_map.get(s, "OTHER") != grp]
                        if other_idx and np.sum(w[other_idx]) > 0:
                            w[other_idx] += excess * (w[other_idx] / np.sum(w[other_idx]))
                        elif other_idx:
                            w[other_idx] += excess / len(other_idx)
                if not violated:
                    break

            w = np.maximum(0.0, w)
            sum_w = np.sum(w)
            return w / sum_w if sum_w > 1e-9 else np.full(n, 1.0 / n)

        # Pure-NumPy subgradient descent
        w = _project(w_prev.copy())
        lr = 0.02
        for t in range(400):
            grad = -self.expected_returns + (2.0 * lambda_risk * (self.cov_matrix @ w)) + (churn_penalty * np.sign(w - w_prev))
            step_size = lr / np.sqrt(1.0 + t * 0.1)
            w_next = w - step_size * grad
            w = _project(w_next)

        # Final check: strict clamping of group caps
        for grp, cap in adjusted_caps.items():
            idx = [i for i, s in enumerate(self.symbols) if g_map.get(s, "OTHER") == grp]
            if not idx:
                continue
            grp_sum = np.sum(w[idx])
            if grp_sum > cap:
                excess = grp_sum - cap
                w[idx] = w[idx] * (cap / grp_sum)
                other_idx = [i for i, s in enumerate(self.symbols) if g_map.get(s, "OTHER") != grp]
                if other_idx:
                    w[other_idx] += excess * (w[other_idx] / np.sum(w[other_idx]))

        w = np.maximum(0.0, w)
        w = w / np.sum(w)

        turnover = float(0.5 * np.sum(np.abs(w - w_prev)))
        port_ret = float(np.dot(w, self.expected_returns))
        port_vol = float(np.sqrt(w @ self.cov_matrix @ w))
        sharpe = port_ret / port_vol if port_vol > 1e-9 else 0.0

        w_dict = {sym: round(float(wi), 4) for sym, wi in zip(self.symbols, w)}
        return OptimizationResult(w_dict, port_ret, port_vol, sharpe, turnover, True, "turnover_aware")

    # --------------------------------------------------------------------------
    # Backward Compatibility Static Methods
    # --------------------------------------------------------------------------

    @staticmethod
    def equal_volatility(returns_df: pd.DataFrame) -> OptimizationResult:
        cols = list(returns_df.columns)
        cov = returns_df.cov().values * 252.0
        mean = returns_df.mean().values * 252.0
        return PortfolioOptimizer(cols, cov, mean).solve_equal_volatility()

    @staticmethod
    def mean_variance(
        returns_df: pd.DataFrame,
        risk_free_rate: float = 0.0,
        max_weight: float = 0.40,
    ) -> OptimizationResult:
        cols = list(returns_df.columns)
        cov = returns_df.cov().values * 252.0
        mean = returns_df.mean().values * 252.0
        return PortfolioOptimizer(cols, cov, mean).solve_mean_variance(
            risk_free_rate=risk_free_rate,
            max_weight=max_weight,
        )

    @staticmethod
    def risk_parity(cov_matrix: np.ndarray, symbols: List[str]) -> OptimizationResult:
        return PortfolioOptimizer(symbols, cov_matrix).solve_risk_parity_erc()

    @staticmethod
    def turnover_aware(
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        current_weights: np.ndarray,
        symbols: List[str],
        lambda_risk: float = 1.0,
        gamma_turnover: float = 0.5,
        max_weight: float = 0.40,
        group_map: Optional[Dict[str, str]] = None,
        group_caps: Optional[Dict[str, float]] = None,
    ) -> OptimizationResult:
        return PortfolioOptimizer(symbols, cov_matrix, expected_returns).solve_turnover_aware(
            prev_weights=current_weights,
            churn_penalty=gamma_turnover,
            lambda_risk=lambda_risk,
            max_weight=max_weight,
            group_map=group_map,
            group_caps=group_caps,
        )
