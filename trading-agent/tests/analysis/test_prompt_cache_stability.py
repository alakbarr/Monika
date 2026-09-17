import pytest
from unittest.mock import MagicMock
from analysis.stages.per_asset_stage import PerAssetStage


def test_stage2_system_prompt_cache_stability_across_symbols():
    """
    Ensure static system prompts generated across all symbols (Forex, Gold, Crypto, Oil)
    are 100% byte-for-byte identical to guarantee KV-cache hit rate >90%.
    """
    settings = {
        "trading": {
            "caveman_mode": True,
            "risk": {"min_rr_ratio": 1.3}
        }
    }
    stage = PerAssetStage(settings)
    
    symbols_to_test = [
        ("EURUSD", "099741", 8),
        ("GBPUSD", "096742", 8),
        ("USDJPY", "097741", 8),
        ("XAUUSD", "088691", 9),
        ("BTCUSD", None, 8),
        ("XTIUSD", "067651", 8),
        ("XBRUSD", "067655", 8),
    ]
    
    static_prompts = []
    dynamic_prompts = []
    
    for sym, cot, thresh in symbols_to_test:
        prompt_res, abort_res = stage._compose_stage2_system_prompt(
            symbol=sym,
            cot_code=cot,
            effective_threshold=thresh,
            tool_order_guidance="DATA SUDAH TERSEDIA"
        )
        assert abort_res is None
        assert isinstance(prompt_res, tuple)
        static_sys, dyn_sys = prompt_res
        
        static_prompts.append(static_sys)
        dynamic_prompts.append(dyn_sys)
    
    # 1. Verifikasi seluruh static prompt 100% identik
    first_static = static_prompts[0]
    for i, p in enumerate(static_prompts[1:], 1):
        sym = symbols_to_test[i][0]
        assert p == first_static, f"Static prompt untuk {sym} berbeda dari EURUSD! Cache akan bust!"
        
    # 2. Verifikasi dynamic prompt memuat info simbol masing-masing
    for i, dyn in enumerate(dynamic_prompts):
        sym = symbols_to_test[i][0]
        assert f"Symbol: {sym}" in dyn, f"Dynamic prompt tidak memuat Symbol: {sym}"
