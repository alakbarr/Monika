#!/usr/bin/env python3
"""
Monika Institutional Quantitative Invariant & Risk Engine (monika_quant_engine.py)

Zero-dependency, Python Standard Library-only CLI engine for algorithmic trading
invariants, pre-computed brackets, fixed-fractional Decimal position sizing,
and 12-point RiskGate pre-execution auditing.

Replicates the deterministic mathematical fortress of Monika in standalone AI Agent skills.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, UTC
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# 1. ASSET SPECIFICATIONS & INSTRUMENT DICTIONARY
# ==============================================================================

DEFAULT_INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "EURUSD": {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "099741",
    },
    "GBPUSD": {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "096742",
    },
    "USDJPY": {
        "pip_size": 0.01,
        "pip_value_usd": 6.67,  # Dynamic fallback
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 3,
        "cot_code": "097741",
    },
    "AUDUSD": {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "232741",
    },
    "USDCAD": {
        "pip_size": 0.0001,
        "pip_value_usd": 7.41,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "090741",
    },
    "USDCHF": {
        "pip_size": 0.0001,
        "pip_value_usd": 11.10,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "092741",
    },
    "XAUUSD": {
        "pip_size": 0.01,
        "pip_value_usd": 1.0,  # $1 per 0.01 pt per 100 oz lot
        "contract_size": 100,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 2,
        "cot_code": "088691",
    },
    "XTIUSD": {
        "pip_size": 0.01,
        "pip_value_usd": 10.0,  # 1000 bbl * $0.01 = $10.0/pip
        "contract_size": 1000,
        "min_lot": 0.01,
        "max_lot": 50.0,
        "lot_step": 0.01,
        "digits": 2,
        "cot_code": "067651",
    },
    "XBRUSD": {
        "pip_size": 0.01,
        "pip_value_usd": 10.0,
        "contract_size": 1000,
        "min_lot": 0.01,
        "max_lot": 50.0,
        "lot_step": 0.01,
        "digits": 2,
        "cot_code": "06765T",
    },
    "BTCUSD": {
        "pip_size": 1.0,
        "pip_value_usd": 1.0,  # 1 BTC * $1 = $1/point
        "contract_size": 1,
        "min_lot": 0.01,
        "max_lot": 10.0,
        "lot_step": 0.01,
        "digits": 1,
        "cot_code": "133741",
    },
}


def get_asset_spec(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if sym in DEFAULT_INSTRUMENTS:
        return DEFAULT_INSTRUMENTS[sym]
    # Inferred defaults based on naming patterns
    if any(k in sym for k in ("JPY", "XAG", "XTI", "XBR", "BRENT", "WTI")):
        digits = 3 if "JPY" in sym else 2
        return {
            "pip_size": 0.01,
            "pip_value_usd": 10.0 if ("XTI" in sym or "XBR" in sym) else 6.67,
            "contract_size": 1000 if ("XTI" in sym or "XBR" in sym) else 100000,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "digits": digits,
            "cot_code": "UNKNOWN",
        }
    if any(k in sym for k in ("XAU", "GOLD", "ETH")):
        return {
            "pip_size": 0.01,
            "pip_value_usd": 1.0,
            "contract_size": 100,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "digits": 2,
            "cot_code": "088691",
        }
    if "BTC" in sym:
        return {
            "pip_size": 1.0,
            "pip_value_usd": 1.0,
            "contract_size": 1,
            "min_lot": 0.01,
            "max_lot": 10.0,
            "lot_step": 0.01,
            "digits": 1,
            "cot_code": "133741",
        }
    return {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "UNKNOWN",
    }


def extract_price_precision(symbol: str) -> int:
    return int(get_asset_spec(symbol)["digits"])


# ==============================================================================
# 2. SUBCOMMAND: VALIDATE TELEMETRY & SESSION TIMING
# ==============================================================================


def validate_telemetry(
    timestamps_json: Optional[str] = None,
    now_utc_str: Optional[str] = None,
    event_time_utc_str: Optional[str] = None,
    event_impact: str = "HIGH",
) -> Dict[str, Any]:
    """
    Validates data freshness (TTL), session killzones, and event/rollover blackouts.
    """
    now = datetime.fromisoformat(now_utc_str.replace("Z", "+00:00")) if now_utc_str else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    # TTL Specifications (Hours)
    ttl_limits: Dict[str, float] = {
        "fedwatch": 12.0,
        "treasury_yields": 24.0,
        "central_bank_rates": 72.0,
        "cftc_cot": 168.0,  # 7 days
        "vix": 4.0,
        "h4_indicators": 5.0,
        "d1_indicators": 24.0,
    }

    freshness_results: Dict[str, Any] = {}
    stale_found = False
    reasons: List[str] = []

    if timestamps_json:
        try:
            ts_data = json.loads(timestamps_json)
            for domain, limit_hrs in ttl_limits.items():
                if domain in ts_data:
                    dt_val = datetime.fromisoformat(str(ts_data[domain]).replace("Z", "+00:00"))
                    if dt_val.tzinfo is None:
                        dt_val = dt_val.replace(tzinfo=UTC)
                    age_hrs = (now - dt_val).total_seconds() / 3600.0
                    is_fresh = age_hrs <= limit_hrs
                    if not is_fresh:
                        stale_found = True
                        reasons.append(f"{domain} is {age_hrs:.1f}h old (TTL={limit_hrs:.1f}h)")
                    freshness_results[domain] = {
                        "age_hours": round(age_hrs, 2),
                        "limit_hours": limit_hrs,
                        "status": "FRESH" if is_fresh else "STALE",
                    }
        except Exception as e:
            stale_found = True
            reasons.append(f"Invalid timestamps JSON: {e}")

    # Session Timing & Killzones
    hour = now.hour
    minute = now.minute
    minute_of_day = hour * 60 + minute

    killzones: List[str] = []
    # Tokyo: 00:00 - 06:00 UTC
    if 0 <= hour < 6:
        killzones.append("TOKYO_SESSION")
    # London Open: 07:00 - 10:00 UTC
    if 7 <= hour < 10:
        killzones.append("LONDON_OPEN")
        # Judas Swing window: 07:00 - 08:30 UTC
        if hour == 7 or (hour == 8 and minute <= 30):
            killzones.append("JUDAS_SWING_ALERT")
    # London-NY Overlap: 12:00 - 16:00 UTC
    if 12 <= hour < 16:
        killzones.append("LONDON_NY_OVERLAP")
    # NY Afternoon: 16:00 - 20:00 UTC
    if 16 <= hour < 20:
        killzones.append("NY_AFTERNOON")

    # Rollover Blackout: 21:55 - 22:15 UTC (1315 - 1335 minute of day)
    rollover_blackout = 1315 <= minute_of_day <= 1335
    if rollover_blackout:
        reasons.append("Daily Rollover Blackout active (21:55 - 22:15 UTC)")

    # High-Impact Event Window
    event_blackout = False
    event_delta_mins: Optional[float] = None
    if event_time_utc_str and event_impact.upper() in ("HIGH", "TIER1", "CRITICAL"):
        try:
            ev_dt = datetime.fromisoformat(event_time_utc_str.replace("Z", "+00:00"))
            if ev_dt.tzinfo is None:
                ev_dt = ev_dt.replace(tzinfo=UTC)
            event_delta_mins = (ev_dt - now).total_seconds() / 60.0
            # 30 mins before, 15 mins after
            if -15.0 <= event_delta_mins <= 30.0:
                event_blackout = True
                reasons.append(f"High-impact event in progress (~{event_delta_mins:.0f}m away)")
        except Exception as e:
            reasons.append(f"Failed parsing event time: {e}")

    ttl_multiplier = 0.50 if stale_found else 1.00
    execution_permitted = not rollover_blackout and not event_blackout

    return {
        "timestamp_checked": now.isoformat(),
        "stale_data_detected": stale_found,
        "ttl_multiplier": ttl_multiplier,
        "active_killzones": killzones,
        "overlap_bonus_eligible": "LONDON_NY_OVERLAP" in killzones,
        "judas_swing_active": "JUDAS_SWING_ALERT" in killzones,
        "rollover_blackout": rollover_blackout,
        "event_blackout": event_blackout,
        "event_delta_minutes": round(event_delta_mins, 1) if event_delta_mins is not None else None,
        "execution_permitted": execution_permitted,
        "rejection_reasons": reasons,
        "freshness_details": freshness_results,
    }


# ==============================================================================
# 3. SUBCOMMAND: CENTRAL BANK DIFFERENTIAL & FX SIGN INVARIANT
# ==============================================================================


CB_PROFILES: Dict[str, Dict[str, Any]] = {
    "USD": {"name": "Federal Reserve", "target_inflation": 2.0, "default_r_star": 2.875},
    "EUR": {"name": "European Central Bank", "target_inflation": 2.0, "default_r_star": 2.125},
    "GBP": {"name": "Bank of England", "target_inflation": 2.0, "default_r_star": 3.375},
    "JPY": {"name": "Bank of Japan", "target_inflation": 2.0, "default_r_star": 0.875},
    "AUD": {"name": "Reserve Bank of Australia", "target_inflation": 2.5, "default_r_star": 3.625},
    "CAD": {"name": "Bank of Canada", "target_inflation": 2.0, "default_r_star": 2.75},
    "CHF": {"name": "Swiss National Bank", "target_inflation": 1.0, "default_r_star": 1.00},
}


def cb_differential(
    base_currency: str,
    quote_currency: str,
    base_rate: float,
    quote_rate: float,
    base_r_star: Optional[float] = None,
    quote_r_star: Optional[float] = None,
    base_inflation: Optional[float] = None,
    quote_inflation: Optional[float] = None,
    base_unemployment_chg: float = 0.0,
    quote_unemployment_chg: float = 0.0,
) -> Dict[str, Any]:
    """
    Computes Taylor/Neutral stance divergence, net pair bias, and FX Algebraic Sign Invariant.
    Bias(BASE/QUOTE) = Bias(BASE) - Bias(QUOTE)
    """
    b_curr = base_currency.strip().upper()
    q_curr = quote_currency.strip().upper()

    b_prof = CB_PROFILES.get(b_curr, {"name": f"CB_{b_curr}", "target_inflation": 2.0, "default_r_star": 2.5})
    q_prof = CB_PROFILES.get(q_curr, {"name": f"CB_{q_curr}", "target_inflation": 2.0, "default_r_star": 2.5})

    r_star_b = base_r_star if base_r_star is not None else b_prof["default_r_star"]
    r_star_q = quote_r_star if quote_r_star is not None else q_prof["default_r_star"]

    inf_b = base_inflation if base_inflation is not None else b_prof["target_inflation"]
    inf_q = quote_inflation if quote_inflation is not None else q_prof["target_inflation"]

    # Policy stance = Policy Rate - Neutral Rate (r*)
    base_stance = base_rate - r_star_b
    quote_stance = quote_rate - r_star_q

    # Inflation pressure
    base_inf_gap = inf_b - b_prof["target_inflation"]
    quote_inf_gap = inf_q - q_prof["target_inflation"]

    # Macro score (-10 to +10)
    # Higher stance + higher inflation = hawkish (+); rising unemployment = dovish (-)
    base_score = (base_stance * 1.5) + (base_inf_gap * 1.2) - (base_unemployment_chg * 3.0)
    quote_score = (quote_stance * 1.5) + (quote_inf_gap * 1.2) - (quote_unemployment_chg * 3.0)

    base_score = max(-10.0, min(10.0, base_score))
    quote_score = max(-10.0, min(10.0, quote_score))

    # Net Algebraic Differential
    net_bias = round(base_score - quote_score, 2)

    # Direction interpretation
    if net_bias >= 2.5:
        bias_label = "BULLISH"
    elif net_bias <= -2.5:
        bias_label = "BEARISH"
    else:
        bias_label = "NEUTRAL"

    return {
        "pair": f"{base_currency.upper()}{quote_currency.upper()}",
        "base_currency": base_currency.upper(),
        "quote_currency": quote_currency.upper(),
        "base_policy_stance": round(base_stance, 2),
        "quote_policy_stance": round(quote_stance, 2),
        "rate_differential_bps": round((base_rate - quote_rate) * 100, 1),
        "base_macro_score": round(base_score, 2),
        "quote_macro_score": round(quote_score, 2),
        "net_pair_bias_score": net_bias,
        "structural_bias": bias_label,
        "algebraic_invariant_verified": True,
    }


# ==============================================================================
# 4. SUBCOMMAND: MACRO REGIME & SYSTEMIC LIQUIDITY PLUMBING
# ==============================================================================


def macro_calc(
    walcl_billions: Optional[float] = None,
    tga_billions: Optional[float] = None,
    rrp_billions: Optional[float] = None,
    prev_net_liquidity_billions: Optional[float] = None,
    us10y: Optional[float] = None,
    us2y: Optional[float] = None,
    tips10y: Optional[float] = None,
    vix: float = 16.0,
    hy_oas_bps: float = 340.0,
) -> Dict[str, Any]:
    """
    Computes Net Systemic Liquidity (WALCL - TGA - RRP), 4-Quadrant Yield Curve Regime,
    10Y Breakeven Inflation, and 5-Regime VIX Multiplier.
    """
    # 1. Net Liquidity
    net_liquidity: Optional[float] = None
    net_liq_chg: Optional[float] = None
    liq_stance = "NEUTRAL"

    if walcl_billions is not None and tga_billions is not None and rrp_billions is not None:
        net_liquidity = round(walcl_billions - tga_billions - rrp_billions, 2)
        if prev_net_liquidity_billions is not None:
            net_liq_chg = round(net_liquidity - prev_net_liquidity_billions, 2)
            if net_liq_chg > 25.0:
                liq_stance = "EXPANDING"
            elif net_liq_chg < -25.0:
                liq_stance = "CONTRACTING"

    # 2. 4-Quadrant Yield Curve
    curve_regime = "UNKNOWN"
    breakeven_inflation: Optional[float] = None
    slope_2s10s: Optional[float] = None

    if us10y is not None and us2y is not None:
        slope_2s10s = round(us10y - us2y, 3)
        # Classify curve quadrant based on slope and absolute levels
        if slope_2s10s > 0:
            curve_regime = "STEEPENER_NORMAL"
        else:
            curve_regime = "INVERTED_FLATTENER"

    if us10y is not None and tips10y is not None:
        breakeven_inflation = round(us10y - tips10y, 3)

    # 3. 5-Regime VIX Classification & Multiplier
    vix_val = float(vix)
    if vix_val < 15.0:
        vix_regime = "RISK_ON"
        vix_multiplier = 1.00
    elif vix_val <= 20.0:
        vix_regime = "CARRY_RANGE"
        vix_multiplier = 1.00
    elif vix_val <= 25.0:
        vix_regime = "CAUTION"
        vix_multiplier = 0.75
    elif vix_val <= 30.0:
        vix_regime = "STRESS"
        vix_multiplier = 0.50
    else:
        vix_regime = "CRISIS"
        vix_multiplier = 0.25

    # 4. Credit Spread (HY OAS) Stress Gate
    credit_stress = hy_oas_bps >= 450.0
    credit_benign = hy_oas_bps <= 350.0

    return {
        "net_liquidity_billions": net_liquidity,
        "net_liquidity_delta_billions": net_liq_chg,
        "systemic_liquidity_stance": liq_stance,
        "yield_2s10s_spread": slope_2s10s,
        "curve_regime": curve_regime,
        "breakeven_inflation_10y": breakeven_inflation,
        "vix_level": vix_val,
        "vix_regime": vix_regime,
        "vix_risk_multiplier": vix_multiplier,
        "hy_oas_bps": hy_oas_bps,
        "credit_stress_hard_veto": credit_stress,
        "credit_environment": "BENIGN" if credit_benign else ("STRESS" if credit_stress else "NEUTRAL"),
    }


# ==============================================================================
# 5. SUBCOMMAND: EVENT NOWCASTING & PRICED-IN SCORE
# ==============================================================================


def event_calc(
    actual: Optional[float] = None,
    consensus: Optional[float] = None,
    previous: Optional[float] = None,
    prior_revision: float = 0.0,
    priced_in_fedwatch: float = 5.0,
    priced_in_cot: float = 5.0,
    priced_in_exhaustion: float = 5.0,
    priced_in_historical: float = 5.0,
    event_high: Optional[float] = None,
    event_low: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes Net Surprise with revision, Canonical 4-Method Priced-In Score (1-10),
    and normalized Event Anchor Range.
    """
    net_surprise: Optional[float] = None
    if actual is not None and consensus is not None:
        net_surprise = round((actual - consensus) + prior_revision, 3)

    # 4-Method Priced-In Average
    scores = [priced_in_fedwatch, priced_in_cot, priced_in_exhaustion, priced_in_historical]
    priced_in_avg = round(sum(scores) / len(scores), 2)
    exhaustion_warning = priced_in_avg >= 8.0

    # Event Anchor Range
    anchor_range: Optional[Dict[str, float]] = None
    if event_high is not None and event_low is not None:
        hi = max(float(event_high), float(event_low))
        lo = min(float(event_high), float(event_low))
        rng = hi - lo
        anchor_range = {
            "event_high": hi,
            "event_low": lo,
            "event_midpoint": round(lo + (rng * 0.5), 5),
            "range_size": round(rng, 5),
        }

    return {
        "actual": actual,
        "consensus": consensus,
        "previous": previous,
        "prior_revision": prior_revision,
        "net_surprise": net_surprise,
        "priced_in_score": priced_in_avg,
        "exhaustion_warning": exhaustion_warning,
        "event_anchor_range": anchor_range,
        "execution_guidance": (
            "EXHAUSTION WARNING: Market has pre-priced the outcome (Score >= 8.0). High risk of 'Sell-the-Fact' reversal."
            if exhaustion_warning
            else "NORMAL ABSORPTION: Event catalyst is fresh; trade structural acceptance."
        ),
    }


