# ==============================================================================
# File: benchmark/fixture_loader.py
# ==============================================================================
"""
Fixture Loader for Monika LLM Benchmark Harness.
Provides structured access to authentic Golden Production Fixtures (anchored to 2026-10-01)
across all 8 architectural layers of Monika.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture_json(filename: str, default: Any = None) -> Any:
    """Loads a JSON fixture by filename, searching root and subdirectories."""
    # 1. Direct path
    path = FIXTURES_DIR / filename
    if not path.exists() and not filename.endswith(".json"):
        path = FIXTURES_DIR / f"{filename}.json"

    # 2. Search in subdirectories if not found directly
    if not path.exists():
        fname = Path(filename).name
        if not fname.endswith(".json"):
            fname = f"{fname}.json"
        for sub in ["macro", "per_asset", "specialists", "debate", "risk", "news", "system1_jev", "omnichannel"]:
            sub_path = FIXTURES_DIR / sub / fname
            if sub_path.exists():
                path = sub_path
                break

    if not path.exists():
        logger.warning(f"Fixture file not found: {filename} in {FIXTURES_DIR}")
        return default if default is not None else {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading fixture {path}: {e}")
        return default if default is not None else {}


# ==============================================================================
# Layer 1: Macro & Fundamental Golden Loaders
# ==============================================================================


def get_golden_macro_stage1() -> dict:
    """Returns the full Golden Macro Snapshot from 2026-10-01."""
    return load_fixture_json("macro/golden_macro_stage1_20261001.json")


def get_golden_escalation_crisis() -> dict:
    """Returns the geopolitical crisis escalation test case."""
    return load_fixture_json("macro/escalation_geopolitical_crisis.json")


def get_golden_shadow_check_audit() -> dict:
    """Returns the shadow check audit scenario with injected bias."""
    return load_fixture_json("macro/shadow_check_audit_case.json")


def get_synthetic_market_snapshot() -> dict:
    """Backwards-compatible helper returning market snapshot."""
    golden = dict(get_golden_macro_stage1())
    if golden:
        if "volatility" not in golden:
            vix_val = golden.get("macro_indicators", {}).get("vix", {}).get("value", 15.68)
            golden["volatility"] = {"vix": vix_val}
        if "fx_prices" not in golden:
            golden["fx_prices"] = {
                "EURUSD": 1.1377,
                "GBPUSD": 1.3325,
                "USDJPY": 144.20,
                "XAUUSD": 4260.00,
                "BTCUSD": 63400.0,
                "XTIUSD": 71.85,
            }
        return golden
    return load_fixture_json("_market_snapshot_2026_09.json")


def get_stage1_fixture_bundle_dict() -> dict:
    """Returns the parsed dictionary of the full production Stage 1 fixture bundle."""
    return load_fixture_json("macro/full_production_stage1_bundle.json", default={})


def get_synthetic_stage1_bundle() -> str:
    """Realistic production-scale stage 1 data bundle formatted from Golden Snapshot or Full Production Bundle."""
    full_bundle = load_fixture_json("macro/full_production_stage1_bundle.json")
    if full_bundle and "formatted_text_bundle" in full_bundle:
        return full_bundle["formatted_text_bundle"]

    golden = get_golden_macro_stage1()
    macro_ind = golden.get("macro_indicators", {})
    dxy = macro_ind.get("dxy", {}).get("value", 101.48)
    vix = macro_ind.get("vix", {}).get("value", 16.70)
    us10y = macro_ind.get("us10y_yield", {}).get("value", 3.82)
    us2y = macro_ind.get("us02y_yield", {}).get("value", 3.65)
    crude = macro_ind.get("wti_crude", {}).get("value", 71.85)

    # Format news
    news_lines = []
    for i, it in enumerate(golden.get("high_impact_news", []), 1):
        news_lines.append(
            f"[{i}] [{it.get('impact', 'HIGH')}] {it.get('title', '')} "
            f"(Source: {it.get('source', 'news')}, Published: {it.get('published_at', '2026-10-01')}) - {it.get('summary', '')}"
        )
    news_block = "\n".join(news_lines)

    # Format calendar
    cal_lines = []
    for ev in golden.get("upcoming_calendar", [])[:20]:
        cal_lines.append(
            f"- [{ev.get('currency', 'USD')}] {ev.get('event', '')}: "
            f"Actual: {ev.get('actual', 'N/A')} | Forecast: {ev.get('forecast', 'N/A')} | Previous: {ev.get('previous', 'N/A')} "
            f"({ev.get('impact', 'MEDIUM')})"
        )
    cal_block = "\n".join(cal_lines)

    lines = [
        "=== GLOBAL MACROECONOMIC SNAPSHOT & PREFETCH BUNDLE (OCTOBER 2026 BENCHMARK GROUND TRUTH) ===",
        "As of Timestamp: 2026-10-04T19:00:00Z",
        "",
        "--- [CENTRAL_BANK_RATES & EXPECTATIONS] ---",
        "Fed Funds Target: 3.75% - 4.00% (Hawkish hold, pause/cut trajectory delayed to 2027)",
        "ECB Deposit Facility: 2.50% (Constrained by imported energy inflation)",
        "Bank of Japan Policy Rate: 1.25% (Hawkish normalization, carry trade unwinding risk)",
        "Bank of England Bank Rate: 3.75% (Split 6-3, stagflationary wage pressure)",
        "Reserve Bank of Australia: 4.10% (Hawkish)",
        "",
        "--- [SOVEREIGN BOND YIELDS & SPREADS] ---",
        f"US 10-Year: {us10y}% | US 2-Year: {us2y}% | 10Y-2Y Spread: +17.0 bps (un-inverting)",
        "DE 10-Year: 2.38% | DE 2-Year: 2.15% | US-DE 10Y Spread: +144 bps (Dollar positive)",
        "UK 10-Year: 4.18% | JP 10-Year: 1.15%",
        "",
        "--- [CME FEDWATCH PROBABILITIES] ---",
        "Next FOMC Meeting: 25 bps Cut (18.0%), Hold at 3.75-4.00% (82.0%), Hike (0.0%)",
        "",
        "--- [INTERMARKET METRICS & COMMODITIES] ---",
        f"US Dollar Index (DXY): {dxy} (-0.28%) | Retest of key 101.40-101.80 support/resistance",
        f"CBOE Volatility Index (VIX): {vix} | Regime: Normal / Selective Volatility",
        f"WTI Crude (XTIUSD): ${crude}/bbl (+2.4%) | Catalyst: Middle East Supply Concerns",
        "Spot Gold (XAUUSD): $2,658.50/oz | Institutional Safe-Haven & All-Time-High Consolidation",
        "Bitcoin (BTCUSD): $84,200.00 (-1.2%)",
        "",
        "--- [HIGH-IMPACT ECONOMIC CALENDAR RELEASES] ---",
        cal_block,
        "",
        "--- [CFTC COMMITMENTS OF TRADERS (COT) INSTITUTIONAL POSITIONING] ---",
        "EUR: Leveraged Net Short -62,400 contracts | Asset Managers neutral",
        "USD: Asset Manager Net Long 48,200 contracts (72nd percentile)",
        "JPY: Massive Short Covering rally | Unwinding carry trades",
        "XAU: Money Managers holding near-record long +218,000 contracts",
        "",
        "--- [MARKET SENTIMENT & RETAIL POSITIONING (MYFXBOOK & FXSSI)] ---",
        "EURUSD: 74.2% Long (Retail attempting to buy dip) -> Contrarian Bearish Signal",
        "GBPUSD: 83.0% Long -> Contrarian Bearish Signal",
        "USDJPY: 76.7% Short -> Contrarian Bullish Signal",
        "XAUUSD: 56.5% Long / 43.5% Short -> Neutral / Slight Contrarian Bearish",
        "",
        f"--- [AGGREGATED FINANCIAL & GEOPOLITICAL NEWS BRIEFING ({len(golden.get('high_impact_news', []))} REAL ARTICLES)] ---",
        news_block,
        "=================================================================================",
    ]
    return "\n".join(lines)


def get_synthetic_fundamental_brief() -> dict:
    """Returns production-grade FundamentalBrief dictionary."""
    golden = get_golden_macro_stage1()
    brief = golden.get("fundamental_brief", {}).get("structured_json")
    if brief:
        return brief
    return {
        "macro_bias": "bearish",
        "macro_narrative": "Transatlantic policy divergence persists with US Fed hawkish at 3.75-4.00% while ECB remains constrained at 2.50%. Middle East geopolitical risk adds premium to crude and gold.",
        "macro_regime": "risk_off",
        "currency_bias": {
            "USD": "bullish",
            "EUR": "bearish",
            "GBP": "bearish",
            "JPY": "bullish",
            "AUD": "bearish",
            "OIL": "bullish",
            "BTC": "bullish",
            "XAU": "bullish",
        },
        "currency_confidence": {
            "USD": 0.85,
            "EUR": 0.80,
            "GBP": 0.70,
            "JPY": 0.75,
            "AUD": 0.70,
            "OIL": 0.80,
            "BTC": 0.65,
            "XAU": 0.85,
        },
        "invalidation_conditions": {
            "EUR": "EURUSD D1 close above 1.1150 with ECB emergency rate hike",
            "USD": "US Core PCE dropping below 2.5% YoY with 50bps rate cut",
        },
        "risk_sentiment": "selective_risk_off",
        "confidence": 0.82,
        "priced_in_assessment": {
            "dominant_driver": "Fed higher-for-longer policy combined with energy volatility",
            "priced_in_score": 7,
            "sell_the_news_risk": "medium",
        },
    }


# ==============================================================================
# Layer 2: Per-Asset Pipeline Golden Loaders
# ==============================================================================


def get_golden_asset_bundle(symbol: str = "EURUSD") -> dict:
    """Returns the per-asset golden bundle JSON."""
    sym = (symbol or "EURUSD").upper()
    bundle = load_fixture_json(f"per_asset/{sym.lower()}_golden_bundle.json")
    if bundle:
        return bundle
    return load_fixture_json("per_asset/eurusd_golden_bundle.json")


def get_golden_prescreen_matrix() -> dict:
    """Returns the multi-asset prescreen matrix for stage2_prescreen."""
    return load_fixture_json("per_asset/prescreen_multi_asset_matrix.json")


def get_synthetic_stage2_bundle(symbol: str = "EURUSD") -> Tuple[str, dict]:
    """Generates formatted string bundle and raw dictionary matching PerAssetStage._SPECIALIST_KEY_MAP."""
    sym = (symbol or "EURUSD").upper()
    bundles = load_fixture_json("per_asset/full_production_stage2_bundles.json")
    if bundles and sym in bundles:
        asset_b = dict(bundles[sym])
        if "technical" not in asset_b:
            asset_b["technical"] = asset_b.get("technical_slice") or asset_b.get("get_technical_indicators_H4") or {}
        return asset_b.get("formatted_text_bundle", ""), asset_b

    bundle = get_golden_asset_bundle(sym)
    if bundle and "formatted_text_bundle" in bundle:
        return bundle.get("formatted_text_bundle", ""), bundle

    price = bundle.get("current_price", 1.1065 if sym == "EURUSD" else 2658.0)
    ind = bundle.get("indicators", {})
    h4 = ind.get("H4", {})
    h1 = ind.get("H1", {})
    m15 = ind.get("M15", {})
    smc = bundle.get("smc_zones", {})

    prec = (
        5
        if "JPY" not in sym and sym not in ("XAUUSD", "BTCUSD", "XTIUSD")
        else (2 if sym in ("XAUUSD", "USDJPY") else (1 if sym == "BTCUSD" else 3))
    )

    fvg_lines = []
    for f in smc.get("unmitigated_fvg", []):
        fvg_lines.append(
            f"- [{f.get('tf', 'H4')}] {f.get('direction', 'BULLISH')} FVG: Top={f.get('gap_high', 0):.{prec}f}, Bottom={f.get('gap_low', 0):.{prec}f}"
        )
    fvg_text = (
        "\n".join(fvg_lines)
        if fvg_lines
        else f"- [{sym}] Unmitigated H4 FVG: {price * 0.998:.{prec}f} to {price * 0.996:.{prec}f}"
    )

    ob_lines = []
    for ob in smc.get("order_blocks", []):
        ob_lines.append(
            f"- [{ob.get('tf', 'H4')}] {ob.get('direction', 'DEMAND')} Order Block: High={ob.get('price_high', 0):.{prec}f}, Low={ob.get('price_low', 0):.{prec}f}"
        )
    ob_text = (
        "\n".join(ob_lines)
        if ob_lines
        else f"- [{sym}] Demand Order Block: {price * 0.995:.{prec}f} to {price * 0.992:.{prec}f}"
    )

    text_bundle = f"""=== ASSET ANALYSIS BUNDLE: {sym} ===
