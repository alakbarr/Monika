import pytest
from analysis.calculators.stage1_priced_in import calculate_stage1_priced_in_baseline

def test_stage1_priced_in_baseline_eurusd_extreme():
    result = calculate_stage1_priced_in_baseline("EURUSD", 95.0, 25.0)
    assert result["is_priced_in"] is True
    assert "reasons" in result
    assert "COT positioning is extremely long (Priced-in for downside)" in result["reasons"]
    assert "Retail is heavily short (25.0%)" in result["reasons"]

def test_stage1_priced_in_baseline_usd_jpy_extreme():
    result = calculate_stage1_priced_in_baseline("USDJPY", 5.0, 75.0)
    assert result["is_priced_in"] is True
    assert "COT positioning is extremely short (Priced-in for upside)" in result["reasons"]
    assert "Retail is heavily long (75.0%)" in result["reasons"]

def test_stage1_priced_in_baseline_not_extreme():
    result = calculate_stage1_priced_in_baseline("GBPUSD", 50.0, 50.0)
    assert result["is_priced_in"] is False
    assert len(result["reasons"]) == 0

def test_stage1_priced_in_baseline_no_retail():
    result = calculate_stage1_priced_in_baseline("AUDUSD", 50.0)
    assert result["is_priced_in"] is False
    assert len(result["reasons"]) == 0
