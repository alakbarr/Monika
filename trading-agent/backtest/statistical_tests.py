"""
Statistical tests and multiple-testing corrections for backtest evaluation.
Implements Probabilistic Sharpe Ratio (PSR), Expected Maximum Sharpe,
and Deflated Sharpe Ratio (DSR) based on Bailey & López de Prado (2012, 2014).

Uses Python stdlib (math, statistics) for zero external dependencies.
"""
import math
import statistics
from typing import Optional, Sequence

_NORMAL = statistics.NormalDist(0.0, 1.0)
_EULER_MASCHERONI = 0.5772156649015328606


def probabilistic_sharpe_ratio(
    observed_sr: float,
    benchmark_sr: float = 0.0,
    n_obs: int = 100,
    skew: float = 0.0,
    excess_kurt: float = 0.0,
) -> float:
    """
    Compute Probabilistic Sharpe Ratio (PSR).

    PSR calculates the probability that the true Sharpe Ratio exceeds benchmark_sr,
    adjusting for small sample size, return skewness, and non-normality (fat tails).

    Formula (Bailey & López de Prado, 2012):
        PSR(SR*) = Phi( (SR - SR*) * sqrt(T - 1) / sqrt(1 - skew*SR + ((excess_kurt + 2)/4)*SR^2) )
    """
    if n_obs < 3:
        return 0.5

    # Variance adjustment term for non-normal returns (Bailey & López de Prado 2012, eq. 6)
    # (gamma4 - 1)/4 = (excess_kurt + 2)/4 = excess_kurt/4 + 0.5
    var_term = 1.0 - (skew * observed_sr) + (((excess_kurt + 2.0) / 4.0) * (observed_sr ** 2))
    if var_term <= 1e-12:
        var_term = 1e-12

    se = math.sqrt(var_term / (n_obs - 1))
    if se < 1e-12:
        return 1.0 if observed_sr >= benchmark_sr else 0.0

    z = (observed_sr - benchmark_sr) / se
    # Clamp z to avoid extreme precision issues
    z = max(-10.0, min(10.0, z))
    return float(_NORMAL.cdf(z))


def expected_max_sharpe(
    n_trials: int,
    sr_std: float = 0.5,
) -> float:
    """
    Calculate Expected Maximum Sharpe Ratio across N independent strategy trials under H0.

    Approximation based on extreme value theory (Bailey & López de Prado, 2014):
        E[max_N] ≈ sr_std * [ (1 - gamma) * Phi^-1(1 - 1/N) + gamma * Phi^-1(1 - 1/(N*e)) ]
    """
    if n_trials <= 1:
        return 0.0

    if sr_std <= 0.0:
        return 0.0

    p1 = max(1e-12, min(1.0 - 1e-12, 1.0 - (1.0 / n_trials)))
    p2 = max(1e-12, min(1.0 - 1e-12, 1.0 - (1.0 / (n_trials * math.e))))

    z1 = _NORMAL.inv_cdf(p1)
    z2 = _NORMAL.inv_cdf(p2)

    e_max = sr_std * (((1.0 - _EULER_MASCHERONI) * z1) + (_EULER_MASCHERONI * z2))
    return float(max(0.0, e_max))


def deflated_sharpe_ratio(
    observed_sr: float,
    n_trials: int = 1,
    n_obs: int = 100,
    skew: float = 0.0,
    excess_kurt: float = 0.0,
    sr_std: float = 0.5,
) -> float:
    """
    Compute Deflated Sharpe Ratio (DSR).

    Answers: "Given that N strategy configurations/parameters were evaluated,
    is this observed Sharpe Ratio statistically significant, or is it merely
    the maximum of N random trials?"
    """
    if n_trials <= 1:
        return probabilistic_sharpe_ratio(
            observed_sr=observed_sr,
            benchmark_sr=0.0,
            n_obs=n_obs,
            skew=skew,
            excess_kurt=excess_kurt,
        )

    e_max = expected_max_sharpe(n_trials=n_trials, sr_std=sr_std)
    return probabilistic_sharpe_ratio(
        observed_sr=observed_sr,
        benchmark_sr=e_max,
        n_obs=n_obs,
        skew=skew,
        excess_kurt=excess_kurt,
    )


def compute_sample_moments(returns: Sequence[float]) -> tuple[float, float, float, float]:
    """
    Compute sample mean, std, skewness, and excess kurtosis from a sequence of returns.
    Returns: (mean, std, skewness, excess_kurtosis)
    """
    n = len(returns)
    if n < 3:
        return 0.0, 0.0, 0.0, 0.0

    mean = sum(returns) / n
    diffs = [x - mean for x in returns]
    var = sum(d * d for d in diffs) / (n - 1)
    std = math.sqrt(var) if var > 0 else 0.0

    if std < 1e-12:
        return mean, 0.0, 0.0, 0.0

    # Skewness (Fisher-Pearson)
    m3 = sum(d ** 3 for d in diffs) / n
    skew = m3 / (std ** 3)

    # Excess kurtosis
    m4 = sum(d ** 4 for d in diffs) / n
    excess_kurt = (m4 / (std ** 4)) - 3.0

    return mean, std, skew, excess_kurt


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """
    Apply Benjamini-Hochberg False Discovery Rate (FDR) procedure for multiple hypothesis testing.
    Controls FDR at level alpha across m strategy or parameter tests.

    Returns:
        List of booleans where True indicates rejection of H0 (statistically significant discovery).
    """
    m = len(p_values)
    if m == 0:
        return []

    # Store original indices and sort by p-value
    indexed_p = sorted(enumerate(p_values), key=lambda x: x[1])

    # Find largest k such that P_(k) <= (k / m) * alpha (1-indexed rank)
    max_k = -1
    for rank, (orig_idx, p_val) in enumerate(indexed_p, start=1):
        threshold = (rank / m) * alpha
        if p_val <= threshold:
            max_k = rank

    # Any hypothesis with rank <= max_k is significant
    significant_orig_indices = set(orig_idx for orig_idx, _ in indexed_p[:max_k]) if max_k > 0 else set()
    return [i in significant_orig_indices for i in range(m)]