### PRE-FETCHED DATA BUNDLE: {sym} (GOLDEN PRODUCTION SNAPSHOT 2026-10-01)
TEMPORAL CONSISTENCY LOCK: All data below fetched in consistent cycle window.

--- MULTI-TIMEFRAME OHLCV PRICE METRICS ---
Symbol: {sym}
Current Market Price: {price:.{prec}f}
H4 Trend: {h4.get("trend_ema", "BULLISH")} (EMA20={h4.get("ema_20", 0):.{prec}f}, EMA50={h4.get("ema_50", 0):.{prec}f}, EMA200={h4.get("ema_200", 0):.{prec}f})
H4 RSI: {h4.get("rsi", 54.2)} | ADX: {h4.get("adx_14", 31.4)} | ATR 14 (H4): {h4.get("atr_14", 0.0055)}
H1 Intraday Structure: {h1.get("trend_ema", "PULLBACK")} | RSI: {h1.get("rsi", 48.6)}
M15 Execution Structure: {m15.get("structure", "CHoCH_BULLISH_RETEST")} | ATR: {m15.get("atr_14", 0.0012)}

--- SMART MONEY CONCEPTS (SMC / ICT) STRUCTURE ---
Fair Value Gaps (FVG unmitigated):
{fvg_text}

Institutional Order Blocks:
{ob_text}

