import numpy as np
import pandas as pd
import pytest

from indicators.alpha_zoo.vector_factor_engine import (
    VectorFactorEngine,
    VectorFactorResult,
    FactorSignal,
)


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """Generate 60 bars of synthetic OHLCV data."""
    np.random.seed(42)
    n = 60
    close = 1.1000 + np.cumsum(np.random.normal(0, 0.001, n))
    high = close + np.random.uniform(0.0005, 0.0015, n)
    low = close - np.random.uniform(0.0005, 0.0015, n)
    open_p = close + np.random.normal(0, 0.0005, n)
    volume = np.random.uniform(100, 1000, n)

    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


def test_vector_factor_engine_initialization():
    engine = VectorFactorEngine.get_instance()
    assert engine is not None
    factors = engine.get_available_factors()
    assert len(factors) > 0


def test_vector_factor_engine_evaluation(sample_ohlcv_df):
    engine = VectorFactorEngine.get_instance()
    result = engine.evaluate(
        sample_ohlcv_df,
        symbol="EURUSD",
        regime="trending",
        top_k=5,
    )

    assert isinstance(result, VectorFactorResult)
    assert result.symbol == "EURUSD"
    assert result.regime == "trending"
    assert -1.0 <= result.composite_alpha_score <= 1.0
    assert len(result.top_factors) <= 5

    for f in result.top_factors:
        assert isinstance(f, FactorSignal)
        assert -1.0 <= f.signal <= 1.0
        assert -3.0 <= f.z_score <= 3.0
        assert f.direction in ("positive_bullish", "positive_bearish", "neutral_volatility")

    # Verify prompt context formatting
    prompt_str = result.to_prompt_context()
    assert "EURUSD" in prompt_str
    assert "TRENDING" in prompt_str
    assert "Composite Alpha Score" in prompt_str


def test_vector_factor_engine_regime_filtering(sample_ohlcv_df):
    engine = VectorFactorEngine.get_instance()
    
    # Evaluate under ranging regime
    ranging_res = engine.evaluate(sample_ohlcv_df, symbol="USDJPY", regime="ranging", top_k=3)
    assert ranging_res.symbol == "USDJPY"
    assert ranging_res.regime == "ranging"
    assert -1.0 <= ranging_res.composite_alpha_score <= 1.0


def test_vector_factor_engine_empty_or_short_data():
    engine = VectorFactorEngine.get_instance()
    
    empty_df = pd.DataFrame()
    res_empty = engine.evaluate(empty_df, symbol="GBPUSD")
    assert res_empty.factor_count == 0
    assert res_empty.composite_alpha_score == 0.0
    assert "Insufficient data" in res_empty.to_prompt_context()

    short_df = pd.DataFrame({"close": [1.0, 1.1, 1.2]})
    res_short = engine.evaluate(short_df, symbol="GBPUSD")
    assert res_short.factor_count == 0
