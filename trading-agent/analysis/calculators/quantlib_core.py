# ==============================================================================
# File: analysis/calculators/quantlib_core.py
# Monika Institutional Quantitative Mathematics & Statistical Validation Engine
# ==============================================================================

"""
Core quantitative finance mathematics and statistical validation primitives.

Implements rigorous mathematical models with pure Python standard library resilience:
1. Deflated Sharpe Ratio (DSR) & Probabilistic Sharpe Ratio (PSR) (Bailey & Lopez de Prado, 2014)
2. Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric Cross-Validation (CSCV)
3. Combinatorial Purged & Embargoed Cross-Validation (López de Prado, 2018)
4. Market Impact Models (Square-Root Almgren-Chriss power-law & Linear Impact)
5. Black-Scholes-Merton European Option Pricing, Greeks, and Implied Volatility Solver
6. Parametric Archimedean & Elliptical Copulas (Frank, Gaussian, Clayton, Gumbel)
7. Value-at-Risk Validation Tests: Kupiec POF, Christoffersen Independence, Basel Traffic Light
"""

from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

EULER_MASCHERONI = 0.57721566490153286060
GAUSSIAN_KURTOSIS = 3.0

_STD_NORM = statistics.NormalDist(0.0, 1.0)


def _norm_cdf(x: float) -> float:
    return _STD_NORM.cdf(x)


def _norm_pdf(x: float) -> float:
    return _STD_NORM.pdf(x)


def _norm_ppf(p: float) -> float:
    clamped_p = min(max(p, 1e-12), 1.0 - 1e-12)
    return _STD_NORM.inv_cdf(clamped_p)


def _brentq_solve(f: Callable[[float], float], a: float, b: float, tol: float = 1e-5, max_iter: int = 100) -> float:
    """Robust Brent-Dekker root finding algorithm (zero external dependency)."""
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        raise ValueError("Root is not bracketed: f(a) and f(b) must have opposite signs")

    if abs(fa) < abs(fb):
        a, b = b, a
        fa, fb = fb, fa

    c, fc = a, fa
    mflag = True
    d = 0.0

    for _ in range(max_iter):
        if abs(fb) < tol:
            return b

        if fa != fc and fb != fc:
            # Inverse quadratic interpolation
            s = (a * fb * fc) / ((fa - fb) * (fa - fc)) + \
                (b * fa * fc) / ((fb - fa) * (fb - fc)) + \
                (c * fa * fb) / ((fc - fa) * (fc - fb))
        else:
            # Secant method
            s = b - fb * (b - a) / (fb - fa)

        # Condition checks for bisection fallback
        cond1 = not ((3 * a + b) / 4 < s < b if a < b else b < s < (3 * a + b) / 4)
        cond2 = mflag and abs(s - b) >= abs(b - c) / 2
        cond3 = not mflag and abs(s - b) >= abs(c - d) / 2
        cond4 = mflag and abs(b - c) < tol
        cond5 = not mflag and abs(c - d) < tol

        if cond1 or cond2 or cond3 or cond4 or cond5:
            s = (a + b) / 2
            mflag = True
        else:
            mflag = False

        fs = f(s)
        d = c
        c, fc = b, fb

        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs

        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa

    return b


# ==============================================================================
# 1. Deflated & Probabilistic Sharpe Ratio
# ==============================================================================

@dataclass(frozen=True, slots=True)
class DeflatedSharpeResult:
    observed_sharpe: float
    expected_maximum_sharpe: float
    deflated_sharpe_ratio: float
    n_trials: int
    n_observations: int
    trial_sharpe_std: float
    skew: float
    kurtosis: float
    survives: bool


