import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from analysis.calculators.leading_indicator_mapper import LeadingIndicatorMapper
from analysis.calculators.garch_volatility import GarchVolatilityEngine
from analysis.calculators.taylor_rule import TaylorRuleCalculator
from analysis.calculators.timesfm_residual_validator import TimesFMResidualValidator
from data_sources.fred_treasury_yield import TENOR_SERIES, SERIES_TO_TENOR

def test_leading_indicator_mapper():
    # Test PCE nowcast
    res_pce = LeadingIndicatorMapper.nowcast_pce(
        cpi_core_mom=0.35,
        ppi_core_mom=0.40,
        ppi_airfares_mom=2.5,
        ppi_portfolio_mgmt_mom=1.8,
        cpi_shelter_mom=0.45,
        consensus_core_pce=0.20
    )
    assert res_pce.projection_category == "BEAT"
    assert res_pce.delta_vs_consensus > 0
    assert len(res_pce.evidence_chain) == 4
    assert "XAUUSD (Gold)" in res_pce.transmission_map
    assert "BEARISH" in res_pce.transmission_map["XAUUSD (Gold)"]["impact"]

    # Test NFP nowcast
    res_nfp = LeadingIndicatorMapper.nowcast_nfp(
        adp_change_k=110.0,
        jobless_claims_4w_avg_k=245.0,
        ism_services_employment=47.5,
        consensus_nfp_k=180.0
    )
    assert res_nfp.projection_category == "MISS"
    assert res_nfp.delta_vs_consensus < 0

def test_taylor_rule():
    res = TaylorRuleCalculator.calculate_fed_taylor_rule(
        actual_effr=5.33,
        current_inflation=2.8,
        unemployment_rate=4.2,
        r_star=1.0
    )
    assert res.central_bank == "Federal Reserve"
    assert res.policy_stance == "OVERLY RESTRICTIVE"
    assert res.rate_gap > 0
    assert "USD (DXY)" in res.market_implications

def test_garch_volatility():
    np.random.seed(42)
    returns = np.random.normal(0, 0.015, 150)
    res = GarchVolatilityEngine.estimate_garch11(returns, is_returns=True)
    assert res.status == "SUCCESS"
    assert res.persistence > 0
    assert res.annualized_forecast_vol > 0

def test_timesfm_residuals():
    np.random.seed(42)
    actual = np.linspace(100, 110, 50) + np.random.normal(0, 0.5, 50)
    # Lagged prediction produces positive autocorrelation
    pred = pd.Series(actual).shift(1).bfill().values
    res = TimesFMResidualValidator.validate_residuals(actual, pred)
    assert res.status == "SUCCESS"
    assert res.durbin_watson_stat > 0
    assert res.sample_size == 50

def test_fred_series_extensions():
    assert "DGS3MO" in TENOR_SERIES
    assert "ACMTP10" in TENOR_SERIES
    assert "CUSR0000SACL1E" in TENOR_SERIES
    assert SERIES_TO_TENOR["DGS3MO"] == "3M"
    assert SERIES_TO_TENOR["ACMTP10"] == "10Y_TERM_PREMIUM"
    assert SERIES_TO_TENOR["CUSR0000SACL1E"] == "SUPERCORE_CPI"

if __name__ == "__main__":
    test_leading_indicator_mapper()
    test_taylor_rule()
    test_garch_volatility()
    test_timesfm_residuals()
    test_fred_series_extensions()
    print("ALL FASE 3 QUANTITATIVE & MACRO TESTS PASSED!")