def benjamini_hochberg_adjusted_p(p_values: Sequence[float]) -> list[float]:
    """
    Computes FDR-adjusted q-values (Benjamini-Hochberg).
    q_(i) = min_(j >= i) (min(1.0, (m / j) * p_(j)))
    """
    m = len(p_values)
    if m == 0:
        return []
    indexed_p = sorted(enumerate(p_values), key=lambda x: x[1])
    q_vals = [0.0] * m
    cum_min = 1.0
    # Walk backwards from largest rank m down to 1
    for rank in range(m, 0, -1):
        orig_idx, p = indexed_p[rank - 1]
        adj = (m / rank) * p
        cum_min = min(cum_min, adj)
        q_vals[orig_idx] = float(min(1.0, max(0.0, cum_min)))
    return q_vals


def probability_of_backtest_overfitting(
    matrix_returns: Any,
    n_partitions: int = 16,
    max_combinations: int = 1000,
) -> dict[str, Any]:
    """
    Combinatorially Symmetric Cross-Validation (CSCV) for Probability of Backtest Overfitting (PBO)
    based on Bailey, Borwein, López de Prado, and Zhu (2017).

    Args:
        matrix_returns: Matrix of shape (T, N) where T = observations and N = trial strategies.
        n_partitions: Number of equal time partitions (must be even, e.g. 8, 12, 16).
        max_combinations: Maximum number of combinations to evaluate to bound computation.

    Returns:
        dict containing:
          - pbo: Probability of Backtest Overfitting in [0.0, 1.0] (PBO > 0.50 indicates severe overfitting)
          - is_overfit: True if pbo > 0.50
          - median_oos_rank: Median percentile rank of the IS-optimal strategy in OOS
          - n_combinations: Number of CSCV combinations evaluated
    """
    import itertools
    import numpy as np

    arr = np.asarray(matrix_returns, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"matrix_returns must be 2-dimensional (T, N), got shape {arr.shape}")

    T, N = arr.shape
    if N < 2:
        return {"pbo": 0.0, "is_overfit": False, "median_oos_rank": 1.0, "n_combinations": 0}

    # Split T into n_partitions chunks
    s = min(n_partitions, T)
    if s % 2 != 0:
        s -= 1
    if s < 4:
        return {"pbo": 0.0, "is_overfit": False, "median_oos_rank": 0.5, "n_combinations": 0}

    indices = np.arange(T)
    chunks = np.array_split(indices, s)

    # Form combinations of size s // 2
    half_s = s // 2
    all_combos = list(itertools.combinations(range(s), half_s))

    if len(all_combos) > max_combinations:
        step = len(all_combos) / max_combinations
        selected_combos = [all_combos[int(i * step)] for i in range(max_combinations)]
    else:
        selected_combos = all_combos

    underperforming_count = 0
    oos_ranks = []

    for is_indices in selected_combos:
        is_set = set(is_indices)
        oos_indices = [idx for idx in range(s) if idx not in is_set]

        is_rows = np.concatenate([chunks[i] for i in is_indices])
        oos_rows = np.concatenate([chunks[j] for j in oos_indices])

        is_mat = arr[is_rows, :]
        oos_mat = arr[oos_rows, :]

        is_mean = np.mean(is_mat, axis=0)
        is_std = np.std(is_mat, axis=0, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            is_sr = np.where(is_std > 1e-12, is_mean / is_std, -np.inf)

        oos_mean = np.mean(oos_mat, axis=0)
        oos_std = np.std(oos_mat, axis=0, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            oos_sr = np.where(oos_std > 1e-12, oos_mean / oos_std, -np.inf)

        best_is_strat = int(np.argmax(is_sr))
        oos_val = oos_sr[best_is_strat]
        valid_oos = oos_sr[~np.isnan(oos_sr) & ~np.isneginf(oos_sr)]
        if len(valid_oos) > 0:
            rank_oos = float(np.sum(valid_oos <= oos_val) / len(valid_oos))
        else:
            rank_oos = 0.5

        oos_ranks.append(rank_oos)
        if rank_oos <= 0.50:
            underperforming_count += 1

    total_eval = len(selected_combos)
    pbo = float(underperforming_count / total_eval) if total_eval > 0 else 0.0
    median_rank = float(np.median(oos_ranks)) if oos_ranks else 0.5

    return {
        "pbo": round(pbo, 4),
        "is_overfit": pbo > 0.50,
        "median_oos_rank": round(median_rank, 4),
        "n_combinations": total_eval,
    }