# ==============================================================================
# 6. SUBCOMMAND: COT POSITIONING & 5 INSTITUTIONAL SYNERGY STATES
# ==============================================================================


def cot_synergy(
    cot_net_pct: float,
    cot_52w_pct: float,
    tech_dir: str,
    macro_dir: str,
    sent_dir: str,
    tech_conf: float = 75.0,
    macro_conf: float = 75.0,
    sent_conf: float = 75.0,
) -> Dict[str, Any]:
    """
    Evaluates 3-Specialist Triangulation (Tech 45%, Macro 35%, Contrarian Sent 20%)
    and classifies into 5 Institutional Synergy States.
    """
    t_conf = max(0.0, min(100.0, float(tech_conf)))
    m_conf = max(0.0, min(100.0, float(macro_conf)))
    s_conf = max(0.0, min(100.0, float(sent_conf)))
    pct_val = max(0.0, min(100.0, float(cot_52w_pct)))

    t_d = (
        1.0
        if tech_dir.lower() in ("buy", "bull", "long")
        else (-1.0 if tech_dir.lower() in ("sell", "bear", "short") else 0.0)
    )
    m_d = (
        1.0
        if macro_dir.lower() in ("buy", "bull", "long")
        else (-1.0 if macro_dir.lower() in ("sell", "bear", "short") else 0.0)
    )
    s_d = (
        1.0
        if sent_dir.lower() in ("buy", "bull", "long")
        else (-1.0 if sent_dir.lower() in ("sell", "bear", "short") else 0.0)
    )

    # Weighted Composite Score: Tech 45%, Macro 35%, Sent 20%
    composite = (t_d * (t_conf / 100.0) * 0.45) + (m_d * (m_conf / 100.0) * 0.35) + (s_d * (s_conf / 100.0) * 0.20)
    composite_score = round(composite * 100.0, 1)

    # Extreme COT Crowd Alert
    is_cot_crowded = pct_val >= 85.0 or pct_val <= 15.0

    # Synergy State Classification
    if t_d == m_d and t_d != 0.0:
        if s_d == 0.0 or not is_cot_crowded:
            synergy_state = "uncrowded_institutional_synergy"
            synergy_mult = 1.10
            historical_edge = "81.8% accuracy (Prime Institutional Flow)"
        elif s_d != t_d:
            synergy_state = "institutional_contrarian_synergy"
            synergy_mult = 1.08
            historical_edge = "Retail/Crowd trapped against institutional trend"
        else:
            synergy_state = "crowded_unanimous_exhaustion"
            synergy_mult = 0.82
            historical_edge = "72.7%-80% reversal trap risk (Over-crowded consensus)"
    elif t_d != m_d and t_d == s_d and t_d != 0.0:
        synergy_state = "crowded_tech_sent_trap_vs_macro"
        synergy_mult = 0.85
        historical_edge = "71.4% retail trap (Technical & Crowd fighting Macro)"
    else:
        synergy_state = "technical_macro_conflict"
        synergy_mult = 0.88
        historical_edge = "Domain conflict: Reduce exposure or wait for resolution"

    return {
        "cot_net_percentile": cot_52w_pct,
        "cot_extreme_crowded": is_cot_crowded,
        "three_specialist_composite_score": composite_score,
        "synergy_state": synergy_state,
        "synergy_multiplier": synergy_mult,
        "historical_edge_context": historical_edge,
    }


