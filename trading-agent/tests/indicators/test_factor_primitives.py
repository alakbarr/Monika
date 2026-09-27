import pytest
import numpy as np
import pandas as pd
from indicators.factor_primitives import (
    safe_div,
    rank,
    zscore,
    scale,
    delta,
    signed_power,
    ts_rank,
    ts_corr,
    ts_cov,
    ts_mean,
    ts_std,
    ts_max,
    ts_min,
    ts_argmax,
    ts_argmin,
    decay_linear,
    observed_over,
)


def test_safe_div():
    # scalar
    assert np.isnan(safe_div(10.0, 0.0))
    assert safe_div(10.0, 2.0) == pytest.approx(5.0)
    
    # dataframe
    df_a = pd.DataFrame({"x": [10.0, 20.0, 30.0], "y": [4.0, 5.0, 6.0]})
    df_b = pd.DataFrame({"x": [2.0, 0.0, 5.0], "y": [2.0, np.nan, 3.0]})
    res = safe_div(df_a, df_b)
    assert res.loc[0, "x"] == pytest.approx(5.0)
    assert np.isnan(res.loc[1, "x"])
    assert res.loc[2, "x"] == pytest.approx(6.0)
    assert np.isnan(res.loc[1, "y"])


def test_delta_lookahead_ban():
    df = pd.DataFrame({"c": [1.0, 2.0, 3.0, 5.0]})
    with pytest.raises(ValueError, match="lookahead violation"):
        delta(df, 0)
    with pytest.raises(ValueError, match="lookahead violation"):
        delta(df, -1)
    d1 = delta(df, 1)
    assert np.isnan(d1.iloc[0, 0])
    assert d1.iloc[1, 0] == pytest.approx(1.0)
    assert d1.iloc[3, 0] == pytest.approx(2.0)


def test_decay_linear():
    df = pd.DataFrame({"s": [1.0, 2.0, 3.0, 4.0, 5.0]})
    # window=3, weights = [3, 2, 1] / 6 = [0.5, 0.333333, 0.166667]
    dl = decay_linear(df, 3)
    assert np.isnan(dl.iloc[0, 0])
    assert np.isnan(dl.iloc[1, 0])
    # at row 2 (values 1, 2, 3), decay_linear = (3*3 + 2*2 + 1*1)/6 = (9 + 4 + 1)/6 = 14/6 = 2.333333
    assert dl.iloc[2, 0] == pytest.approx(14.0 / 6.0)
    # at row 3 (values 2, 3, 4), decay_linear = (4*3 + 3*2 + 2*1)/6 = (12 + 6 + 2)/6 = 20/6 = 3.333333
    assert dl.iloc[3, 0] == pytest.approx(20.0 / 6.0)


def test_ts_rank():
    df = pd.DataFrame({"s": [10.0, 20.0, 15.0, 30.0, 25.0]})
    tr = ts_rank(df, 3)
    assert np.isnan(tr.iloc[0, 0])
    assert np.isnan(tr.iloc[1, 0])
    # window [10, 20, 15]: last value is 15. Less: [10] (1), Eq: [15] (1). rank_avg = 1 + 0.5*2 = 2.0. pct = 2/3 ≈ 0.6667
    assert tr.iloc[2, 0] == pytest.approx(2.0 / 3.0)


def test_ts_argmax_argmin():
    df = pd.DataFrame({"s": [10.0, 30.0, 20.0, 5.0, 40.0]})
    # window 3:
    # row 2: [10, 30, 20] -> max is 30 at index 1, min is 10 at index 0
    t_max = ts_argmax(df, 3)
    t_min = ts_argmin(df, 3)
    assert t_max.iloc[2, 0] == 1.0
    assert t_min.iloc[2, 0] == 0.0


def test_zscore_and_scale():
    df = pd.DataFrame({
        "a": [1.0, 2.0, 10.0],
        "b": [3.0, 2.0, 20.0],
        "c": [5.0, 2.0, 30.0],
    })
    zs = zscore(df)
    # row 0: [1, 3, 5], mean=3, std=2 -> zscores: -1, 0, 1
    assert zs.iloc[0, 0] == pytest.approx(-1.0)
    assert zs.iloc[0, 1] == pytest.approx(0.0)
    assert zs.iloc[0, 2] == pytest.approx(1.0)
    # row 1 has 0 std -> must be NaN (never silent 0)
    assert np.isnan(zs.iloc[1, 0])
    assert np.isnan(zs.iloc[1, 1])

    sc = scale(df, a=1.0)
    assert sc.iloc[0].abs().sum() == pytest.approx(1.0)