--- MACRO / FUNDAMENTAL CONTEXT LINK ---
Target Currency Macro Bias: USD=BULLISH (+0.85), EUR=BEARISH (-0.75)
Fed Policy Rate: 3.75-4.00% | VIX: 16.70
Retail Sentiment: 74.2% Long (Contrarian Bearish Headwind)
COT Commercial Bias: Net Short Hedging

--- ACCOUNT RISK PARAMETERS & GATES (FBS-DEMO) ---
Account Balance: $76,849.91 | Free Margin: $75,200.00
Daily PnL: -$350.00 | Max Permitted Daily Drawdown: $1,500.00 (2.0%)
Open Trades: 2 | Maximum Risk Per Trade: 1.0% ($750.00)
=================================================================================
"""

    raw_dict = {
        "symbol": sym,
        "current_price": price,
        "technical": h4,
        "get_technical_indicators_H4": h4,
        "get_technical_indicators_H1": h1,
        "get_atr_H4": {"atr_14": h4.get("atr_14", 0.0055)},
        "get_smc_zones_H4": smc,
        "market_regime": "TRENDING_EXPANSION" if h4.get("adx_14", 0) > 25 else "RANGING_COMPRESSION",
        "cot_report": load_fixture_json("macro/cot_institutional_report.json"),
        "retail_sentiment": {"long_pct": 74.2, "short_pct": 25.8},
        "get_fundamental_brief": get_synthetic_fundamental_brief(),
        "get_dxy": {"latest": 101.48, "trend_5d": "pullback_retest"},
        "get_vix": {"latest": 16.70, "regime": "normal"},
        "account": {"balance": 76849.91, "equity": 76849.91, "free_margin": 75200.0},
        "fixture_id": f"golden_production_{sym.lower()}",
    }
    return text_bundle, raw_dict


# ==============================================================================
# Layer 3: Specialists & Pattern Similarity Loaders
# ==============================================================================


def get_golden_technical_indicators() -> dict:
    """Returns technical multi-timeframe indicator summary."""
    return load_fixture_json("specialists/technical_multi_tf_indicators.json")


def get_golden_sentiment_matrix() -> dict:
    """Returns retail vs institutional sentiment matrix."""
    return load_fixture_json("specialists/sentiment_cot_retail_matrix.json")


def get_golden_pattern_case() -> dict:
    """Returns the historical pattern match case (2024 EURUSD match vs 2026-10-01)."""
    return load_fixture_json("specialists/pattern_historical_match_case.json")


# ==============================================================================
# Layer 4: Dialectical Debate & Adjudication Loaders
# ==============================================================================


def get_golden_debate_case(symbol: str = "EURUSD") -> dict:
    """Returns real Bull vs Bear dialectical clash."""
    return load_fixture_json("debate/eurusd_dialectical_clash.json")


def get_golden_adjudication_case() -> dict:
    """Returns the Technical vs Macro conflict case for stage2_adjudicator."""
    return load_fixture_json("debate/stage2_adjudication_conflict.json")


def get_golden_jev_debate_clash() -> dict:
    """Returns the micro debate clash for JEV."""
    return load_fixture_json("debate/jev_debate_micro_clash.json")


def get_synthetic_debate_claims(symbol: str = "EURUSD") -> Tuple[dict, dict]:
    """Backwards-compatible helper returning bull and bear claims."""
    deb = get_golden_debate_case(symbol)
    bull_claim = {
        "bull_thesis": deb.get("bull_case", "Bull Thesis: Price holding H4 FVG demand zone."),
        "strength_score": 8,
        "evidence_cited": ["H4_FVG_demand=1.1050", "RSI_bullish_divergence"],
        "key_levels": [1.1050, 1.1070, 1.1120],
        "falsification_triggers": ["D1 close below 1.1030"],
    }
    bear_dissent = {
        "bear_thesis": deb.get("bear_case", "Bear Thesis: DXY strength and resistance at 1.1100 limits upside."),
        "strength_score": 7,
        "evidence_cited": ["DXY_resistance=101.80", "Retail_long=74%"],
        "key_levels": [1.1100, 1.1020],
        "falsification_triggers": ["H4 close above 1.1120"],
    }
    return bull_claim, bear_dissent


# ==============================================================================
# Layer 5: Risk Fortress, Portfolio & Self-Reflection Loaders
# ==============================================================================


def get_golden_risk_state(scenario: str = "baseline") -> dict:
    """Returns risk state: 'baseline' or 'defensive'."""
    if scenario == "defensive":
        return load_fixture_json("risk/risk_gate_defensive_drawdown.json")
    return load_fixture_json("risk/risk_gate_production_state.json")


def get_golden_adversarial_case() -> dict:
    """Returns the adversarial liquidity trap case."""
    return load_fixture_json("risk/adversarial_liquidity_trap.json")


def get_golden_trade_reflection() -> dict:
    """Returns the real post-mortem trade reflection with full outcome PnL and lessons."""
    postmortem = load_fixture_json("risk/trade_reflection_postmortem.json")
    if postmortem and postmortem.get("outcome_pnl_usd") is not None:
        return postmortem
    curated = load_fixture_json("risk/curated_decision_reflections.json", default=[])
    if curated and isinstance(curated, list):
        for ref in curated:
            if ref.get("outcome_pnl_usd") is not None:
                return ref
        if curated:
            return curated[0]
    return postmortem or {}


def get_production_decision_reflections() -> List[dict]:
    """Returns all 452 curated post-mortem trade reflections from live production."""
    curated = load_fixture_json("risk/curated_decision_reflections.json", default=[])
    if curated and isinstance(curated, list):
        return curated
    single = get_golden_trade_reflection()
    return [single] if single else []


def get_golden_concurrent_orders() -> dict:
    """Returns multi-asset concurrent orders and portfolio correlation state."""
    return load_fixture_json("risk/multi_asset_concurrent_orders.json", default={})


def get_synthetic_risk_context(symbol: str = "EURUSD") -> dict:
    """Backwards-compatible helper returning realistic risk context."""
    risk_fix = get_golden_risk_state("baseline")
    prop = risk_fix.get("proposed_trade", {})
    acct = risk_fix.get("account_state", {})
    return {
        "symbol": symbol,
        "decision": prop.get("direction", "BUY"),
        "confluence_score": 11,
        "priced_in_score": 4,
        "rr_ratio": prop.get("risk_reward_ratio", 2.33),
        "sl_beyond_structure": True,
        "actual_risk_state": {
            "daily_pnl_usd": acct.get("daily_realized_pnl", -350.0),
            "open_positions": acct.get("open_positions_count", 2),
            "portfolio_heat_pct": acct.get("daily_drawdown_pct", 1.2),
            "equity": acct.get("equity", 76849.91),
        },
    }


# ==============================================================================
# Layer 6: News Engine Loaders
# ==============================================================================


def get_golden_news_batch(limit: int = 25) -> List[dict]:
    """Returns 25 real news items from 2026-10-01."""
    items = load_fixture_json("news/raw_news_batch_25.json", default=[])
    return items[:limit] if items else []


def get_golden_breaking_news() -> dict:
    """Returns the instant reaction breaking news alert."""
    return load_fixture_json("news/breaking_news_escalation.json")


def get_production_news_1000() -> List[dict]:
    """Returns 1,000 real production news items for daily cycle benchmark."""
    return load_fixture_json("news/production_news_1000_daily.json", default=[])


def get_golden_news_digest() -> dict:
    """Returns the full curated production news digest (Digest ID 406, 12,702 chars)."""
    return load_fixture_json("news/production_curated_news_digest.json", default={})


def get_synthetic_news_digest() -> str:
    """Returns full realistic news digest text string (~12,700 chars)."""
    digest_json = get_golden_news_digest()
    if digest_json and "formatted_digest" in digest_json:
        return digest_json["formatted_digest"]
    if digest_json and "digest_text" in digest_json:
        return digest_json["digest_text"]
    return ""


def get_synthetic_news_items() -> List[dict]:
    """Returns curated authentic news items (1,000 items daily cycle)."""
    items_1000 = get_production_news_1000()
    if items_1000:
        return items_1000
    batch = get_golden_news_batch(25)
    if batch:
        return batch
    prod = load_fixture_json("production_news_snapshot.json")
    if prod and "news_items" in prod:
        return prod["news_items"]
    return []


# ==============================================================================
# Layer 7: System 1 Fast-Path Reflexes (JEV) Loaders
# ==============================================================================


def get_golden_jev_reflexes() -> dict:
    """Returns the JEV reflex suite (news, trigger, position guard)."""
    return load_fixture_json("system1_jev/jev_reflex_suite.json")


def get_golden_jev_confluence() -> dict:
    """Returns the JEV confluence gate state."""
    return load_fixture_json("system1_jev/jev_confluence_gate_state.json")


def get_golden_jev_timing() -> dict:
    """Returns the JEV session timing gate state."""
    return load_fixture_json("system1_jev/jev_session_timing_state.json")


# ==============================================================================
# Layer 8: Omnichannel Chat & Voice Loaders
# ==============================================================================


def get_golden_telegram_dialogues() -> dict:
    """Returns telegram dialogues (fast, medium, complex)."""
    return load_fixture_json("omnichannel/telegram_conversations.json")


def get_golden_voice_transcripts() -> List[dict]:
    """Returns voice command transcripts in Indonesian and English."""
    return load_fixture_json("omnichannel/voice_transcripts_id_en.json", default=[])


def get_golden_reasoning_prompts() -> List[dict]:
    """Returns mathematical and quantitative reasoning prompts."""
    return load_fixture_json("omnichannel/interactive_reasoning_prompts.json", default=[])


# ==============================================================================
# Long Context & Transcript Fixtures (Harness Verification)
# ==============================================================================


def get_synthetic_compaction_payload() -> str:
    """Rich multi-source raw context for context_compaction testing (~20,000 characters)."""
    transcript_file = FIXTURES_DIR / "macro" / "raw_unfiltered_transcript_12p.txt"
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    golden = get_golden_macro_stage1()
    news_items = get_golden_news_batch(20)

    lines = [
        "=== COMPREHENSIVE ECONOMIC CALENDAR & REUTER/BLOOMBERG NEWSFEED (GOLDEN PRODUCTION SNAPSHOT) ===",
        "Cycle Reference: 2026-10-01T14:00:00Z | Source: Tier-1 Feeds",
        "",
        "--- SECTION 1: GLOBAL ECONOMIC CALENDAR RELEASES (FULL DETAILS) ---",
    ]
    for ev in golden.get("upcoming_calendar", [])[:25]:
        lines.append(
            f"Date: {ev.get('datetime_utc', '2026-10-01 12:30:00')} | Currency: {ev.get('currency', 'USD')} | "
            f"Event: {ev.get('event', '')} | Actual: {ev.get('actual')} | Forecast: {ev.get('forecast')} | "
            f"Previous: {ev.get('previous')} | Impact: {ev.get('impact')}"
        )
    lines.extend(
        [
            "",
            "--- SECTION 2: SOVEREIGN BOND YIELD CURVE & INTERBANK DATA ---",
            "US 10-Year: 3.820% | US 2-Year: 3.650% | Spread US 10Y-2Y: +17.0 bps",
            "DE 10-Year: 2.385% | DE 2-Year: 2.150% | Spread US-DE 10Y: +143.5 bps",
            "UK 10-Year: 4.180% | JP 10-Year: 1.150%",
            "",
            "--- SECTION 3: RAW UNEDITED NEWSWIRE DISPATCHES (20 ARTICLES) ---",
        ]
    )
    for i, it in enumerate(news_items, 1):
        lines.append(
            f"[{i}] SOURCE: {it.get('source', 'Newswire')} | TIMESTAMP: {it.get('published_at', '2026-10-01')}\n"
            f"HEADLINE: {it.get('title', '')}\n"
            f"DISPATCH: {it.get('summary', '')}\n"
            f"IMPACT: {it.get('impact', 'HIGH')}\n"
        )
    lines.append("=== END UNFILTERED RAW TRANSCRIPT ===")
    return "\n".join(lines)


def get_synthetic_session_reports_payload() -> str:
    """End-of-cycle session reports across 6 major assets + macro brief (~6,000 characters)."""
    brief = get_synthetic_fundamental_brief()
    reports_file = load_fixture_json("macro/session_reports_multi_asset.json")
    if reports_file and "reports" in reports_file:
        lines = [
            "=== EXECUTIVE PORTFOLIO SESSION REPORTS BUNDLE (ALL ASSETS) ===",
            f"Session: {reports_file.get('session')} | Date: {reports_file.get('date')}",
            "Account: Balance $76,849.91 | Free Margin: $75,200.00 | Daily PnL: -$350.00",
            "",
            "--- MACRO REGIME & STAGE 1 BRIEF OVERVIEW ---",
            f"Dominant Driver: {brief.get('priced_in_assessment', {}).get('dominant_driver', 'Fed higher-for-longer')}",
            f"Macro Narrative: {brief.get('macro_narrative')}",
            f"Currency Biases: {json.dumps(brief.get('currency_bias'))}",
            f"Confidence: {brief.get('confidence')} | Risk Sentiment: {brief.get('risk_sentiment')}",
            "",
        ]
        for sym, rep in reports_file.get("reports", {}).items():
            lines.append(f"--- PAIR: {sym} ---\n{rep}")
        pnl = reports_file.get("portfolio_pnl_summary", {})
        lines.append(
            f"--- PORTFOLIO SUMMARY ---\nRealized PnL: ${pnl.get('realized_usd')} | Unrealized: ${pnl.get('unrealized_usd')} | Win Rate: {pnl.get('win_rate_session')}"
        )
        return "\n\n".join(lines)

    brief = get_synthetic_fundamental_brief()
    return f"""=== EXECUTIVE PORTFOLIO SESSION REPORTS BUNDLE (ALL ASSETS) ===