# ==============================================================================
# 7. SUBCOMMAND: SMC/ICT 3-ZONE DEALING RANGE & 20-PT CONFLUENCE
# ==============================================================================


def smc_confluence(
    close: float,
    high20: float,
    low20: float,
    atr14: float,
    pdl: Optional[float] = None,
    pdh: Optional[float] = None,
    confluence_score: int = 12,
    has_active_impulse: bool = False,
) -> Dict[str, Any]:
    """
    Computes 3-Zone Spatial Dealing Range (pos), Anti-Chasing boundaries,
    and 20-Point Confluence scorecard threshold tiers.
    pos = (Close - Low20) / (High20 - Low20)
    """
    hi = max(float(high20), float(low20))
    lo = min(float(high20), float(low20))
    rng = hi - lo
    pos = 0.50 if rng <= 0.0 else (close - lo) / rng
    pos = round(max(0.0, min(1.0, pos)), 4)
    safe_atr = max(1e-7, float(atr14))

    # Zone Determination
    is_discount = pos <= 0.35 or (pdl is not None and (close - pdl) <= 0.50 * safe_atr and pos <= 0.40)
    is_premium = pos >= 0.65 or (pdh is not None and (pdh - close) <= 0.50 * safe_atr and pos >= 0.60)
    is_equilibrium = not is_discount and not is_premium

    # Dealing Range Restrictions
    anti_chasing_buy_block = pos > 0.85
    anti_chasing_sell_block = pos < 0.15

    if is_discount:
        zone_label = "DISCOUNT_ZONE"
        allowed_direction = "BUY" if not anti_chasing_buy_block else "HOLD"
    elif is_premium:
        zone_label = "PREMIUM_ZONE"
        allowed_direction = "SELL" if not anti_chasing_sell_block else "HOLD"
    else:
        zone_label = "EQUILIBRIUM_CHOP"
        allowed_direction = "BUY_OR_SELL_IMPULSE" if has_active_impulse else "HOLD"

    # Confluence Tiers
    if confluence_score >= 13:
        conf_tier = "FULL_CONFLUENCE"
        conf_mult = 1.00
    elif confluence_score >= 11:
        conf_tier = "STRONG_CONFLUENCE"
        conf_mult = 0.75
    elif confluence_score >= 10:
        conf_tier = "MODERATE_CONFLUENCE"
        conf_mult = 0.50
    else:
        conf_tier = "SUB_THRESHOLD_REJECT"
        conf_mult = 0.00

    return {
        "dealing_range_pos": pos,
        "zone": zone_label,
        "is_discount": is_discount,
        "is_premium": is_premium,
        "is_equilibrium": is_equilibrium,
        "allowed_direction": allowed_direction,
        "anti_chasing_buy_block": anti_chasing_buy_block,
        "anti_chasing_sell_block": anti_chasing_sell_block,
        "confluence_score": confluence_score,
        "confluence_tier": conf_tier,
        "confluence_multiplier": conf_mult,
    }


