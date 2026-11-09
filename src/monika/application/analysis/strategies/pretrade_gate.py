import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.calculators.regime_classifier import (
    classify_market_regime,
    compute_bollinger_donchian_chop,
)
from monika.application.analysis.calculators.volume_profile import compute_volume_profile
from monika.core.validation.data_validator import is_crypto_symbol

logger = logging.getLogger("TradingAgent.PreTradeGate")

TOXIC_STRATEGIES: set[str] = {
    "liquidity_sweep",
    "bb_volume_profile",
    "smt_divergence",
}

TOXIC_PAIRS: set[tuple[str, str]] = {
    ("asian_range_fade", "EURUSD"),
    ("vwap_mean_reversion", "EURUSD"),
    ("vwap_mean_reversion", "AUDUSD"),
    ("vwap_mean_reversion", "XTIUSD"),
    ("vwap_mean_reversion", "XBRUSD"),
    ("gap_fade", "AUDUSD"),
    ("gap_fade", "EURUSD"),
    ("london_trend_breakout", "GBPUSD"),
    ("crude_london_breakout", "XTIUSD"),
}

DEFAULT_ROUND_TRIP_COSTS: dict[str, float] = {
    "EURUSD": 0.00012,
    "GBPUSD": 0.00018,
    "USDJPY": 0.018,
    "AUDUSD": 0.00018,
    "XAUUSD": 0.35,
    "BTCUSD": 16.0,
    "XTIUSD": 0.05,
    "XBRUSD": 0.05,
}


def _get_estimated_round_trip_cost(symbol: str, entry_price: float = 0.0) -> float:
    sym_clean = symbol.upper().replace("/", "")
    if sym_clean in DEFAULT_ROUND_TRIP_COSTS:
        return DEFAULT_ROUND_TRIP_COSTS[sym_clean]
    for k, v in DEFAULT_ROUND_TRIP_COSTS.items():
        if k in sym_clean:
            return v
    return max(1e-4, entry_price * 0.00015) if entry_price > 0 else 0.0002