Timestamp: 2026-10-01T21:00:00Z | Session: End-of-Day NY Rollover
Account: Balance $76,849.91 | Free Margin: $75,200.00 | Daily PnL: -$350.00

--- MACRO REGIME & STAGE 1 BRIEF OVERVIEW ---
Dominant Driver: {brief.get("priced_in_assessment", {}).get("dominant_driver", "Fed higher-for-longer")}
Macro Narrative: {brief.get("macro_narrative")}
Currency Biases: {json.dumps(brief.get("currency_bias"))}
Confidence: {brief.get("confidence")} | Risk Sentiment: {brief.get("risk_sentiment")}

--- PAIR 1: EURUSD SESSION ANALYSIS & PROPOSAL ---
Decision: BUY (Confluence Score: 11/14, R:R: 2.33)
Current Market Price: 1.1065
Entry Zone: 1.1055 - 1.1070 | Stop Loss: 1.1035 | Take Profit: 1.1135
Technical Highlights: H1 Bullish Displacement with Order Block mitigation at 1.1050 and FVG fill.
Risk Assessment: Macro bias EUR is bearish (-0.75), creating counter-trend friction. ADR usage currently 48%.

--- PAIR 2: GBPUSD SESSION ANALYSIS & PROPOSAL ---
Decision: WAIT (Confluence Score: 6/14)
Current Market Price: 1.3020
Technical Highlights: M15 Range consolidation. No clear structural displacement. Trapped retail volume.