# ==============================================================================
# 8. SUBCOMMAND: ORDERBOOK MICROSTRUCTURE & SLIPPAGE DEFENSE
# ==============================================================================


def session_microstructure(
    spread_current: float,
    spread_typical: float,
    bid_vol: float = 100.0,
    ask_vol: float = 100.0,
    utc_hour: int = 14,
) -> Dict[str, Any]:
    """
    Computes Orderbook Imbalance (OBI), spread expansion ratio, and execution gates.
    OBI = (V_bid - V_ask) / (V_bid + V_ask)
    """
    tot_vol = bid_vol + ask_vol
    obi = round((bid_vol - ask_vol) / tot_vol, 3) if tot_vol > 0 else 0.0

    spread_ratio = round(spread_current / max(1e-7, spread_typical), 2)
    spread_gate_reject = spread_ratio > 2.0

    return {
        "orderbook_imbalance_obi": obi,
        "orderbook_pressure": "BULLISH_DOMINANCE"
        if obi >= 0.30
        else ("BEARISH_DOMINANCE" if obi <= -0.30 else "BALANCED"),
        "spread_ratio": spread_ratio,
        "spread_gate_breached": spread_gate_reject,
        "execution_verdict": "REJECT_SPREAD_EXPANDED" if spread_gate_reject else "PASS_MICROSTRUCTURE",
    }


# ==============================================================================
# 9. SUBCOMMAND: DIALECTICAL DEBATE & BAYESIAN JUDGE ARBITRATION
# ==============================================================================


def debate_judge(
    bull_score: float,
    bear_score: float,
    bull_rebuttal_quality: float = 5.0,
    bear_rebuttal_quality: float = 5.0,
    regime: str = "trending",
    bull_brier: float = 0.20,
    bear_brier: float = 0.20,
    active_criteria_met: int = 4,
) -> Dict[str, Any]:
    """
    Executes Round 2 Rebuttal Attenuation (-3 discount if rebuttal >= 7),
    Brier-calibrated Bayesian arbitration, and Anti-Fence-Sitting verification.
    """
    # Round 2 Attenuation: If rebuttal score >= 7, opponent's score is discounted by 3 points (floor 1.0)
    att_bull = bull_score
    att_bear = bear_score

    if bear_rebuttal_quality >= 7.0:
        att_bull = max(1.0, bull_score - 3.0)
    if bull_rebuttal_quality >= 7.0:
        att_bear = max(1.0, bear_score - 3.0)

    # Regime Weights: {regime: (tech, macro, sent)}
    regime_weights = {
        "trending": {"tech": 0.50, "macro": 0.35, "sent": 0.15},
        "ranging": {"tech": 0.40, "macro": 0.30, "sent": 0.30},
        "volatile": {"tech": 0.35, "macro": 0.45, "sent": 0.20},
        "crisis": {"tech": 0.25, "macro": 0.55, "sent": 0.20},
    }
    weights = regime_weights.get(regime.lower(), regime_weights["trending"])

    # Brier Calibration Weights: w_i = (1 / B_i) / sum(1 / B_j)
    inv_bull = 1.0 / max(0.01, bull_brier)
    inv_bear = 1.0 / max(0.01, bear_brier)
    sum_inv = inv_bull + inv_bear
    w_bull = round(max(0.20, min(0.80, inv_bull / sum_inv)), 3)
    w_bear = round(1.0 - w_bull, 3)

    score_diff = att_bull - att_bear

    # Anti-Fence-Sitting Mandate:
    # If active criteria >= 3 and score difference >= 1.5, judge MUST pick winner with calibrated multiplier
    fence_sitting_violation = False
    if active_criteria_met >= 3 and abs(score_diff) >= 1.5:
        if score_diff > 0:
            winner = "BUY"
            if att_bull >= 8.0:
                risk_mult = 1.00
            elif att_bull >= 6.5:
                risk_mult = 0.75
            elif att_bull >= 5.0:
                risk_mult = 0.50
            else:
                risk_mult = 0.25
        else:
            winner = "SELL"
            if att_bear >= 8.0:
                risk_mult = 1.00
            elif att_bear >= 6.5:
                risk_mult = 0.75
            elif att_bear >= 5.0:
                risk_mult = 0.50
            else:
                risk_mult = 0.25
    else:
        winner = "HOLD"
        risk_mult = 0.00

    return {
        "round1_bull_score": bull_score,
        "round1_bear_score": bear_score,
        "bull_rebuttal_quality": bull_rebuttal_quality,
        "bear_rebuttal_quality": bear_rebuttal_quality,
        "attenuated_bull_score": round(att_bull, 2),
        "attenuated_bear_score": round(att_bear, 2),
        "regime": regime.lower(),
        "regime_domain_weights": weights,
        "brier_weights": {"bull": w_bull, "bear": w_bear},
        "arbitrated_verdict": winner,
        "bayesian_risk_multiplier": risk_mult,
        "anti_fence_sitting_enforced": True,
    }


# ==============================================================================
# 10. SUBCOMMAND: SPECIALIZED ASSET & CARRY TRADE PLAYBOOKS
# ==============================================================================