def expected_maximum_sharpe(n_trials: int, trial_sharpe_std: float) -> float:
    """Expected maximum Sharpe ratio across n_trials independent strategies."""
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if trial_sharpe_std < 0.0:
        raise ValueError(f"trial_sharpe_std must be >= 0, got {trial_sharpe_std}")
    if n_trials == 1 or trial_sharpe_std == 0.0:
        return 0.0

    qa = _norm_ppf(1.0 - 1.0 / n_trials)
    qb = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(trial_sharpe_std * ((1.0 - EULER_MASCHERONI) * qa + EULER_MASCHERONI * qb))


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    n_observations: int,
    benchmark_sharpe: float = 0.0,
    skew: float = 0.0,
    kurtosis: float = GAUSSIAN_KURTOSIS,
) -> float:
    """Computes the probability that true Sharpe ratio exceeds benchmark_sharpe."""
    if n_observations < 2:
        raise ValueError(f"n_observations must be >= 2, got {n_observations}")

    denom_var = 1.0 - skew * observed_sharpe + ((kurtosis - 1.0) / 4.0) * (observed_sharpe ** 2)
    if denom_var <= 0.0:
        denom_var = 1e-12

    se = math.sqrt(denom_var / (n_observations - 1.0))
    z = (observed_sharpe - benchmark_sharpe) / se
    return float(_norm_cdf(z))


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    trial_sharpe_std: float,
    skew: float = 0.0,
    kurtosis: float = GAUSSIAN_KURTOSIS,
    confidence: float = 0.95,
) -> DeflatedSharpeResult:
    """Deflates observed Sharpe ratio by the number of independent trials searched."""
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    bar = expected_maximum_sharpe(n_trials, trial_sharpe_std)
    dsr = probabilistic_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_observations=n_observations,
        benchmark_sharpe=bar,
        skew=skew,
        kurtosis=kurtosis,
    )
    return DeflatedSharpeResult(
        observed_sharpe=observed_sharpe,
        expected_maximum_sharpe=bar,
        deflated_sharpe_ratio=dsr,
        n_trials=n_trials,
        n_observations=n_observations,
        trial_sharpe_std=trial_sharpe_std,
        skew=skew,
        kurtosis=kurtosis,
        survives=dsr > confidence,
    )


# ==============================================================================
# 2. Probability of Backtest Overfitting (PBO - CSCV)
# ==============================================================================

@dataclass(frozen=True, slots=True)
class PBOResult:
    pbo: float
    n_splits: int
    n_blocks: int
    n_strategies: int
    logit_distribution: List[float]


def probability_of_backtest_overfitting(
    matrix_returns: np.ndarray,
    n_blocks: int = 16,
) -> PBOResult:
    """Computes Probability of Backtest Overfitting (PBO) via CSCV."""
    T, N = matrix_returns.shape
    if n_blocks % 2 != 0:
        raise ValueError(f"n_blocks must be even, got {n_blocks}")
    if T < n_blocks:
        raise ValueError(f"T ({T}) must be >= n_blocks ({n_blocks})")

    block_size = T // n_blocks
    blocks = [matrix_returns[i * block_size : (i + 1) * block_size, :] for i in range(n_blocks)]

    half_blocks = n_blocks // 2
    combinations = list(itertools.combinations(range(n_blocks), half_blocks))
    n_splits = len(combinations) // 2

    logits = []
    for is_indices in combinations[:n_splits]:
        oos_indices = [idx for idx in range(n_blocks) if idx not in is_indices]

        is_ret = np.concatenate([blocks[i] for i in is_indices], axis=0)
        oos_ret = np.concatenate([blocks[i] for i in oos_indices], axis=0)

        is_mean = np.nanmean(is_ret, axis=0)
        is_std = np.nanstd(is_ret, axis=0, ddof=1)
        is_std[is_std == 0] = np.nan
        is_sharpe = is_mean / is_std

        oos_mean = np.nanmean(oos_ret, axis=0)
        oos_std = np.nanstd(oos_ret, axis=0, ddof=1)
        oos_std[oos_std == 0] = np.nan
        oos_sharpe = oos_mean / oos_std

        best_is_idx = int(np.nanargmax(is_sharpe))
        oos_best = oos_sharpe[best_is_idx]
        valid_oos = oos_sharpe[~np.isnan(oos_sharpe)]
        if valid_oos.size == 0 or np.isnan(oos_best):
            continue

        rank_oos = float(np.sum(valid_oos <= oos_best) / valid_oos.size)
        rank_clamped = min(max(rank_oos, 1e-4), 1.0 - 1e-4)
        logit = math.log(rank_clamped / (1.0 - rank_clamped))
        logits.append(logit)

    if not logits:
        return PBOResult(pbo=1.0, n_splits=0, n_blocks=n_blocks, n_strategies=N, logit_distribution=[])

    logit_arr = np.array(logits)
    pbo = float(np.mean(logit_arr <= 0.0))
    return PBOResult(
        pbo=pbo,
        n_splits=len(logits),
        n_blocks=n_blocks,
        n_strategies=N,
        logit_distribution=logits[:100],
    )