async def evaluate_pretrade_gate(
    session,
    symbol: str,
    settings: dict,
    strategy_type: Optional[str] = None,
    as_of: Optional[datetime] = None,
    signal: Optional[Any] = None,
) -> tuple[bool, str]:
    """
    Evaluates institutional pre-trade gates:
    1. Microstructure: Session Rollover Deadzone Guard (21:55 - 22:15 UTC).
    2. Spread-Survival Floor & Toxic Strategy/Pair Elimination.
    3. Bollinger-Donchian Volatility Squeeze / Chop Gate.
    4. Volume Profile balance / imbalance regime alignment.
    5. ADX trend strength threshold.
    6. Microstructure Physics & Anti-Chase / Anti-Blowoff Filters.
    """
    settings = settings or {}

    # 1. Microstructure: Session Rollover Deadzone Guard (exempts 24/7 crypto)
    rollover_enabled = settings.get("trading", {}).get("risk", {}).get("rollover_protection_enabled", True)
    is_crypto = is_crypto_symbol(symbol)
    if rollover_enabled and not is_crypto:
        if as_of is not None:
            if as_of.tzinfo is None:
                now_utc = as_of.replace(tzinfo=timezone.utc)
            else:
                now_utc = as_of.astimezone(timezone.utc)
        else:
            now_utc = clock.now()
        cur_h = now_utc.hour
        cur_m = now_utc.minute
        if (cur_h == 21 and cur_m >= 55) or (cur_h == 22 and cur_m < 15):
            return False, "session_rollover_deadzone: high spread risk during 21:55-22:15 UTC interbank rollover"

    # 2. Spread-Survival Floor & Toxic Elimination (if signal object provided)
    if signal is not None:
        strat_id = getattr(signal, "strategy_id", "")
        if strat_id in TOXIC_STRATEGIES:
            return False, f"toxic_strategy_eliminated: {strat_id} has negative empirical expectancy"
        if (strat_id, symbol.upper()) in TOXIC_PAIRS:
            return False, f"toxic_pair_eliminated: {strat_id} on {symbol} has negative empirical edge"

        entry_p = getattr(signal, "entry_price", None)
        sl_p = getattr(signal, "stop_loss", None)
        if entry_p is not None and sl_p is not None:
            try:
                e_f = float(entry_p)
                sl_f = float(sl_p)
                sl_dist = abs(e_f - sl_f)
                if sl_dist <= 0:
                    return False, "invalid_sl_distance: stop loss equals or exceeds entry price"
                rt_cost = _get_estimated_round_trip_cost(symbol, e_f)
                if (rt_cost / sl_dist) > 0.20:
                    return (
                        False,
                        f"spread_survival_floor_breached: round-trip cost ({rt_cost:.5f}) exceeds 20% of stop distance ({sl_dist:.5f})",
                    )
            except ValueError, TypeError:
                pass

    # If strategy_type is not provided and no signal, rollover check is the universal gate
    if not strategy_type and not signal:
        return True, "ok"

    fam = strategy_type or getattr(signal, "factor_family", "")
    is_trend_like = fam in ("trend", "breakout", "tri_convergent")
    is_mr_like = fam in ("mean_reversion", "stat_arb")

    # 3. Volatility Chop Gate
    chop = await compute_bollinger_donchian_chop(session, symbol, "H4", settings, as_of=as_of)
    if chop.get("chop_block") and is_trend_like:
        return False, f"chop_block: {chop.get('reason')}"

    # 4. Volume Profile Regime Alignment
    vp_cfg = settings.get("trading", {}).get("edge_strategy", {}).get("volume_profile", {})
    vp_required = vp_cfg.get("required", False)
    vp = await compute_volume_profile(session, symbol, settings, as_of=as_of)
    if "error" in vp:
        if vp_required and (is_trend_like or is_mr_like):
            return False, f"volume_profile_unavailable: {vp['error']}"
    else:
        if vp.get("regime") == "imbalanced" and is_mr_like:
            return False, "imbalanced volume regime blocks mean-reversion / stat-arb"
        if vp.get("regime") == "balanced" and is_trend_like:
            return False, "balanced volume regime blocks pure trend-following / breakout"

    # 5. ADX Trend Confirmation (fail-closed if adx is unavailable for trend-following)
    regime = await classify_market_regime(session, symbol, settings, as_of=as_of)
    min_adx = settings.get("trading", {}).get("edge_strategy", {}).get("min_adx_for_trend", 20)
    if is_trend_like:
        adx_val = regime.get("adx")
        if adx_val is None:
            return False, "adx_unavailable: cannot confirm trend strength"
        if adx_val < min_adx:
            return False, f"ADX={adx_val:.1f} < {min_adx}"

    # 6. Microstructure Physics & Anti-Chase / Anti-Blowoff Filters
    try:
        from monika.infrastructure.database.models import PriceOHLCV

        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == "H1")
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(20)
        )
        if as_of:
            stmt = stmt.where(PriceOHLCV.timestamp <= as_of)
        exec_res = await session.execute(stmt)
        res_rows = []
        if hasattr(exec_res, "scalars"):
            sc = exec_res.scalars()
            if asyncio.iscoroutine(sc):
                sc = await sc
            raw_all = sc.all() if hasattr(sc, "all") else []
            if asyncio.iscoroutine(raw_all):
                raw_all = await raw_all
            if hasattr(raw_all, "__iter__") and not isinstance(raw_all, (dict, str, bytes)):
                try:
                    res_rows = list(raw_all)
                except Exception:
                    res_rows = []
        if res_rows and len(res_rows) >= 15:
            bars = sorted(res_rows, key=lambda r: r.timestamp)
            last_b = bars[-1]
            c = float(last_b.close)
            o = float(last_b.open)
            h = float(last_b.high)
            l = float(last_b.low)
            v = float(last_b.volume or 0.0)
            rng = max(h - l, 1e-9)

            trs = []
            for idx in range(1, len(bars)):
                cb = bars[idx]
                pb_c = float(bars[idx - 1].close)
                tr_val = max(
                    float(cb.high) - float(cb.low),
                    abs(float(cb.high) - pb_c),
                    abs(float(cb.low) - pb_c),
                )
                trs.append(tr_val)
            atr14 = max(sum(trs[-14:]) / max(1, len(trs[-14:])), 1e-9) if trs else rng

            vols = [float(b.volume or 0.0) for b in bars[-10:]]
            avg_vol10 = sum(vols) / max(1, len(vols))
            vol_ratio10 = (v / avg_vol10) if avg_vol10 > 0 else 1.0

            closes = [float(b.close) for b in bars]
            ema20 = sum(closes[-10:]) / 10.0

            dir_str = str(getattr(signal, "direction", "buy") or "buy").lower()
            is_buy = dir_str == "buy"
            dir_bias_ema20_atr = ((c - ema20) / atr14) if is_buy else ((ema20 - c) / atr14)
            close_conviction = ((c - l) / rng) if is_buy else ((h - c) / rng)

            strat_id = getattr(signal, "strategy_id", "")

            # Trend: Anti-Chase & Blow-off
            if is_trend_like:
                if strat_id in ("trend_trailing", "tsm_momentum"):
                    if (rng / atr14) > 2.10 or dir_bias_ema20_atr > 2.40:
                        return (
                            False,
                            f"anti_chase_blowoff: range={rng / atr14:.2f} ATR, bias={dir_bias_ema20_atr:.2f} ATR",
                        )
                elif fam == "trend":
                    if (rng / atr14) > 1.45 or vol_ratio10 > 1.60:
                        return False, f"anti_chase_exhaustion: range={rng / atr14:.2f} ATR, vol_ratio={vol_ratio10:.2f}"
                    if dir_bias_ema20_atr > 2.00:
                        return False, f"anti_chase_bias: price extended {dir_bias_ema20_atr:.2f} ATR from EMA20"

            # Breakout: Conviction & Noise Floor
            if fam == "breakout":
                min_sl_atr = 0.40 if "london_trend" in strat_id else 0.85
                entry_p = getattr(signal, "entry_price", None)
                sl_p = getattr(signal, "stop_loss", None)
                if entry_p and sl_p:
                    sl_dist = abs(float(entry_p) - float(sl_p))
                    if (sl_dist / atr14) < min_sl_atr:
                        return False, f"breakout_noise_floor: stop distance {sl_dist / atr14:.2f} < {min_sl_atr} ATR"
                if close_conviction < 0.38:
                    return False, f"breakout_conviction_failed: close_conviction={close_conviction:.2f} < 0.38"

            # Mean-Reversion: Anti-Marubozu & Blow-off
            if is_mr_like and "exhaustion" not in strat_id and "sweep" not in strat_id:
                if (rng / atr14) > 1.65:
                    return False, f"mean_reversion_marubozu_block: extreme range bar {rng / atr14:.2f} ATR"
                body_ratio = abs(c - o) / rng
                if vol_ratio10 > 1.65 and body_ratio > 0.75:
                    return False, f"mean_reversion_blowoff_block: vol_ratio={vol_ratio10:.2f}, body={body_ratio:.2f}"

            # Tri-Convergent: Participation Gate
            if fam == "tri_convergent" or strat_id == "tri_convergent_alpha":
                if vol_ratio10 < 0.62 or vol_ratio10 > 1.55:
                    return False, f"tri_convergent_volume_out_of_bounds: vol_ratio={vol_ratio10:.2f}"
                if dir_bias_ema20_atr > 2.00 or close_conviction > 0.82:
                    return False, "tri_convergent_exhaustion_block"
    except Exception as exc:
        logger.debug(f"[{symbol}] Microstructure physics check skipped: {exc}")

    return True, "ok"