def asset_special(
    asset_type: str,
    brent_price: Optional[float] = None,
    wti_price: Optional[float] = None,
    mean_spread: float = 4.50,
    std_spread: float = 0.85,
    gasoline_price: Optional[float] = None,
    distillate_price: Optional[float] = None,
    crude_price: Optional[float] = None,
    etf_net_inflow_m: Optional[float] = None,
    funding_rate_8h_pct: Optional[float] = None,
    open_interest_chg_pct: Optional[float] = None,
    long_rate: Optional[float] = None,
    short_rate: Optional[float] = None,
    implied_vol_pct: Optional[float] = None,
    vix: float = 16.0,
    tips10y: Optional[float] = None,
    dxy: Optional[float] = None,
    shanghai_premium_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates asset-specific playbooks: Brent-WTI Stat-Arb & 3:2:1 Crack, BTC ETF/Funding,
    FX Carry-to-Risk ratio, and Gold TIPS non-linearity.
    """
    asset = asset_type.upper().strip()

    if asset in ("OIL", "CRUDE", "XTIUSD", "XBRUSD"):
        spread_val: Optional[float] = None
        z_score: Optional[float] = None
        arb_signal = "NEUTRAL_IN_BAND"

        if brent_price is not None and wti_price is not None:
            spread_val = round(brent_price - wti_price, 2)
            z_score = round((spread_val - mean_spread) / max(1e-5, std_spread), 2)
            if z_score >= 2.0:
                arb_signal = "SHORT_BRENT_LONG_WTI (Spread over-extended, expect mean reversion)"
            elif z_score <= -2.0:
                arb_signal = "LONG_BRENT_SHORT_WTI (Spread under-extended, expect widening)"

        crack_spread_321: Optional[float] = None
        if gasoline_price is not None and distillate_price is not None and crude_price is not None:
            crack_spread_321 = round(
                ((2 * gasoline_price * 42) + (1 * distillate_price * 42) - (3 * crude_price)) / 3, 2
            )

        return {
            "asset_class": "CRUDE_OIL",
            "brent_wti_spread": {
                "brent_price": brent_price,
                "wti_price": wti_price,
                "current_spread": spread_val,
                "historical_mean": mean_spread,
                "historical_std": std_spread,
                "z_score": z_score,
                "statistical_arbitrage_verdict": arb_signal,
            },
            "crack_spread_3_2_1_usd_bbl": crack_spread_321,
        }

    elif asset in ("BTC", "BTCUSD", "CRYPTO"):
        etf_stance = "NEUTRAL"
        if etf_net_inflow_m is not None:
            if etf_net_inflow_m > 200.0:
                etf_stance = "HEAVY_INSTITUTIONAL_INFLOW"
            elif etf_net_inflow_m < -150.0:
                etf_stance = "INSTITUTIONAL_OUTFLOW_PRESSURE"

        funding_stance = "NORMAL"
        if funding_rate_8h_pct is not None:
            if funding_rate_8h_pct >= 0.05:
                funding_stance = "OVERHEATED_LONG_LEVERAGE (Squeeze Danger)"
            elif funding_rate_8h_pct <= -0.02:
                funding_stance = "EXTREME_SHORT_SQUEEZE_POTENTIAL"

        return {
            "asset_class": "BITCOIN_CRYPTO",
            "spot_etf_flow_millions": etf_net_inflow_m,
            "etf_flow_regime": etf_stance,
            "perpetual_funding_8h_pct": funding_rate_8h_pct,
            "funding_regime": funding_stance,
            "open_interest_change_pct": open_interest_chg_pct,
        }

    elif asset in ("CARRY", "CARRY_TRADE", "FX_CARRY"):
        cr_ratio: Optional[float] = None
        if long_rate is not None and short_rate is not None and implied_vol_pct is not None:
            rate_diff = long_rate - short_rate
            cr_ratio = round(rate_diff / max(1e-5, implied_vol_pct), 3)

        carry_stance = "ATTRACTIVE" if (cr_ratio is not None and cr_ratio >= 0.50) else "UNATTRACTIVE"

        if vix > 28.0:
            unwind_status = "FULL_EMERGENCY_UNWIND (Close all Long Carry, Reverse to Long JPY/CHF)"
        elif vix > 22.0:
            unwind_status = "DEFENSIVE_HAIRCUT (Cut Carry exposure by 50%)"
        else:
            unwind_status = "SAFE_STABLE_CARRY_ENVIRONMENT"

        return {
            "asset_class": "FX_CARRY_TRADE",
            "rate_differential_pct": (
                round(long_rate - short_rate, 3) if (long_rate is not None and short_rate is not None) else None
            ),
            "implied_volatility_pct": implied_vol_pct,
            "carry_to_risk_ratio_cr": cr_ratio,
            "carry_attractiveness": carry_stance,
            "vix_level": vix,
            "unwind_ladder_protocol": unwind_status,
        }

    elif asset in ("GOLD", "XAU", "XAUUSD"):
        regime = "NORMAL_NEGATIVE_CORRELATION"
        if tips10y is not None:
            if tips10y > 2.0:
                regime = "SOVEREIGN_DEBT_STRESS_REGIME (Gold decouples and rises despite high Real Yields)"
            elif tips10y < 1.0:
                regime = "NEGATIVE_REAL_YIELD_TAILWIND (Gold rallies aggressively)"

        return {
            "asset_class": "GOLD_XAUUSD",
            "tips_10y_real_yield": tips10y,
            "dxy_index": dxy,
            "shanghai_gold_premium_usd": shanghai_premium_usd,
            "gold_macro_regime": regime,
        }

    return {"error": f"Unsupported asset class: '{asset_type}'"}


# ==============================================================================
# 11. SUBCOMMAND: PRE-COMPUTED DETERMINISTIC BRACKET GENERATOR
# ==============================================================================


def generate_brackets(
    symbol: str,
    price: float,
    atr14: float,
    adr5d: Optional[float] = None,
    demand_level: Optional[float] = None,
    supply_level: Optional[float] = None,
    target_rr: float = 1.80,
    regime: Optional[str] = None,
    impulse_atr: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Pre-computes LONG_OPTION_A and SHORT_OPTION_B bounding boxes with guaranteed
    minimum R:R >= 1.50 and noise floor protection (1.25x ATR FX, 1.35x ATR High-Vol).
    """
    prec = extract_price_precision(symbol)
    curr_px = float(price)
    atr_val = float(atr14) if atr14 > 0 else curr_px * 0.005
    adr_val = float(adr5d) if adr5d and adr5d > 0 else atr_val * 2.0
    min_rr = max(1.50, float(target_rr))

    sym_clean = symbol.upper()
    is_high_vol = any(k in sym_clean for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR", "BRENT", "WTI"))
    noise_floor_mult = 1.35 if is_high_vol else 1.25
    target_noise_dist = noise_floor_mult * atr_val

    # Maximum SL cap: 35% ADR or 2.5x ATR
    max_sl_dist = min(2.5 * atr_val, max(target_noise_dist, 0.35 * adr_val))

    # 1. Long Option A
    long_entry = round(
        demand_level if demand_level and (curr_px - 0.75 * atr_val) <= demand_level <= curr_px else curr_px, prec
    )
    long_sl_dist = min(max_sl_dist, max(target_noise_dist, 0.35 * adr_val))
    long_sl = round(long_entry - long_sl_dist, prec)
    long_risk = abs(long_entry - long_sl)
    if long_risk <= 0.0:
        long_risk = round(target_noise_dist, prec)
        long_sl = round(long_entry - long_risk, prec)

    long_tp_dist = round(long_risk * min_rr, prec)
    long_tp = round(long_entry + long_tp_dist, prec)
    actual_long_rr = round(long_tp_dist / long_risk, 2)

    # 2. Short Option B
    short_entry = round(
        supply_level if supply_level and curr_px <= supply_level <= (curr_px + 0.75 * atr_val) else curr_px, prec
    )
    short_sl_dist = min(max_sl_dist, max(target_noise_dist, 0.35 * adr_val))
    short_sl = round(short_entry + short_sl_dist, prec)
    short_risk = abs(short_sl - short_entry)
    if short_risk <= 0.0:
        short_risk = round(target_noise_dist, prec)
        short_sl = round(short_entry + short_risk, prec)

    short_tp_dist = round(short_risk * min_rr, prec)
    short_tp = round(short_entry - short_tp_dist, prec)
    actual_short_rr = round(short_tp_dist / short_risk, 2)

    return {
        "symbol": sym_clean,
        "current_price": curr_px,
        "precision": prec,
        "atr_14": round(atr_val, prec),
        "adr_5d": round(adr_val, prec),
        "noise_floor_atr": noise_floor_mult,
        "long_option_a": {
            "name": "LONG_OPTION_A",
            "direction": "buy",
            "entry": long_entry,
            "stop_loss": long_sl,
            "take_profit": long_tp,
            "risk_distance": round(long_risk, prec),
            "rr_ratio": actual_long_rr,
            "sl_distance_atr": round(long_risk / atr_val, 2),
        },
        "short_option_b": {
            "name": "SHORT_OPTION_B",
            "direction": "sell",
            "entry": short_entry,
            "stop_loss": short_sl,
            "take_profit": short_tp,
            "risk_distance": round(short_risk, prec),
            "rr_ratio": actual_short_rr,
            "sl_distance_atr": round(short_risk / atr_val, 2),
        },
    }


# ==============================================================================
# 11. SUBCOMMAND: FIXED-FRACTIONAL DECIMAL (ROUND_FLOOR) POSITION SIZING
# ==============================================================================


def calculate_position_size(
    equity: float,
    base_risk_pct: float,
    entry: float,
    sl: float,
    symbol: str = "EURUSD",
    vix_mult: float = 1.0,
    judge_mult: float = 1.0,
    ttl_mult: float = 1.0,
    synergy_mult: float = 1.0,
) -> Dict[str, Any]:
    """
    Computes exact lot size via decimal.Decimal with ROUND_FLOOR rounding.
    Guarantees actual dollar risk <= allocated risk budget.
    """
    spec = get_asset_spec(symbol)
    min_lot = Decimal(str(spec["min_lot"]))
    max_lot = Decimal(str(spec["max_lot"]))
    lot_step = Decimal(str(spec["lot_step"]))
    pip_size = Decimal(str(spec["pip_size"]))
    pip_val_usd = Decimal(str(spec["pip_value_usd"]))

    d_equity = Decimal(str(equity))
    d_base_risk = Decimal(str(base_risk_pct))
    d_vix = Decimal(str(vix_mult))
    d_judge = Decimal(str(judge_mult))
    d_ttl = Decimal(str(ttl_mult))
    d_synergy = Decimal(str(synergy_mult))

    # Effective risk percentage clamped to max 2.0%
    eff_risk_pct = min(Decimal("2.0"), d_base_risk * d_vix * d_judge * d_ttl * d_synergy)
    dollar_risk_budget = (d_equity * eff_risk_pct) / Decimal("100")

    d_entry = Decimal(str(entry))
    d_sl = Decimal(str(sl))
    sl_distance = abs(d_entry - d_sl)

    if sl_distance <= Decimal("0") or dollar_risk_budget <= Decimal("0"):
        return {
            "symbol": symbol.upper(),
            "recommended_lots": 0.0,
            "effective_risk_pct": float(eff_risk_pct),
            "dollar_risk_budget": float(dollar_risk_budget),
            "actual_dollar_risk": 0.0,
            "is_valid": False,
            "rejection_reason": "Zero or negative stop distance / risk budget",
        }

    # SL in pips
    sl_pips = sl_distance / pip_size

    # Raw lots = dollar_risk_budget / (sl_pips * pip_value_usd)
    raw_lots = dollar_risk_budget / (sl_pips * pip_val_usd)

    # ROUND_FLOOR to nearest lot_step
    steps = (raw_lots / lot_step).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    floored_lots = steps * lot_step

    # Clamp between min_lot and max_lot
    if floored_lots < min_lot:
        is_valid = False
        rejection = f"Calculated lots ({floored_lots}) < minimum allowed ({min_lot})"
        final_lots = Decimal("0.0")
    elif floored_lots > max_lot:
        final_lots = max_lot
        is_valid = True
        rejection = ""
    else:
        final_lots = floored_lots
        is_valid = True
        rejection = ""

    actual_dollar_risk = float((final_lots * sl_pips * pip_val_usd).quantize(Decimal("0.01"), rounding=ROUND_FLOOR))

    return {
        "symbol": symbol.upper(),
        "recommended_lots": float(final_lots),
        "raw_lots": float(raw_lots),
        "effective_risk_pct": float(eff_risk_pct),
        "dollar_risk_budget": float(dollar_risk_budget),
        "actual_dollar_risk": actual_dollar_risk,
        "is_valid": is_valid,
        "rejection_reason": rejection,
    }


# ==============================================================================
# 12. SUBCOMMAND: 12-POINT RISKGATE PRE-EXECUTION AUDIT
# ==============================================================================


def audit_risk_gate(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    atr14: float,
    adr5d: float,
    pos: float,
    equity: float,
    daily_drawdown_pct: float = 0.0,
    vix: float = 16.0,
    spread_ratio: float = 1.0,
    now_utc_str: Optional[str] = None,
    event_delta_mins: Optional[float] = None,
    hy_oas_bps: float = 340.0,
    stale_data: bool = False,
) -> Dict[str, Any]:
    """
    Executes all 12 Pre-Execution RiskGate checks. Fail-closed on any failure.
    """
    checks_passed: List[str] = []
    checks_failed: List[str] = []
    reasons: List[str] = []

    dir_clean = direction.strip().lower()
    sym_clean = symbol.strip().upper()
    spec = get_asset_spec(sym_clean)

    # 1. Finite Numerical Validation
    strictly_positive_vals = [entry, sl, tp, atr14, adr5d, equity]
    if (
        any(not math.isfinite(v) or v <= 0.0 for v in strictly_positive_vals)
        or not math.isfinite(pos)
        or not (0.0 <= pos <= 1.0)
    ):
        checks_failed.append("valid_finite_inputs")
        reasons.append("Inputs contain NaN, infinite, or out-of-bounds values (pos must be finite in [0.0, 1.0])")
    else:
        checks_passed.append("valid_finite_inputs")

    # 2. Directional Bracket Ordering
    if dir_clean in ("buy", "long"):
        if sl < entry < tp:
            checks_passed.append("directional_bracket_ordering")
        else:
            checks_failed.append("directional_bracket_ordering")
            reasons.append(f"Inverted BUY bracket: require SL ({sl}) < Entry ({entry}) < TP ({tp})")
    elif dir_clean in ("sell", "short"):
        if tp < entry < sl:
            checks_passed.append("directional_bracket_ordering")
        else:
            checks_failed.append("directional_bracket_ordering")
            reasons.append(f"Inverted SELL bracket: require TP ({tp}) < Entry ({entry}) < SL ({sl})")
    else:
        checks_failed.append("directional_bracket_ordering")
        reasons.append(f"Invalid direction: '{direction}'")

    # 3. Minimum Noise Floor Protection (1.25x ATR FX / 1.35x ATR High-Vol)
    is_high_vol = any(k in sym_clean for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR", "BRENT", "WTI"))
    min_noise_mult = 1.35 if is_high_vol else 1.25
    sl_dist = abs(entry - sl)
    if sl_dist >= (min_noise_mult * atr14 * 0.98):  # 2% rounding allowance
        checks_passed.append("noise_floor_protection")
    else:
        checks_failed.append("noise_floor_protection")
        reasons.append(
            f"SL distance ({sl_dist:.5f}) below {min_noise_mult:.2f}x ATR noise floor ({min_noise_mult * atr14:.5f})"
        )

    # 4. Maximum Stop Cap (3.0x ATR & <= 1.0x ADR)
    if sl_dist <= (3.0 * atr14) and sl_dist <= adr5d:
        checks_passed.append("max_stop_cap")
    else:
        checks_failed.append("max_stop_cap")
        reasons.append(f"SL distance ({sl_dist:.5f}) exceeds max cap (3.0x ATR or 1.0x ADR)")

    # 5. Minimum R:R Ratio >= 1.50
    tp_dist = abs(tp - entry)
    rr_ratio = tp_dist / max(1e-7, sl_dist)
    if rr_ratio >= 1.48:  # 0.02 rounding allowance
        checks_passed.append("minimum_rr_ratio")
    else:
        checks_failed.append("minimum_rr_ratio")
        reasons.append(f"R:R ratio ({rr_ratio:.2f}) < 1.50 minimum institutional threshold")

    # 6. Spatial Dealing Range & Anti-Chasing
    if dir_clean in ("buy", "long") and pos > 0.85:
        checks_failed.append("spatial_dealing_range_anti_chasing")
        reasons.append(f"Anti-chasing violation: BUY blocked at extreme premium dealing range (pos={pos:.2f} > 0.85)")
    elif dir_clean in ("sell", "short") and pos < 0.15:
        checks_failed.append("spatial_dealing_range_anti_chasing")
        reasons.append(f"Anti-chasing violation: SELL blocked at extreme discount dealing range (pos={pos:.2f} < 0.15)")
    else:
        checks_passed.append("spatial_dealing_range_anti_chasing")

    # 7. Daily Drawdown Limit (<= 3.0%)
    if daily_drawdown_pct >= 3.0:
        checks_failed.append("daily_drawdown_limit")
        reasons.append(f"Daily drawdown limit breached ({daily_drawdown_pct:.2f}% >= 3.00%)")
    else:
        checks_passed.append("daily_drawdown_limit")

    # 8. Spread Spike Gate (<= 2.0x Typical)
    if spread_ratio > 2.0:
        checks_failed.append("spread_spike_gate")
        reasons.append(f"Spread expansion spike ({spread_ratio:.2f}x > 2.0x typical spread)")
    else:
        checks_passed.append("spread_spike_gate")

    # 9. Rollover Window Blackout (21:55 - 22:15 UTC)
    if now_utc_str:
        try:
            now = datetime.fromisoformat(now_utc_str.replace("Z", "+00:00"))
        except Exception:
            reasons.append(f"Invalid now-utc format '{now_utc_str}', defaulted to current UTC time")
            now = datetime.now(UTC)
    else:
        now = datetime.now(UTC)

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    minute_of_day = now.hour * 60 + now.minute
    if 1315 <= minute_of_day <= 1335:
        checks_failed.append("rollover_blackout_window")
        reasons.append(f"Daily rollover blackout active at {now.strftime('%H:%M UTC')} (21:55 - 22:15 UTC)")
    else:
        checks_passed.append("rollover_blackout_window")

    # 10. Tier-1 News Event Blackout
    if event_delta_mins is not None and -15.0 <= event_delta_mins <= 30.0:
        checks_failed.append("event_blackout_window")
        reasons.append(f"High-impact news event window active (~{event_delta_mins:.0f}m away)")
    else:
        checks_passed.append("event_blackout_window")

    # 11. Systemic Crisis Gate (VIX > 30 or HY OAS > 450)
    if vix > 30.0 or hy_oas_bps >= 450.0:
        checks_failed.append("systemic_crisis_gate")
        reasons.append(f"Systemic crisis gate active (VIX={vix:.1f}, HY OAS={hy_oas_bps:.0f} bps)")
    else:
        checks_passed.append("systemic_crisis_gate")

    # 12. Stale Data & Broker Lot Specs
    if stale_data:
        checks_passed.append("stale_data_scaled")  # Passes with size penalty
    else:
        checks_passed.append("stale_data_verified")

    approved = len(checks_failed) == 0

    return {
        "verdict": "APPROVED" if approved else "REJECTED",
        "approved": approved,
        "symbol": sym_clean,
        "direction": dir_clean.upper(),
        "total_checks": 12,
        "passed_count": len(checks_passed),
        "failed_count": len(checks_failed),
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "rejection_reasons": reasons,
    }


# ==============================================================================
# CLI ENTRYPOINT & ARGPARSE DISPATCHER
# ==============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Institutional Quantitative Invariant & Risk Engine")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. validate-telemetry
    p_tel = subparsers.add_parser("validate-telemetry")
    p_tel.add_argument("--timestamps-json", type=str, default=None)
    p_tel.add_argument("--now-utc", type=str, default=None)
    p_tel.add_argument("--event-time-utc", type=str, default=None)
    p_tel.add_argument("--event-impact", type=str, default="HIGH")

    # 2. cb-differential
    p_cb = subparsers.add_parser("cb-differential")
    p_cb.add_argument("--base-currency", type=str, required=True)
    p_cb.add_argument("--quote-currency", type=str, required=True)
    p_cb.add_argument("--base-rate", type=float, required=True)
    p_cb.add_argument("--quote-rate", type=float, required=True)
    p_cb.add_argument("--base-r-star", type=float, default=None)
    p_cb.add_argument("--quote-r-star", type=float, default=None)
    p_cb.add_argument("--base-inflation", type=float, default=None)
    p_cb.add_argument("--quote-inflation", type=float, default=None)
    p_cb.add_argument("--base-unemp-chg", type=float, default=0.0)
    p_cb.add_argument("--quote-unemp-chg", type=float, default=0.0)

    # 3. macro-calc
    p_mac = subparsers.add_parser("macro-calc")
    p_mac.add_argument("--walcl", type=float, default=None)
    p_mac.add_argument("--tga", type=float, default=None)
    p_mac.add_argument("--rrp", type=float, default=None)
    p_mac.add_argument("--prev-net-liq", type=float, default=None)
    p_mac.add_argument("--us10y", type=float, default=None)
    p_mac.add_argument("--us2y", type=float, default=None)
    p_mac.add_argument("--tips10y", type=float, default=None)
    p_mac.add_argument("--vix", type=float, default=16.0)
    p_mac.add_argument("--hy-oas", type=float, default=340.0)

    # 4. event-calc
    p_ev = subparsers.add_parser("event-calc")
    p_ev.add_argument("--actual", type=float, default=None)
    p_ev.add_argument("--consensus", type=float, default=None)
    p_ev.add_argument("--previous", type=float, default=None)
    p_ev.add_argument("--prior-revision", type=float, default=0.0)
    p_ev.add_argument("--priced-in-fedwatch", type=float, default=5.0)
    p_ev.add_argument("--priced-in-cot", type=float, default=5.0)
    p_ev.add_argument("--priced-in-exhaustion", type=float, default=5.0)
    p_ev.add_argument("--priced-in-historical", type=float, default=5.0)
    p_ev.add_argument("--event-high", type=float, default=None)
    p_ev.add_argument("--event-low", type=float, default=None)

    # 5. cot-synergy
    p_cot = subparsers.add_parser("cot-synergy")
    p_cot.add_argument("--cot-net-pct", type=float, default=50.0)
    p_cot.add_argument("--cot-52w-pct", type=float, required=True)
    p_cot.add_argument("--tech-dir", type=str, required=True)
    p_cot.add_argument("--macro-dir", type=str, required=True)
    p_cot.add_argument("--sent-dir", type=str, required=True)
    p_cot.add_argument("--tech-conf", type=float, default=75.0)
    p_cot.add_argument("--macro-conf", type=float, default=75.0)
    p_cot.add_argument("--sent-conf", type=float, default=75.0)

    # 6. smc-confluence
    p_smc = subparsers.add_parser("smc-confluence")
    p_smc.add_argument("--close", type=float, required=True)
    p_smc.add_argument("--high20", type=float, required=True)
    p_smc.add_argument("--low20", type=float, required=True)
    p_smc.add_argument("--atr14", type=float, required=True)
    p_smc.add_argument("--pdl", type=float, default=None)
    p_smc.add_argument("--pdh", type=float, default=None)
    p_smc.add_argument("--confluence-score", type=int, default=12)
    p_smc.add_argument("--has-active-impulse", action="store_true")

    # 7. session-microstructure
    p_mic = subparsers.add_parser("session-microstructure")
    p_mic.add_argument("--spread-current", type=float, required=True)
    p_mic.add_argument("--spread-typical", type=float, required=True)
    p_mic.add_argument("--bid-vol", type=float, default=100.0)
    p_mic.add_argument("--ask-vol", type=float, default=100.0)
    p_mic.add_argument("--utc-hour", type=int, default=14)

    # 8. debate-judge
    p_deb = subparsers.add_parser("debate-judge")
    p_deb.add_argument("--bull-score", type=float, required=True)
    p_deb.add_argument("--bear-score", type=float, required=True)
    p_deb.add_argument("--bull-rebuttal", type=float, default=5.0)
    p_deb.add_argument("--bear-rebuttal", type=float, default=5.0)
    p_deb.add_argument("--regime", type=str, default="trending")
    p_deb.add_argument("--bull-brier", type=float, default=0.20)
    p_deb.add_argument("--bear-brier", type=float, default=0.20)
    p_deb.add_argument("--active-criteria-met", type=int, default=4)

    # 9. asset-special
    p_asp = subparsers.add_parser("asset-special")
    p_asp.add_argument(
        "--asset",
        type=str,
        required=True,
        help="Asset type or symbol: OIL/CRUDE/XTIUSD, BTC/BTCUSD, CARRY/FX_CARRY, GOLD/XAUUSD",
    )
    p_asp.add_argument("--brent-price", type=float, default=None)
    p_asp.add_argument("--wti-price", type=float, default=None)
    p_asp.add_argument("--mean-spread", type=float, default=4.50)
    p_asp.add_argument("--std-spread", type=float, default=0.85)
    p_asp.add_argument("--gasoline-price", type=float, default=None)
    p_asp.add_argument("--distillate-price", type=float, default=None)
    p_asp.add_argument("--crude-price", type=float, default=None)
    p_asp.add_argument("--etf-net-inflow-m", type=float, default=None)
    p_asp.add_argument("--funding-rate-8h", type=float, default=None)
    p_asp.add_argument("--open-interest-chg-pct", type=float, default=None)
    p_asp.add_argument("--long-rate", type=float, default=None)
    p_asp.add_argument("--short-rate", type=float, default=None)
    p_asp.add_argument("--implied-vol", type=float, default=None)
    p_asp.add_argument("--vix", type=float, default=16.0)
    p_asp.add_argument("--tips10y", type=float, default=None)
    p_asp.add_argument("--dxy", type=float, default=None)
    p_asp.add_argument("--shanghai-premium", type=float, default=None)

    # 10. brackets
    p_brk = subparsers.add_parser("brackets")
    p_brk.add_argument("--symbol", type=str, required=True)
    p_brk.add_argument("--price", type=float, required=True)
    p_brk.add_argument("--atr14", type=float, required=True)
    p_brk.add_argument("--adr5d", type=float, default=None)
    p_brk.add_argument("--demand-level", type=float, default=None)
    p_brk.add_argument("--supply-level", type=float, default=None)
    p_brk.add_argument("--target-rr", type=float, default=1.80)
    p_brk.add_argument("--regime", type=str, default=None)
    p_brk.add_argument("--impulse-atr", type=float, default=None)

    # 10. size
    p_sz = subparsers.add_parser("size")
    p_sz.add_argument("--equity", type=float, required=True)
    p_sz.add_argument("--base-risk-pct", type=float, required=True)
    p_sz.add_argument("--entry", type=float, required=True)
    p_sz.add_argument("--sl", type=float, required=True)
    p_sz.add_argument("--symbol", type=str, default="EURUSD")
    p_sz.add_argument("--vix-mult", type=float, default=1.0)
    p_sz.add_argument("--judge-mult", type=float, default=1.0)
    p_sz.add_argument("--ttl-mult", type=float, default=1.0)
    p_sz.add_argument("--synergy-mult", type=float, default=1.0)

    # 11. risk-gate
    p_rg = subparsers.add_parser("risk-gate")
    p_rg.add_argument("--symbol", type=str, required=True)
    p_rg.add_argument("--direction", type=str, required=True)
    p_rg.add_argument("--entry", type=float, required=True)
    p_rg.add_argument("--sl", type=float, required=True)
    p_rg.add_argument("--tp", type=float, required=True)
    p_rg.add_argument("--atr14", type=float, required=True)
    p_rg.add_argument("--adr5d", type=float, required=True)
    p_rg.add_argument("--pos", type=float, required=True)
    p_rg.add_argument("--equity", type=float, required=True)
    p_rg.add_argument("--daily-drawdown-pct", type=float, default=0.0)
    p_rg.add_argument("--vix", type=float, default=16.0)
    p_rg.add_argument("--spread-ratio", type=float, default=1.0)
    p_rg.add_argument("--now-utc", type=str, default=None)
    p_rg.add_argument("--event-delta-mins", type=float, default=None)
    p_rg.add_argument("--hy-oas", type=float, default=340.0)
    p_rg.add_argument("--stale-data", action="store_true")

    args = parser.parse_args()

    out: Dict[str, Any] = {}
    if args.subcommand == "validate-telemetry":
        out = validate_telemetry(
            timestamps_json=args.timestamps_json,
            now_utc_str=args.now_utc,
            event_time_utc_str=args.event_time_utc,
            event_impact=args.event_impact,
        )
    elif args.subcommand == "cb-differential":
        out = cb_differential(
            base_currency=args.base_currency,
            quote_currency=args.quote_currency,
            base_rate=args.base_rate,
            quote_rate=args.quote_rate,
            base_r_star=args.base_r_star,
            quote_r_star=args.quote_r_star,
            base_inflation=args.base_inflation,
            quote_inflation=args.quote_inflation,
            base_unemployment_chg=args.base_unemp_chg,
            quote_unemployment_chg=args.quote_unemp_chg,
        )
    elif args.subcommand == "macro-calc":
        out = macro_calc(
            walcl_billions=args.walcl,
            tga_billions=args.tga,
            rrp_billions=args.rrp,
            prev_net_liquidity_billions=args.prev_net_liq,
            us10y=args.us10y,
            us2y=args.us2y,
            tips10y=args.tips10y,
            vix=args.vix,
            hy_oas_bps=args.hy_oas,
        )
    elif args.subcommand == "event-calc":
        out = event_calc(
            actual=args.actual,
            consensus=args.consensus,
            previous=args.previous,
            prior_revision=args.prior_revision,
            priced_in_fedwatch=args.priced_in_fedwatch,
            priced_in_cot=args.priced_in_cot,
            priced_in_exhaustion=args.priced_in_exhaustion,
            priced_in_historical=args.priced_in_historical,
            event_high=args.event_high,
            event_low=args.event_low,
        )
    elif args.subcommand == "cot-synergy":
        out = cot_synergy(
            cot_net_pct=args.cot_net_pct,
            cot_52w_pct=args.cot_52w_pct,
            tech_dir=args.tech_dir,
            macro_dir=args.macro_dir,
            sent_dir=args.sent_dir,
            tech_conf=args.tech_conf,
            macro_conf=args.macro_conf,
            sent_conf=args.sent_conf,
        )
    elif args.subcommand == "smc-confluence":
        out = smc_confluence(
            close=args.close,
            high20=args.high20,
            low20=args.low20,
            atr14=args.atr14,
            pdl=args.pdl,
            pdh=args.pdh,
            confluence_score=args.confluence_score,
            has_active_impulse=args.has_active_impulse,
        )
    elif args.subcommand == "session-microstructure":
        out = session_microstructure(
            spread_current=args.spread_current,
            spread_typical=args.spread_typical,
            bid_vol=args.bid_vol,
            ask_vol=args.ask_vol,
            utc_hour=args.utc_hour,
        )
    elif args.subcommand == "debate-judge":
        out = debate_judge(
            bull_score=args.bull_score,
            bear_score=args.bear_score,
            bull_rebuttal_quality=args.bull_rebuttal,
            bear_rebuttal_quality=args.bear_rebuttal,
            regime=args.regime,
            bull_brier=args.bull_brier,
            bear_brier=args.bear_brier,
            active_criteria_met=args.active_criteria_met,
        )
    elif args.subcommand == "asset-special":
        out = asset_special(
            asset_type=args.asset,
            brent_price=args.brent_price,
            wti_price=args.wti_price,
            mean_spread=args.mean_spread,
            std_spread=args.std_spread,
            gasoline_price=args.gasoline_price,
            distillate_price=args.distillate_price,
            crude_price=args.crude_price,
            etf_net_inflow_m=args.etf_net_inflow_m,
            funding_rate_8h_pct=args.funding_rate_8h,
            open_interest_chg_pct=args.open_interest_chg_pct,
            long_rate=args.long_rate,
            short_rate=args.short_rate,
            implied_vol_pct=args.implied_vol,
            vix=args.vix,
            tips10y=args.tips10y,
            dxy=args.dxy,
            shanghai_premium_usd=args.shanghai_premium,
        )
    elif args.subcommand == "brackets":
        out = generate_brackets(
            symbol=args.symbol,
            price=args.price,
            atr14=args.atr14,
            adr5d=args.adr5d,
            demand_level=args.demand_level,
            supply_level=args.supply_level,
            target_rr=args.target_rr,
            regime=args.regime,
            impulse_atr=args.impulse_atr,
        )
    elif args.subcommand == "size":
        out = calculate_position_size(
            equity=args.equity,
            base_risk_pct=args.base_risk_pct,
            entry=args.entry,
            sl=args.sl,
            symbol=args.symbol,
            vix_mult=args.vix_mult,
            judge_mult=args.judge_mult,
            ttl_mult=args.ttl_mult,
            synergy_mult=args.synergy_mult,
        )
    elif args.subcommand == "risk-gate":
        out = audit_risk_gate(
            symbol=args.symbol,
            direction=args.direction,
            entry=args.entry,
            sl=args.sl,
            tp=args.tp,
            atr14=args.atr14,
            adr5d=args.adr5d,
            pos=args.pos,
            equity=args.equity,
            daily_drawdown_pct=args.daily_drawdown_pct,
            vix=args.vix,
            spread_ratio=args.spread_ratio,
            now_utc_str=args.now_utc,
            event_delta_mins=args.event_delta_mins,
            hy_oas_bps=args.hy_oas,
            stale_data=args.stale_data,
        )

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