--- PAIR 3: USDJPY SESSION ANALYSIS & PROPOSAL ---
Decision: SELL (Confluence Score: 10/14, R:R: 2.10)
Current Market Price: 143.80
Entry Zone: 143.90 - 144.10 | Stop Loss: 144.60 | Take Profit: 142.20
Technical Highlights: H4 Bearish Supply rejection at 144.20. BoJ policy normalization tailwinds.

--- PAIR 4: XAUUSD SESSION ANALYSIS & PROPOSAL ---
Decision: BUY (Confluence Score: 12/14, R:R: 2.45)
Current Market Price: 2658.50
Entry Zone: 2652.00 - 2660.00 | Stop Loss: 2642.00 | Take Profit: 2695.00
Technical Highlights: Liquidity sweep below Asian low followed by immediate V-shape institutional absorption.

--- PAIR 5: BTCUSD SESSION ANALYSIS & PROPOSAL ---
Decision: BUY (Confluence Score: 10/14, R:R: 1.85)
Current Market Price: 84,200.00
Entry Zone: 83,800 - 84,200 | Stop Loss: 83,400.00 | Take Profit: 85,800.00

--- PAIR 6: XTIUSD (CRUDE OIL) SESSION ANALYSIS & PROPOSAL ---
Decision: BUY (Confluence Score: 11/14, R:R: 2.00)
Current Market Price: 71.85
Entry Zone: 71.20 - 71.85 | Stop Loss: 70.40 | Take Profit: 74.50

