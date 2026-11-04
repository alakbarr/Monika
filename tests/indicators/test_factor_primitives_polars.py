# ==============================================================================
# File: tests/indicators/test_factor_primitives_polars.py
# Description: Tests for Polars-Accelerated Factor Primitives
# ==============================================================================

import numpy as np
import pandas as pd
import polars as pl
import pytest

from monika.domain.indicators.factor_primitives import (
    decay_linear,
    delta,
    safe_div,
    ts_max,
    ts_mean,
    ts_min,
    ts_std,
    ts_sum,
)


def test_safe_div_polars_expr_and_series():
    # Polars Expr
    df = pl.DataFrame(
        {
            "a": [10.0, 20.0, 30.0, 40.0],
            "b": [2.0, 0.0, -5.0, None],
        }
    )
    expr_res = df.select(safe_div(pl.col("a"), pl.col("b")).alias("div"))
    vals = expr_res["div"].to_list()
    assert abs(vals[0] - 5.0) < 1e-6
    assert vals[1] is None  # Zero guard strictly returns None/NaN
    assert abs(vals[2] - (-6.0)) < 1e-6
    assert vals[3] is None  # Null guard strictly returns None/NaN

    # Polars Series
    s_a = pl.Series("a", [10.0, 20.0, 0.0])
    s_b = pl.Series("b", [2.0, 0.0, 5.0])
    s_res = safe_div(s_a, s_b)
    assert isinstance(s_res, pl.Series)
    assert abs(s_res[0] - 5.0) < 1e-6
    assert s_res[1] is None
    assert s_res[2] == 0.0


def test_decay_linear_polars():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    df = pl.DataFrame({"x": data})

    # Polars Expr
    res_expr = df.select(decay_linear(pl.col("x"), 3).alias("dl"))
    vals = res_expr["dl"].to_list()
    assert vals[0] is None  # Warmup
    assert vals[1] is None  # Warmup
    # Index 2: (3*3 + 2*2 + 1*1)/6 = 14/6 = 2.333333
    assert abs(vals[2] - 14.0 / 6.0) < 1e-5

    # Polars Series
    s_x = pl.Series("x", data)
    s_res = decay_linear(s_x, 3)
    assert isinstance(s_res, pl.Series)
    assert s_res[0] is None
    assert s_res[1] is None
    assert abs(s_res[2] - 14.0 / 6.0) < 1e-5


def test_delta_polars():
    data = [10.0, 15.0, 12.0, 20.0]
    df = pl.DataFrame({"x": data})

    res = df.select(delta(pl.col("x"), 1).alias("d1"))
    vals = res["d1"].to_list()
    assert vals[0] is None
    assert vals[1] == 5.0
    assert vals[2] == -3.0
    assert vals[3] == 8.0

    # Lookahead guard
    with pytest.raises(ValueError, match="delta lag must be >= 1"):
        delta(pl.col("x"), 0)


def test_rolling_primitives_polars():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    df = pl.DataFrame({"x": data})

    res = df.select(
        [
            ts_mean(pl.col("x"), 3).alias("mean"),
            ts_std(pl.col("x"), 3).alias("std"),
            ts_sum(pl.col("x"), 3).alias("sum"),
            ts_min(pl.col("x"), 3).alias("min"),
            ts_max(pl.col("x"), 3).alias("max"),
        ]
    )

    assert res["mean"][0] is None
    assert res["mean"][1] is None
    assert res["mean"][2] == 2.0
    assert res["sum"][2] == 6.0
    assert res["min"][2] == 1.0
    assert res["max"][2] == 3.0
    assert abs(res["std"][2] - 1.0) < 1e-6


def test_factor_primitives_numerical_parity_with_pandas():
    np.random.seed(42)
    raw = np.random.randn(100).cumsum() + 100.0

    df_pd = pd.Series(raw, name="close")
    s_pl = pl.Series("close", raw)

    # ts_mean parity
    mean_pd = ts_mean(df_pd, 10).values
    mean_pl = ts_mean(s_pl, 10).to_numpy()
    np.testing.assert_allclose(mean_pd[9:], mean_pl[9:], rtol=1e-5)

    # ts_sum parity
    sum_pd = ts_sum(df_pd, 10).values
    sum_pl = ts_sum(s_pl, 10).to_numpy()
    np.testing.assert_allclose(sum_pd[9:], sum_pl[9:], rtol=1e-5)

    # decay_linear parity
    dl_pd = decay_linear(df_pd, 10).values
    dl_pl = decay_linear(s_pl, 10).to_numpy()
    np.testing.assert_allclose(dl_pd[9:], dl_pl[9:], rtol=1e-5)
