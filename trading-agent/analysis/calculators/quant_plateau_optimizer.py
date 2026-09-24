"""
Quant Plateau Optimizer: Anti-Overfitting Parameter Optimization Engine.

Implements Parameter Flat Plateau Optimization (Robert Pardo / Marcos López de Prado).
Rather than searching for isolated overfitted Sharpe peaks (curve-fitting),
this optimizer evaluates the parameter surface and selects regions where parameter
perturbations (neighbors) remain consistently profitable and stable.

Plateau Fitness:
    Fitness(θ) = E_{δ}[SR(θ + δ)] - λ * Std_{δ}[SR(θ + δ)] - DSR_penalty

Uses pure NumPy/SciPy for zero external pip dependency overhead.
"""

import math
import random
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Awaitable, Union, Sequence
import numpy as np

from backtest.statistical_tests import deflated_sharpe_ratio, compute_sample_moments

logger = logging.getLogger("TradingAgent.QuantPlateauOptimizer")


@dataclass
class ParameterSpec:
    name: str
    param_type: str  # "int", "float", "choice"
    low: float = 0.0
    high: float = 1.0
    step: Optional[float] = None
    choices: Optional[List[Any]] = None

    def sample(self) -> Any:
        if self.param_type == "choice" and self.choices:
            return random.choice(self.choices)
        elif self.param_type == "int":
            low_i = int(self.low)
            high_i = int(self.high)
            if self.step:
                steps = int((high_i - low_i) / self.step) + 1
                return low_i + int(random.randint(0, max(0, steps - 1)) * self.step)
            return random.randint(low_i, high_i)
        else:  # float
            val = random.uniform(self.low, self.high)
            if self.step:
                steps = round((val - self.low) / self.step)
                val = self.low + steps * self.step
            return round(val, 4)

    def perturb(self, val: Any, step_factor: float = 1.0) -> List[Any]:
        """Returns adjacent neighbor parameter values for plateau testing."""
        neighbors = [val]
        if self.param_type == "choice" and self.choices:
            idx = self.choices.index(val) if val in self.choices else 0
            if idx > 0:
                neighbors.append(self.choices[idx - 1])
            if idx < len(self.choices) - 1:
                neighbors.append(self.choices[idx + 1])
        elif self.param_type == "int":
            delta = max(1, int((self.step or 1.0) * step_factor))
            if int(val) - delta >= int(self.low):
                neighbors.append(int(val) - delta)
            if int(val) + delta <= int(self.high):
                neighbors.append(int(val) + delta)
        else:  # float
            effective_step = (self.step or ((self.high - self.low) * 0.05)) * step_factor
            if float(val) - effective_step >= self.low:
                neighbors.append(round(float(val) - effective_step, 4))
            if float(val) + effective_step <= self.high:
                neighbors.append(round(float(val) + effective_step, 4))
        return neighbors


@dataclass
class PlateauOptimizationResult:
    best_params: Dict[str, Any]
    best_plateau_score: float
    center_sharpe: float
    neighbor_mean_sharpe: float
    neighbor_std_sharpe: float
    total_evaluations: int
    dsr_score: float
    is_plateau_stable: bool
    trials_history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def best_parameters(self) -> Dict[str, Any]:
        """Backward-compatible alias for best_params."""
        return self.best_params