# ==============================================================================
# 3. Combinatorial Purged & Embargoed Cross-Validation
# ==============================================================================

def combinatorial_purged_splits(
    n_samples: int,
    n_splits: int = 6,
    n_test_splits: int = 2,
    embargo_pct: float = 0.01,
) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
    """Generates train/test index splits with Purging and Embargo."""
    indices = np.arange(n_samples)
    split_size = n_samples // n_splits
    splits = [indices[i * split_size : (i + 1) * split_size if i < n_splits - 1 else n_samples] for i in range(n_splits)]
    embargo_bars = int(n_samples * embargo_pct)

    for test_fold_ids in itertools.combinations(range(n_splits), n_test_splits):
        test_indices = np.concatenate([splits[i] for i in test_fold_ids])
        test_indices.sort()

        train_mask = np.ones(n_samples, dtype=bool)
        for fold_id in test_fold_ids:
            start_idx = splits[fold_id][0]
            end_idx = splits[fold_id][-1] + 1 + embargo_bars
            train_mask[start_idx : min(end_idx, n_samples)] = False

        train_indices = indices[train_mask]
        yield train_indices, test_indices


def detect_boundary_leakage(train_idx: np.ndarray, test_idx: np.ndarray, max_horizon: int = 5) -> bool:
    """Returns True if any training bar falls within max_horizon bars of test set boundary."""
    if len(train_idx) == 0 or len(test_idx) == 0:
        return False
    train_set = set(train_idx)
    for t in test_idx:
        for offset in range(-max_horizon, max_horizon + 1):
            if (t + offset) in train_set:
                return True
    return False


# ==============================================================================
# 4. Market Impact & Slippage Models
# ==============================================================================

def fixed_slippage(price: float, side: str, bps: float = 5.0) -> float:
    """Fixed basis point slippage model for orders < 0.5% of ADV."""
    mult = 1.0 + (bps * 1e-4) if side.lower() == "buy" else 1.0 - (bps * 1e-4)
    return float(price * mult)


def linear_impact(price: float, side: str, volume: float, adv: float, coeff: float = 0.1) -> float:
    """Linear market impact model for intermediate order sizes (0.5% - 5% ADV)."""
    if adv <= 0:
        return fixed_slippage(price, side, bps=25.0)
    participation = min(volume / adv, 1.0)
    impact_bps = coeff * participation * 10000.0
    return fixed_slippage(price, side, bps=impact_bps)


def sqrt_impact(
    price: float,
    side: str,
    volume: float,
    adv: float,
    daily_volatility: float,
    eta: float = 0.5,
) -> float:
    """Square-root market impact power-law model for institutional orders (> 5% ADV)."""
    if adv <= 0:
        return fixed_slippage(price, side, bps=50.0)
    participation = min(max(volume / adv, 0.0), 1.0)
    fractional_impact = eta * daily_volatility * math.sqrt(participation)
    mult = (1.0 + fractional_impact) if side.lower() == "buy" else (1.0 - fractional_impact)
    return float(price * mult)


# ==============================================================================
# 5. Black-Scholes-Merton Pricing, Greeks & Implied Volatility Solver
# ==============================================================================

