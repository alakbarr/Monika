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