--- PORTFOLIO ALLOCATION SUMMARY ---
Approved: EURUSD, XAUUSD, USDJPY, XTIUSD | Total Risk: 3.2% NAV
============================================================="""


def get_synthetic_fomc_transcript_payload() -> str:
    """Realistic transcript of FOMC press conference (~12,000 characters)."""
    transcript_file = FIXTURES_DIR / "macro" / "fomc_press_conference_transcript.txt"
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    return """FEDERAL OPEN MARKET COMMITTEE (FOMC) PRESS CONFERENCE TRANSCRIPT
Washington, D.C. | Chair Policy Remarks & Q&A Session

CHAIR POWELL: Good afternoon. My colleagues and I remain squarely focused on our dual mandate: maximum employment and stable prices. Today, the Committee decided to maintain the target range for the federal funds rate at 3.75 to 4.00 percent, and to continue the process of significantly reducing our securities holdings.

Recent economic indicators suggest that economic activity has continued to expand at a solid pace. Job gains have remained resilient, and the unemployment rate remains low at 3.9 percent. Inflation has eased substantially over the past two years, but remains somewhat elevated above our 2 percent longer-run objective.

The recent geopolitical developments in the Middle East and the associated increase in crude oil prices present renewed upside risks to headline inflation. While market-based measures of longer-term inflation expectations appear anchored, short-term breakevens have widened. In considering any future adjustments to the target range for the federal funds rate, the Committee will carefully assess incoming data, the evolving outlook, and the balance of risks.