def black_scholes_price(
    spot: float,
    strike: float,
    t_years: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: str = "call",
) -> float:
    """Black-Scholes-Merton European option analytical pricing."""
    if t_years <= 0.0 or volatility <= 0.0:
        intrinsic = max(spot - strike, 0.0) if option_type.lower() == "call" else max(strike - spot, 0.0)
        return float(intrinsic)

    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility ** 2) * t_years) / (volatility * math.sqrt(t_years))
    d2 = d1 - volatility * math.sqrt(t_years)

    df_q = math.exp(-dividend_yield * t_years)
    df_r = math.exp(-rate * t_years)

    if option_type.lower() == "call":
        return float(spot * df_q * _norm_cdf(d1) - strike * df_r * _norm_cdf(d2))
    else:
        return float(strike * df_r * _norm_cdf(-d2) - spot * df_q * _norm_cdf(-d1))


def black_scholes_greeks(
    spot: float,
    strike: float,
    t_years: float,
    volatility: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: str = "call",
) -> Dict[str, float]:
    """Analytical Black-Scholes Greeks: Delta, Gamma, Vega, Theta, Rho."""
    if t_years <= 1e-6 or volatility <= 1e-6:
        is_call = option_type.lower() == "call"
        delta_val = 1.0 if (is_call and spot > strike) else (-1.0 if (not is_call and spot < strike) else 0.0)
        return {"delta": delta_val, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility ** 2) * t_years) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    df_q = math.exp(-dividend_yield * t_years)
    df_r = math.exp(-rate * t_years)
    n_prime_d1 = _norm_pdf(d1)

    is_call = option_type.lower() == "call"
    delta = df_q * _norm_cdf(d1) if is_call else df_q * (_norm_cdf(d1) - 1.0)
    gamma = (df_q * n_prime_d1) / (spot * volatility * sqrt_t)
    vega = (spot * df_q * sqrt_t * n_prime_d1) * 0.01

    theta_base = -(spot * df_q * n_prime_d1 * volatility) / (2.0 * sqrt_t)
    if is_call:
        theta = (theta_base - rate * strike * df_r * _norm_cdf(d2) + dividend_yield * spot * df_q * _norm_cdf(d1)) / 365.0
        rho = (strike * t_years * df_r * _norm_cdf(d2)) * 0.01
    else:
        theta = (theta_base + rate * strike * df_r * _norm_cdf(-d2) - dividend_yield * spot * df_q * _norm_cdf(-d1)) / 365.0
        rho = (-strike * t_years * df_r * _norm_cdf(-d2)) * 0.01

    return {"delta": float(delta), "gamma": float(gamma), "vega": float(vega), "theta": float(theta), "rho": float(rho)}


def implied_volatility_solver(
    market_price: float,
    spot: float,
    strike: float,
    t_years: float,
    rate: float = 0.0,
    dividend_yield: float = 0.0,
    option_type: str = "call",
) -> Optional[float]:
    """Inverts Black-Scholes formula using pure Python Brent-Dekker solver."""
    intrinsic = max(spot - strike, 0.0) if option_type.lower() == "call" else max(strike - spot, 0.0)
    if market_price <= intrinsic + 1e-7:
        return None

    def objective(sig: float) -> float:
        return black_scholes_price(spot, strike, t_years, sig, rate, dividend_yield, option_type) - market_price

    try:
        sol = _brentq_solve(objective, 1e-4, 5.0, tol=1e-5, max_iter=100)
        return float(sol)
    except Exception:
        return None


# ==============================================================================
# 6. Copula Models
# ==============================================================================

def gaussian_copula_cdf(u: float, v: float, rho: float) -> float:
    """Bivariate Gaussian copula CDF using Drezner-Wesolowsky bivariate normal approximation."""
    if not (-1.0 < rho < 1.0):
        raise ValueError(f"rho must be in (-1, 1), got {rho}")
    u_c = min(max(u, 1e-9), 1.0 - 1e-9)
    v_c = min(max(v, 1e-9), 1.0 - 1e-9)
    z1 = _norm_ppf(u_c)
    z2 = _norm_ppf(v_c)

    # Fast 10-point Gauss-Legendre quadrature along correlation ray
    def integrand(r: float) -> float:
        denom = 1.0 - r * r
        arg = -(z1 * z1 - 2.0 * r * z1 * z2 + z2 * z2) / (2.0 * denom)
        return math.exp(arg) / (2.0 * math.pi * math.sqrt(denom))

    # Simpson's rule over [0, rho]
    n_steps = 20
    dr = rho / n_steps
    acc = 0.5 * (integrand(0.0) + integrand(rho))
    for i in range(1, n_steps):
        acc += integrand(i * dr)
    integral = acc * dr
    return float(u_c * v_c + integral)