class QuantPlateauOptimizer:
    """
    Adaptive Plateau Parameter Optimizer.
    Evaluates candidate parameters and their neighbor perturbations to identify
    wide, flat, robust profit zones that survive live market shifts.
    """

    def __init__(
        self,
        param_space: List[ParameterSpec],
        n_trials: int = 30,
        n_neighbors_per_candidate: int = 3,
        lambda_stability: float = 0.5,
        min_trade_count: int = 20,
        seed: Optional[int] = 42,
    ):
        self.param_space = param_space
        self.n_trials = n_trials
        self.n_neighbors_per_candidate = n_neighbors_per_candidate
        self.lambda_stability = lambda_stability
        self.min_trade_count = min_trade_count
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    def _sample_candidate(self, good_trials: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Adaptive TPE-inspired sampling: With probability 0.70, sample near previously
        successful plateau candidates; with probability 0.30, explore uniformly.
        """
        if good_trials and random.random() < 0.70:
            parent = random.choice(good_trials)["params"]
            candidate = {}
            for p in self.param_space:
                val = parent[p.name]
                # Perturb parent
                neighbors = p.perturb(val, step_factor=random.choice([0.5, 1.0, 1.5]))
                candidate[p.name] = random.choice(neighbors)
            return candidate
        else:
            return {p.name: p.sample() for p in self.param_space}

    async def optimize(
        self,
        eval_fn: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
    ) -> PlateauOptimizationResult:
        """
        Executes plateau optimization.
        eval_fn must accept params dict and return dict containing at least:
        {'sharpe': float, 'trades': int, 'trade_returns': List[float], 'pnl_pct': float}
        """
        best_candidate: Optional[Dict[str, Any]] = None
        best_score = -float("inf")
        best_center_sr = 0.0
        best_mean_sr = 0.0
        best_std_sr = 0.0
        best_dsr = 0.0
        best_stable = False

        evaluated_cache: Dict[str, Dict[str, Any]] = {}
        trials_history: List[Dict[str, Any]] = []
        good_trials: List[Dict[str, Any]] = []

        total_evals = 0

        async def _eval_cached(params: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal total_evals
            key = str(sorted(params.items()))
            if key in evaluated_cache:
                return evaluated_cache[key]
            total_evals += 1
            try:
                res = await eval_fn(params)
            except Exception as e:
                logger.debug(f"[QuantOptimizer] Evaluation error for {params}: {e}")
                res = {"sharpe": 0.0, "trades": 0, "trade_returns": [], "pnl_pct": 0.0}
            evaluated_cache[key] = res
            return res

        for trial_idx in range(self.n_trials):
            candidate_params = self._sample_candidate(good_trials)

            # 1. Evaluate center parameter
            center_res = await _eval_cached(candidate_params)
            center_sr = float(center_res.get("sharpe", 0.0) or 0.0)
            center_trades = int(center_res.get("trades", 0) or 0)
            trade_returns = list(center_res.get("trade_returns", []) or [])

            # Reject candidates with insufficient trade count
            if center_trades < self.min_trade_count or center_sr <= 0.0:
                trials_history.append({
                    "params": candidate_params,
                    "plateau_score": -1.0,
                    "center_sharpe": center_sr,
                    "trades": center_trades,
                })
                continue

            # 2. Evaluate neighbor perturbations to measure plateau stability
            neighbor_sharpes = [center_sr]
            for p in self.param_space:
                val = candidate_params[p.name]
                neighbors = p.perturb(val)
                for n_val in neighbors:
                    if n_val == val:
                        continue
                    n_params = dict(candidate_params)
                    n_params[p.name] = n_val
                    n_res = await _eval_cached(n_params)
                    neighbor_sharpes.append(float(n_res.get("sharpe", 0.0) or 0.0))

            mean_neighbor_sr = float(np.mean(neighbor_sharpes))
            std_neighbor_sr = float(np.std(neighbor_sharpes)) if len(neighbor_sharpes) > 1 else 0.0

            # 3. Deflated Sharpe Ratio calculation
            skew, kurt = 0.0, 0.0
            if len(trade_returns) >= 3:
                _, _, skew, kurt = compute_sample_moments(trade_returns)

            daily_sr = (center_sr / math.sqrt(252.0)) if center_sr > 0 else 0.0
            dsr = deflated_sharpe_ratio(
                observed_sr=daily_sr,
                n_trials=max(1, total_evals),
                n_obs=len(trade_returns),
                skew=skew,
                excess_kurt=kurt,
                sr_std=0.5 / math.sqrt(252.0),
            )

            # Plateau Fitness Function:
            # Rewards high neighbor mean, penalizes high neighbor variance and isolated peaks
            plateau_score = mean_neighbor_sr - (self.lambda_stability * std_neighbor_sr)
            # DSR gating penalty if DSR < 0.60
            if dsr < 0.60:
                plateau_score *= 0.70

            is_stable = bool(std_neighbor_sr < (mean_neighbor_sr * 0.40) and mean_neighbor_sr >= 0.8)

            record = {
                "params": candidate_params,
                "plateau_score": round(plateau_score, 3),
                "center_sharpe": round(center_sr, 2),
                "mean_neighbor_sharpe": round(mean_neighbor_sr, 2),
                "std_neighbor_sharpe": round(std_neighbor_sr, 3),
                "dsr": round(dsr, 2),
                "trades": center_trades,
                "is_stable": is_stable,
            }
            trials_history.append(record)

            if plateau_score > 0.8 and is_stable:
                good_trials.append(record)

            if plateau_score > best_score:
                best_score = plateau_score
                best_candidate = candidate_params
                best_center_sr = center_sr
                best_mean_sr = mean_neighbor_sr
                best_std_sr = std_neighbor_sr
                best_dsr = dsr
                best_stable = is_stable

        fallback_params = {p.name: p.sample() for p in self.param_space}
        return PlateauOptimizationResult(
            best_params=best_candidate or fallback_params,
            best_plateau_score=max(0.0, round(best_score, 3)),
            center_sharpe=round(best_center_sr, 2),
            neighbor_mean_sharpe=round(best_mean_sr, 2),
            neighbor_std_sharpe=round(best_std_sr, 3),
            total_evaluations=total_evals,
            dsr_score=round(best_dsr, 2),
            is_plateau_stable=best_stable,
            trials_history=trials_history,
        )