QUESTION: Mr. Chair, markets had previously priced in multiple rate cuts. Given the geopolitical tension and resilient jobs data, how does the Committee view the path forward?

CHAIR POWELL: We make our decisions meeting by meeting based on the totality of the incoming data. We are not on a preset course. What I can say is that the labor market gives us the flexibility to be patient and deliberate. If the economy remains strong and inflation remains sticky, we are prepared to hold rates at this plateau for as long as appropriate.

QUESTION: Chair Powell, regarding the balance sheet runoff and dollar liquidity, are you concerned that rising long-term yields and persistent dollar strength could tighten financial conditions more than desired across global financial markets?

CHAIR POWELL: We continue to monitor broad financial conditions closely across all market sectors. Our balance sheet runoff is proceeding smoothly according to the parameters established in our prior communications. While currency movements reflect differential growth and monetary policy trajectories across jurisdictions, our focus remains squarely on our domestic price stability and maximum employment objectives. We do not target specific exchange rate levels, but we take account of the persistent effects that broad financial tightening can exert on the real economy."""


def get_synthetic_macro_anomaly_payload() -> str:
    """Yield divergence anomaly data context (~3,500 characters)."""
    return """MACROECONOMIC ANOMALY DATA PACKET: TRANSATLANTIC REAL YIELD DIVERGENCE & ENERGY SHOCK
Target Analysis Horizon: 2026-10-01 | Cycle Focus: US TIPS vs. DE Bund Real Yields vs. Crude Oil