def frank_copula_cdf(u: float, v: float, theta: float) -> float:
    """Bivariate Frank Archimedean copula CDF."""
    if abs(theta) < 1e-9:
        return u * v
    num = (math.exp(-theta * u) - 1.0) * (math.exp(-theta * v) - 1.0)
    denom = math.exp(-theta) - 1.0
    return float(- (1.0 / theta) * math.log(1.0 + num / denom))


def clayton_copula_cdf(u: float, v: float, theta: float) -> float:
    """Bivariate Clayton lower tail-dependence copula CDF."""
    if theta <= 0:
        return u * v
    term = (u ** (-theta)) + (v ** (-theta)) - 1.0
    return float(max(term, 0.0) ** (-1.0 / theta))


def gumbel_copula_cdf(u: float, v: float, theta: float) -> float:
    """Bivariate Gumbel upper tail-dependence copula CDF."""
    if theta < 1.0:
        raise ValueError(f"Gumbel theta must be >= 1.0, got {theta}")
    if theta == 1.0:
        return u * v
    u_c = min(max(u, 1e-9), 1.0 - 1e-9)
    v_c = min(max(v, 1e-9), 1.0 - 1e-9)
    term = ((-math.log(u_c)) ** theta) + ((-math.log(v_c)) ** theta)
    return float(math.exp(- (term ** (1.0 / theta))))


# ==============================================================================
# 7. Value-at-Risk Validation Tests
# ==============================================================================

@dataclass(frozen=True, slots=True)
class KupiecPOFResult:
    n_observations: int
    n_exceptions: int
    expected_exceptions: float
    lr_stat: float
    p_value: float
    reject_null: bool


def _chi2_1df_pvalue(x: float) -> float:
    """Exact closed-form p-value for 1 degree of freedom Chi-squared distribution."""
    if x <= 0.0:
        return 1.0
    return float(math.erfc(math.sqrt(x / 2.0)))


def kupiec_pof_test(
    exceptions: int,
    total_observations: int,
    target_alpha: float = 0.01,
    significance_level: float = 0.05,
) -> KupiecPOFResult:
    """Kupiec Proportion of Failures (POF) unconditional coverage likelihood-ratio test."""
    p_hat = exceptions / total_observations
    p = target_alpha
    expected = total_observations * target_alpha

    if exceptions == 0:
        lr = -2.0 * math.log((1.0 - p) ** total_observations)
    elif exceptions == total_observations:
        lr = -2.0 * math.log(p ** total_observations)
    else:
        log_num = (total_observations - exceptions) * math.log(1.0 - p) + exceptions * math.log(p)
        log_den = (total_observations - exceptions) * math.log(1.0 - p_hat) + exceptions * math.log(p_hat)
        lr = -2.0 * (log_num - log_den)

    lr = max(float(lr), 0.0)
    p_val = _chi2_1df_pvalue(lr)
    return KupiecPOFResult(
        n_observations=total_observations,
        n_exceptions=exceptions,
        expected_exceptions=expected,
        lr_stat=lr,
        p_value=p_val,
        reject_null=p_val < significance_level,
    )


@dataclass(frozen=True, slots=True)
class ChristoffersenResult:
    lr_ind_stat: float
    p_value: float
    reject_null: bool


