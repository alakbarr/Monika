import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture_json(filename: str) -> dict:
    path = FIXTURES_DIR / filename
    if not path.exists():
        if not filename.endswith(".json"):
            path = FIXTURES_DIR / f"{filename}.json"
    if not path.exists():
        logger.warning(f"Fixture file not found: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_synthetic_market_snapshot() -> dict:
    return load_fixture_json("_market_snapshot_2026_09.json")


def get_synthetic_stage1_bundle() -> str:
    snap = get_synthetic_market_snapshot()
    if not snap:
        return "GLOBAL MACRO SNAPSHOT: EURUSD=1.1377, XAUUSD=4260, Fed=3.75-4.00%, ECB=2.50%, VIX=15.68, Brent=$106."
    lines = [
        "=== GLOBAL MACROECONOMIC SNAPSHOT (SEPTEMBER 2026) ===",
        f"As of: {snap.get('as_of_date', '2026-09-25')}",
        f"FX Prices: {json.dumps(snap.get('fx_prices', {}))}",
        f"Volatility: {json.dumps(snap.get('volatility', {}))}",
        f"Central Bank Policy: {json.dumps(snap.get('central_banks', {}))}",
        f"Inflation Data: {json.dumps(snap.get('inflation_data', {}))}",
        f"Commodities: {json.dumps(snap.get('commodities', {}))}",
        f"Geopolitical Developments: {json.dumps(snap.get('geopolitical', {}))}",
        "======================================================="
    ]
    return "\n".join(lines)


def get_synthetic_stage2_bundle(symbol: str = "EURUSD") -> tuple[str, dict]:
    sym = (symbol or "EURUSD").upper()
    filename_map = {
        "EURUSD": "smc_eurusd_h1_bull_displacement.json",
        "GBPUSD": "smc_gbpusd_h1_choppy_trap.json",
        "XAUUSD": "smc_xauusd_m15_bear_sweep.json",
    }
    fname = filename_map.get(sym, "smc_eurusd_h1_bull_displacement.json")
    fix = load_fixture_json(fname)
    if not fix:
        fix = {
            "symbol": sym,
            "current_price": 1.1377,
            "technical_context": {"structure": "BOS_BULLISH", "order_block": {"low": 1.1350, "high": 1.1365}},
            "macro_context": {"fed_rate": "3.75-4.00%", "ecb_rate": "2.50%", "vix": 15.68}
        }
    text_bundle = (
        f"=== ASSET ANALYSIS BUNDLE: {sym} ===\n"
        f"Timeframe: {fix.get('timeframe', 'H1')}\n"
        f"Current Price: {fix.get('current_price')}\n"
        f"Market Regime: {fix.get('market_regime', 'low_volatility_bull')}\n"
        f"Technical Structure: {json.dumps(fix.get('technical_context', {}))}\n"
        f"Macro Background: {json.dumps(fix.get('macro_context', {}))}\n"
        f"Account State: {json.dumps(fix.get('account_state', {}))}\n"
        "====================================="
    )
    raw_dict = {
        "symbol": sym,
        "current_price": fix.get("current_price"),
        "technical": fix.get("technical_context", {}),
        "macro": fix.get("macro_context", {}),
        "account": fix.get("account_state", {}),
        "fixture_id": fix.get("fixture_id")
    }
    return text_bundle, raw_dict


def get_synthetic_fundamental_brief() -> dict:
    snap = get_synthetic_market_snapshot()
    return {
        "macro_narrative": "Transatlantic policy divergence persists with US Fed hawkish at 3.75-4.00% while ECB remains constrained at 2.50%. Strait of Hormuz conflict pushes crude to $106, exerting imported inflation pressure globally.",
        "currency_bias": {"USD": "bullish", "EUR": "bearish", "GBP": "neutral", "JPY": "bullish", "XAU": "bullish"},
        "currency_confidence": {"USD": "HIGH", "EUR": "HIGH", "GBP": "MEDIUM", "JPY": "MEDIUM", "XAU": "HIGH"},
        "risk_sentiment": "selective_risk_off",
        "confidence": 0.82,
        "strongest_counter_thesis": "Potential de-escalation in Middle East could collapse crude back to $85, rapidly shifting market focus to Fed terminal rate easing."
    }


def get_synthetic_news_items() -> list[dict]:
    hormuz = load_fixture_json("news_hormuz_escalation.json")
    nfp = load_fixture_json("news_nfp_release.json")
    items = []
    if hormuz and "news_items" in hormuz:
        items.extend(hormuz["news_items"])
    if nfp and "news_items" in nfp:
        items.extend(nfp["news_items"])
    return items


def get_synthetic_risk_context(symbol: str = "EURUSD") -> dict:
    fix = load_fixture_json("risk_eurusd_spread_spike.json")
    return {
        "symbol": symbol,
        "decision": "BUY",
        "confluence_score": 11,
        "priced_in_score": 3,
        "rr_ratio": 1.96,
        "sl_beyond_structure": True,
        "actual_risk_state": {
            "daily_pnl_pct": -0.2,
            "open_positions": 1,
            "portfolio_heat_pct": 1.0
        }
    }
