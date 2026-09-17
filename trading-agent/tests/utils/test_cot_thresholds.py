import pytest
from utils.calibration.cot_thresholds import cot_extreme_score

def test_cot_extreme_score_eurusd():
    assert cot_extreme_score("EURUSD", 90.0) == -1
    assert cot_extreme_score("EURUSD", 80.0) == -1
    assert cot_extreme_score("EURUSD", 75.0) == 0
    assert cot_extreme_score("EURUSD", 50.0) == 0

def test_is_cot_extreme_usdjpy():
    assert cot_extreme_score("USDJPY", 5.0) == 1
    assert cot_extreme_score("USDJPY", 50.0) == 0

def test_cot_extreme_score_gold():
    assert cot_extreme_score("XAUUSD", 96.0) == -1
    assert cot_extreme_score("XAUUSD", 90.0) == -1
    assert cot_extreme_score("XAUUSD", 85.0) == -1
    assert cot_extreme_score("XAUUSD", 50.0) == 0