1. SOVEREIGN REAL & NOMINAL YIELDS COMPARISON:
- US 10-Year Nominal Treasury Yield: 3.820% (Change: -4.1 bps)
- US 10-Year TIPS Real Yield: 1.580%
- DE 10-Year Nominal Bund Yield: 2.385%
- DE 10-Year Real Yield: 0.255%
- Nominal 10Y Spread (US - DE): +143.5 bps -> Significant dollar yield advantage.

2. COMMODITY & TERMS-OF-TRADE SHOCK:
- WTI Crude Spot: $71.85/bbl (+2.4% 1D).
- European Natural Gas TTF: €42.50/MWh.
- Terms of Trade Indicator: US energy independence vs Europe energy import vulnerability.

3. CROSS-CURRENCY TRANSMISSION:
- EURUSD traded at 1.1065 in key H4 demand zone.
- Correlation between (US-DE Yield Spread) and EURUSD: -0.88.

4. CENTRAL BANK REACTION FUNCTIONS & FORWARD PRICING:
- Fed Funds Futures pricing: 82% probability of plateau at 3.75-4.00% through Q4 2026.
- ECB Deposit Facility Rate: 2.50%, market pricing 45 bps of cuts over next 6 months due to European stagflation risks.
- 5y5y Forward Inflation Expectations: US at 2.34% vs Eurozone at 2.12%.

5. INTERMARKET CORRELATIONS & CROSS-ASSET SPILLOVER:
- S&P 500 E-mini: 5,745.25 (-0.45%), testing 20-day EMA support with resilient corporate cash balances.
- Euro Stoxx 50: 4,920.10 (-1.15%), underperforming due to industrial chemical and energy input costs.
- Gold (XAUUSD): $2,658.50/oz (+0.82%), benefiting from dual safe-haven bids and central bank sovereign reserve diversification.
- High Yield Credit Spreads: US CDX HY widened 14 bps to 345 bps; European iTraxx Crossover widened 28 bps to 380 bps.

6. BALANCE OF PAYMENTS & CAPITAL FLOW DYNAMICS:
- Eurozone Current Account surplus deteriorating to +1.2% GDP from +2.8% pre-shock due to hydrocarbon import inflation.
- US Foreign Direct Investment & Portfolio Inflows remaining resilient at +$42B/month driven by tech and AI infrastructure Capex.
- Liquidity metric: Cross-currency basis swap (EUR/USD 3M) widened to -18.5 bps indicating rising structural dollar funding premium."""


def get_synthetic_sentiment_feed_payload() -> str:
    """Rich institutional commentary feed + retail positioning + COT breakdown."""
    return """INSTITUTIONAL POSITIONING COMMENTARY FEED & SENTIMENT AGGREGATION
Window: 24-Hour Ingestion Cycle | Timestamp: 2026-10-01T14:00:00Z

--- FEED ITEM 1: INSTITUTIONAL FX FLOW NOTE ---
"Hedge funds note continued demand for USD as defensive liquidity buffer against Middle East energy headline risk. Corporate hedgers active buyers of USD against European energy importers."

--- FEED ITEM 2: COMMODITY & MACRO DESK ---
"Gold ($2,658.50) physical accumulation remains robust among sovereign reserve managers, absorbing commercial short hedges. Money managers hold +218,000 long contracts."

--- FEED ITEM 3: CFTC COMMITMENTS OF TRADERS (COT) WEEKLY AUDIT ---
- EUR: Leveraged Funds net short -62,400 contracts. Commercials net long +51,000.
- USD: Non-commercial net long +48,200 contracts (72nd percentile).
- XAU: Speculators net long +218,000 contracts.

--- FEED ITEM 4: RETAIL CROWD POSITIONING AGGREGATES ---
- EURUSD: 74.2% Retail LONG -> Contrarian short signal.
- GBPUSD: 83.0% Retail LONG -> Contrarian short signal.
- USDJPY: 76.7% Retail SHORT -> Contrarian long signal.
- XAUUSD: 56.5% Retail LONG / 43.5% SHORT -> Balanced.

--- FEED ITEM 5: GOLDMAN SACHS GLOBAL INVESTMENT RESEARCH ---
"We maintain our overweight stance on the USD against cyclical European currencies. The compounding effect of terms-of-trade degradation from crude oil and natural gas prices, paired with the Fed's higher-for-longer policy plateau at 3.75-4.00%, leaves EUR/USD vulnerable to further downside tests toward 1.0950. Tactical risk sentiment remains in 'selective risk-off' territory, favoring dollar liquidity over high-beta FX."

--- FEED ITEM 6: DERIVATIVES & OPTIONS VOLATILITY SURFACE ---
- EURUSD 1-Month 25-Delta Risk Reversal: -1.25 vol premium for EUR puts vs calls (elevated downside hedging demand).
- USDJPY 1-Month Risk Reversal: +0.85 vol premium for USD calls.
- VIX Implied vs Realized Spread: Implied 16.70 vs 10-day Realized 14.10 (+2.60 vol points risk premium).
- Fear & Greed Multi-Asset Index: 38/100 (Fear regime - cash and short-duration Treasury hoarding)."""