def christoffersen_test(exception_series: np.ndarray, significance_level: float = 0.05) -> ChristoffersenResult:
    """Christoffersen test for independence of consecutive VaR exceptions."""
    arr = (exception_series.astype(int) > 0).astype(int)
    if len(arr) < 2:
        return ChristoffersenResult(lr_ind_stat=0.0, p_value=1.0, reject_null=False)

    pairs = list(zip(arr[:-1], arr[1:]))
    n00 = sum(1 for a, b in pairs if a == 0 and b == 0)
    n01 = sum(1 for a, b in pairs if a == 0 and b == 1)
    n10 = sum(1 for a, b in pairs if a == 1 and b == 0)
    n11 = sum(1 for a, b in pairs if a == 1 and b == 1)

    pi0 = n01 / (n00 + n01) if (n00 + n01) > 0 else 0.0
    pi1 = n11 / (n10 + n11) if (n10 + n11) > 0 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11) if len(pairs) > 0 else 0.0

    if pi0 == 0.0 or pi1 == 0.0 or pi == 0.0 or (1.0 - pi0) <= 0.0 or (1.0 - pi1) <= 0.0:
        return ChristoffersenResult(lr_ind_stat=0.0, p_value=1.0, reject_null=False)

    l_null = (n00 + n10) * math.log(1.0 - pi) + (n01 + n11) * math.log(pi)
    l_alt = n00 * math.log(1.0 - pi0) + n01 * math.log(pi0) + n10 * math.log(1.0 - pi1) + n11 * math.log(pi1)
    lr = -2.0 * (l_null - l_alt)
    lr = max(float(lr), 0.0)
    p_val = _chi2_1df_pvalue(lr)

    return ChristoffersenResult(lr_ind_stat=lr, p_value=p_val, reject_null=p_val < significance_level)


def _binom_cdf(k: int, n: int, p: float) -> float:
    """Exact binomial CDF using standard library math.comb."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    total = 0.0
    for i in range(k + 1):
        total += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
    return float(total)


def basel_traffic_light(exceptions: int, n_observations: int = 250, target_alpha: float = 0.01) -> str:
    """Basel Committee traffic light framework (Green / Yellow / Red)."""
    if n_observations == 250 and target_alpha == 0.01:
        if exceptions <= 4:
            return "GREEN"
        elif exceptions <= 9:
            return "YELLOW"
        else:
            return "RED"

    cdf_val = _binom_cdf(exceptions, n_observations, target_alpha)
    if cdf_val < 0.95:
        return "GREEN"
    elif cdf_val < 0.9999:
        return "YELLOW"
    else:
        return "RED"


def student_t_copula_tail_dependence(df: float, correlation: float) -> float:
    """Computes symmetric tail dependence coefficient for bivariate Student-t copula."""
    if df <= 0 or not (-1.0 < correlation < 1.0):
        return 0.0
    arg = math.sqrt((df + 1.0) * (1.0 - correlation) / (1.0 + correlation))
    # Approximation of Student-t cdf via normal approximation with kurtosis adjustment
    z = -arg
    p = _norm_cdf(z)
    return float(min(max(2.0 * p, 0.0), 1.0))


class QuantLibCore:
    """Namespace for Monika Institutional Quantitative Finance Primitives."""

    deflated_sharpe_ratio = staticmethod(deflated_sharpe_ratio)
    probabilistic_sharpe_ratio = staticmethod(probabilistic_sharpe_ratio)
    expected_maximum_sharpe = staticmethod(expected_maximum_sharpe)
    probability_of_backtest_overfitting = staticmethod(probability_of_backtest_overfitting)
    combinatorial_purged_splits = staticmethod(combinatorial_purged_splits)
    detect_boundary_leakage = staticmethod(detect_boundary_leakage)
    fixed_slippage = staticmethod(fixed_slippage)
    linear_impact = staticmethod(linear_impact)
    sqrt_impact = staticmethod(sqrt_impact)
    black_scholes_price = staticmethod(black_scholes_price)
    black_scholes_greeks = staticmethod(black_scholes_greeks)
    implied_volatility_solver = staticmethod(implied_volatility_solver)
    gaussian_copula_cdf = staticmethod(gaussian_copula_cdf)
    frank_copula_cdf = staticmethod(frank_copula_cdf)
    clayton_copula_cdf = staticmethod(clayton_copula_cdf)
    gumbel_copula_cdf = staticmethod(gumbel_copula_cdf)
    student_t_copula_tail_dependence = staticmethod(student_t_copula_tail_dependence)
    kupiec_pof_test = staticmethod(kupiec_pof_test)
    christoffersen_test = staticmethod(christoffersen_test)
    basel_traffic_light = staticmethod(basel_traffic_light)

