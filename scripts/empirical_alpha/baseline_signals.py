import numpy as np
from typing import Dict, Any
from scripts.empirical_alpha.evaluator import calculate_ema


def get_all_signal_generators(ev: Any) -> Dict[str, Any]:
    sigs = {}

    # 1. London Session Open Expansion
    def sig_london_expansion(i):
        if ev.hours[i] in (7, 8, 9):
            rec_h = np.max(ev.highs[max(0, i - 7) : i])
            rec_l = np.min(ev.lows[max(0, i - 7) : i])
            vol_ok = ev.volumes[i] >= 1.05 * ev.vol_ma20[i]
            if ev.closes[i] > rec_h and vol_ok:
                return "buy"
            elif ev.closes[i] < rec_l and vol_ok:
                return "sell"
        return None

    sigs["london_expansion"] = sig_london_expansion

    # 2. Asian Range Breakout
    def sig_asian_range_breakout(i):
        if ev.hours[i] in (7, 8):
            asia_h = np.max(ev.highs[max(0, i - 7) : i])
            asia_l = np.min(ev.lows[max(0, i - 7) : i])
            if ev.closes[i] > asia_h and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif ev.closes[i] < asia_l and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["asian_range_breakout"] = sig_asian_range_breakout

    # 3. NY Institutional Reversal
    def sig_ny_reversal(i):
        if ev.hours[i] in (13, 14, 15, 16):
            lh = np.max(ev.highs[max(0, i - 6) : i])
            ll = np.min(ev.lows[max(0, i - 6) : i])
            if ev.highs[i] >= lh and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 56:
                return "sell"
            elif ev.lows[i] <= ll and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 44:
                return "buy"
        return None

    sigs["ny_reversal"] = sig_ny_reversal

    # 4. Asian Session Range Fade
    def sig_asian_range_fade(i):
        if ev.hours[i] in (23, 0, 1, 2, 3, 4, 5):
            ah = np.max(ev.highs[max(0, i - 8) : i])
            al = np.min(ev.lows[max(0, i - 8) : i])
            if ev.highs[i] >= ah * 0.9995 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= al * 1.0005 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["asian_range_fade"] = sig_asian_range_fade

    # 5. Bollinger Band Mean Reversion
    def sig_bollinger_reversion(i):
        bw = (ev.bb_upper[i] - ev.bb_lower[i]) / max(1e-5, ev.bb_mid[i])
        if bw > 0.0025:
            if (
                ev.lows[i] <= ev.bb_lower[i]
                and ev.closes[i] > ev.bb_lower[i]
                and ev.rsi14[i] <= 42
                and ev.closes[i] > ev.opens[i]
            ):
                return "buy"
            elif (
                ev.highs[i] >= ev.bb_upper[i]
                and ev.closes[i] < ev.bb_upper[i]
                and ev.rsi14[i] >= 58
                and ev.closes[i] < ev.opens[i]
            ):
                return "sell"
        return None

    sigs["bollinger_reversion"] = sig_bollinger_reversion

    # 6. Fair Value Gap Mitigation
    def sig_fvg_mitigation(i):
        if i >= 3:
            bull_fvg = ev.lows[i - 1] > ev.highs[i - 3] and ev.closes[i - 2] > ev.opens[i - 2]
            bear_fvg = ev.highs[i - 1] < ev.lows[i - 3] and ev.closes[i - 2] < ev.opens[i - 2]
            if bull_fvg and ev.closes[i] > ev.ema50[i] and ev.lows[i] <= ev.lows[i - 1] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif (
                bear_fvg
                and ev.closes[i] < ev.ema50[i]
                and ev.highs[i] >= ev.highs[i - 1]
                and ev.closes[i] < ev.opens[i]
            ):
                return "sell"
        return None

    sigs["fvg_mitigation"] = sig_fvg_mitigation

    # 7. Donchian Channel Breakout
    def sig_donchian_breakout(i):
        vol_spike = ev.volumes[i] >= 1.15 * ev.vol_ma20[i]
        if vol_spike and ev.closes[i] > ev.donch_upper[i] and ev.closes[i] > ev.ema50[i]:
            return "buy"
        elif vol_spike and ev.closes[i] < ev.donch_lower[i] and ev.closes[i] < ev.ema50[i]:
            return "sell"
        return None

    sigs["donchian_breakout"] = sig_donchian_breakout

    # 8. HTF Liquidity Sweep & Displacement
    def sig_liquidity_sweep(i):
        atr = ev.atr14[i]
        body = abs(ev.closes[i] - ev.opens[i])
        if (
            ev.lows[i] < ev.swing_low48[i]
            and ev.closes[i] > ev.swing_low48[i]
            and ev.closes[i] > ev.opens[i]
            and body >= 0.5 * atr
        ):
            return "buy"
        elif (
            ev.highs[i] > ev.swing_high48[i]
            and ev.closes[i] < ev.swing_high48[i]
            and ev.closes[i] < ev.opens[i]
            and body >= 0.5 * atr
        ):
            return "sell"
        return None

    sigs["liquidity_sweep"] = sig_liquidity_sweep

    # 9. Carter Volatility Squeeze Breakout
    def sig_volatility_squeeze(i):
        if i >= 2:
            prev_sqz = ev.bb_upper[i - 1] <= ev.kelt_upper[i - 1] and ev.bb_lower[i - 1] >= ev.kelt_lower[i - 1]
            fire_long = ev.bb_upper[i] > ev.kelt_upper[i] and ev.closes[i] > ev.opens[i]
            fire_short = ev.bb_lower[i] < ev.kelt_lower[i] and ev.closes[i] < ev.opens[i]
            if prev_sqz and fire_long and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif prev_sqz and fire_short and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["volatility_squeeze"] = sig_volatility_squeeze

    # 10. Time Series Momentum (TSM)
    def sig_tsm_momentum(i):
        if i >= 48:
            roc12 = (ev.closes[i] - ev.closes[i - 12]) / ev.closes[i - 12]
            roc48 = (ev.closes[i] - ev.closes[i - 48]) / ev.closes[i - 48]
            thresh = (
                0.0025
                if "USD" in ev.symbol and not any(k in ev.symbol for k in ("BTC", "XAU", "XTI", "XBR"))
                else 0.007
            )
            if roc12 > thresh and roc48 > thresh and ev.closes[i] > ev.ema20[i]:
                return "buy"
            elif roc12 < -thresh and roc48 < -thresh and ev.closes[i] < ev.ema20[i]:
                return "sell"
        return None

    sigs["tsm_momentum"] = sig_tsm_momentum

    # 11. SMT & Oscillator Divergence
    def sig_smt_divergence(i):
        if i >= 15:
            price_lower = ev.lows[i] < ev.lows[i - 8]
            rsi_higher = ev.rsi14[i] > ev.rsi14[i - 8] + 2.0
            if price_lower and rsi_higher and ev.closes[i] > ev.opens[i]:
                return "buy"
            price_higher = ev.highs[i] > ev.highs[i - 8]
            rsi_lower = ev.rsi14[i] < ev.rsi14[i - 8] - 2.0
            if price_higher and rsi_lower and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["smt_divergence"] = sig_smt_divergence

    # 12. Gap Fill Reversion
    def sig_gap_fill_reversion(i):
        if i >= 2:
            gap = ev.opens[i] - ev.closes[i - 1]
            atr = ev.atr14[i]
            if gap <= -0.35 * atr and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif gap >= 0.35 * atr and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["gap_fill_reversion"] = sig_gap_fill_reversion

    # 13. 5-EMA Ribbon Expansion
    def sig_ema_ribbon_momentum(i):
        bull_rib = ev.ema8[i] > ev.ema13[i] > ev.ema21[i] > ev.ema34[i] > ev.ema55[i]
        bear_rib = ev.ema8[i] < ev.ema13[i] < ev.ema21[i] < ev.ema34[i] < ev.ema55[i]
        if bull_rib and ev.lows[i] <= ev.ema21[i] and ev.closes[i] > ev.ema13[i]:
            return "buy"
        elif bear_rib and ev.highs[i] >= ev.ema21[i] and ev.closes[i] < ev.ema13[i]:
            return "sell"
        return None

    sigs["ema_ribbon_momentum"] = sig_ema_ribbon_momentum

    # 14. Multi-Timeframe Structure Break
    def sig_multitimeframe_structure(i):
        h4_bull = ev.h4_ema50[i] > ev.h4_ema200[i]
        h4_bear = ev.h4_ema50[i] < ev.h4_ema200[i]
        rh = np.max(ev.highs[max(0, i - 5) : i])
        rl = np.min(ev.lows[max(0, i - 5) : i])
        if h4_bull and ev.closes[i] > rh and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif h4_bear and ev.closes[i] < rl and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["multitimeframe_structure"] = sig_multitimeframe_structure

    # 15. MACD Zero Cross & Trend
    def sig_macd_zero_cross(i):
        if i >= 2:
            cross_up = ev.macd_line[i - 1] <= 0 and ev.macd_line[i] > 0 and ev.macd_hist[i] > 0
            cross_down = ev.macd_line[i - 1] >= 0 and ev.macd_line[i] < 0 and ev.macd_hist[i] < 0
            if cross_up and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif cross_down and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["macd_zero_cross"] = sig_macd_zero_cross

    # 16. Stochastic Exhaustion Reversal
    def sig_stochastic_reversal(i):
        if i >= 2:
            stoch_bull = ev.stoch_k[i - 1] <= 22 and ev.stoch_k[i] > ev.stoch_d[i] and ev.stoch_k[i] > 20
            stoch_bear = ev.stoch_k[i - 1] >= 78 and ev.stoch_k[i] < ev.stoch_d[i] and ev.stoch_k[i] < 80
            if stoch_bull and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif stoch_bear and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["stochastic_reversal"] = sig_stochastic_reversal

    # 17. Inside Bar Volatility Breakout
    def sig_inside_bar_breakout(i):
        if i >= 2:
            is_inside = ev.highs[i - 1] <= ev.highs[i - 2] and ev.lows[i - 1] >= ev.lows[i - 2]
            break_up = ev.closes[i] > ev.highs[i - 1] and ev.closes[i] > ev.ema50[i]
            break_down = ev.closes[i] < ev.lows[i - 1] and ev.closes[i] < ev.ema50[i]
            if is_inside and break_up:
                return "buy"
            elif is_inside and break_down:
                return "sell"
        return None

    sigs["inside_bar_breakout"] = sig_inside_bar_breakout

    # 18. Pinbar / Long Wick Rejection
    def sig_pinbar_rejection(i):
        tot_range = ev.highs[i] - ev.lows[i]
        if tot_range > 1.0 * ev.atr14[i]:
            lower_wick = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
            upper_wick = ev.highs[i] - max(ev.opens[i], ev.closes[i])
            if lower_wick >= 0.55 * tot_range and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif upper_wick >= 0.55 * tot_range and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["pinbar_rejection"] = sig_pinbar_rejection

    # 19. Keltner Channel Boundary Bounce
    def sig_keltner_bounce(i):
        if (
            ev.lows[i] <= ev.kelt_lower[i]
            and ev.closes[i] > ev.kelt_lower[i]
            and ev.closes[i] > ev.opens[i]
            and ev.rsi14[i] <= 45
        ):
            return "buy"
        elif (
            ev.highs[i] >= ev.kelt_upper[i]
            and ev.closes[i] < ev.kelt_upper[i]
            and ev.closes[i] < ev.opens[i]
            and ev.rsi14[i] >= 55
        ):
            return "sell"
        return None

    sigs["keltner_bounce"] = sig_keltner_bounce

    # 20. Institutional Orderblock Mitigation
    def sig_orderblock_mitigation(i):
        if i >= 5:
            bull_ob = (
                ev.closes[i - 3] < ev.opens[i - 3]
                and ev.closes[i - 2] > ev.opens[i - 2]
                and ev.closes[i - 1] > ev.opens[i - 1]
            )
            ob_high = ev.highs[i - 3]
            ob_low = ev.lows[i - 3]
            if (
                bull_ob
                and ev.lows[i] <= ob_high
                and ev.closes[i] >= ob_low
                and ev.closes[i] > ev.opens[i]
                and ev.closes[i] > ev.ema50[i]
            ):
                return "buy"
            bear_ob = (
                ev.closes[i - 3] > ev.opens[i - 3]
                and ev.closes[i - 2] < ev.opens[i - 2]
                and ev.closes[i - 1] < ev.opens[i - 1]
            )
            if (
                bear_ob
                and ev.highs[i] >= ob_low
                and ev.closes[i] <= ob_high
                and ev.closes[i] < ev.opens[i]
                and ev.closes[i] < ev.ema50[i]
            ):
                return "sell"
        return None

    sigs["orderblock_mitigation"] = sig_orderblock_mitigation

    # 21. London Continuation Trend Pullback
    def sig_london_continuation(i):
        if ev.hours[i] in (10, 11, 12):
            if ev.ema20[i] > ev.ema50[i] and ev.lows[i] <= ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema20[i] < ev.ema50[i] and ev.highs[i] >= ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["london_continuation"] = sig_london_continuation

    # 22. NY Afternoon Trend Drift
    def sig_ny_drift(i):
        if ev.hours[i] in (16, 17, 18):
            if ev.closes[i] > ev.ema50[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 52:
                return "buy"
            elif ev.closes[i] < ev.ema50[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 48:
                return "sell"
        return None

    sigs["ny_drift"] = sig_ny_drift

    # 23. Engulfing Reversal Pattern
    def sig_engulfing_reversal(i):
        if i >= 2:
            prev_body = abs(ev.closes[i - 1] - ev.opens[i - 1])
            curr_body = abs(ev.closes[i] - ev.opens[i])
            if curr_body >= 1.2 * prev_body and curr_body >= 0.6 * ev.atr14[i]:
                if (
                    ev.closes[i - 1] < ev.opens[i - 1]
                    and ev.closes[i] > ev.opens[i]
                    and ev.closes[i] > ev.highs[i - 1]
                    and ev.rsi14[i] <= 48
                ):
                    return "buy"
                elif (
                    ev.closes[i - 1] > ev.opens[i - 1]
                    and ev.closes[i] < ev.opens[i]
                    and ev.closes[i] < ev.lows[i - 1]
                    and ev.rsi14[i] >= 52
                ):
                    return "sell"
        return None

    sigs["engulfing_reversal"] = sig_engulfing_reversal

    # 24. EMA Ribbon Trend Retest
    def sig_ema_trend_retest(i):
        bull = ev.ema20[i] > ev.ema50[i] > ev.ema200[i]
        bear = ev.ema20[i] < ev.ema50[i] < ev.ema200[i]
        if bull and ev.lows[i] <= ev.ema50[i] and ev.closes[i] > ev.ema20[i]:
            return "buy"
        elif bear and ev.highs[i] >= ev.ema50[i] and ev.closes[i] < ev.ema20[i]:
            return "sell"
        return None

    sigs["ema_trend_retest"] = sig_ema_trend_retest

    # 25. Tokyo Institutional Trend Expansion (00-02 UTC)
    def sig_tokyo_fix_expansion(i):
        if ev.hours[i] in (0, 1, 2):
            if ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.ema20[i] and ev.rsi14[i] >= 52:
                return "buy"
            elif ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.ema20[i] and ev.rsi14[i] <= 48:
                return "sell"
        return None

    sigs["tokyo_fix_expansion"] = sig_tokyo_fix_expansion

    # 26. RSI Extreme Reversal
    def sig_rsi_extreme_reversal(i):
        if ev.rsi14[i] <= 32 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.rsi14[i] >= 68 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["rsi_extreme_reversal"] = sig_rsi_extreme_reversal

    # 27. Frankfurt Pre-Open Range Break (06 UTC)
    def sig_frankfurt_pre_open(i):
        if ev.hours[i] == 6:
            ah = np.max(ev.highs[max(0, i - 6) : i])
            al = np.min(ev.lows[max(0, i - 6) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["frankfurt_pre_open"] = sig_frankfurt_pre_open

    # 28. 9/21 EMA Trend Cross
    def sig_ema9_21_cross(i):
        if i >= 2:
            cross_up = ev.ema9[i - 1] <= ev.ema21[i - 1] and ev.ema9[i] > ev.ema21[i]
            cross_down = ev.ema9[i - 1] >= ev.ema21[i - 1] and ev.ema9[i] < ev.ema21[i]
            if cross_up and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif cross_down and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["ema9_21_cross"] = sig_ema9_21_cross

    # 29. Triple EMA Trend Alignment Pullback (9/21/50)
    def sig_triple_ema_pullback(i):
        bull = ev.ema9[i] > ev.ema21[i] > ev.ema50[i]
        bear = ev.ema9[i] < ev.ema21[i] < ev.ema50[i]
        if bull and ev.lows[i] <= ev.ema21[i] and ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.ema21[i]:
            return "buy"
        elif bear and ev.highs[i] >= ev.ema21[i] and ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.ema21[i]:
            return "sell"
        return None

    sigs["triple_ema_pullback"] = sig_triple_ema_pullback

    # 30. London/NY Overlap Momentum Thrust (12-15 UTC)
    def sig_london_ny_overlap(i):
        if ev.hours[i] in (12, 13, 14, 15):
            body = abs(ev.closes[i] - ev.opens[i])
            vol_surge = ev.volumes[i] >= 1.25 * ev.vol_ma20[i]
            if vol_surge and body >= 0.7 * ev.atr14[i]:
                if ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.ema50[i]:
                    return "buy"
                elif ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.ema50[i]:
                    return "sell"
        return None

    sigs["london_ny_overlap"] = sig_london_ny_overlap

    # 31. VWAP Mean Reversion Stretch
    def sig_vwap_mean_reversion(i):
        dist = (ev.closes[i] - ev.vwap[i]) / ev.atr14[i]
        if dist <= -1.4 and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 38:
            return "buy"
        elif dist >= 1.4 and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 62:
            return "sell"
        return None

    sigs["vwap_mean_reversion"] = sig_vwap_mean_reversion

    # 32. Rolling 24h High/Low Rejection Fade
    def sig_session_hl_fade(i):
        if ev.lows[i] <= ev.swing_low24[i] and ev.closes[i] > ev.swing_low24[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.highs[i] >= ev.swing_high24[i] and ev.closes[i] < ev.swing_high24[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["session_hl_fade"] = sig_session_hl_fade

    # 33. Two-Bar Reversal (Railway Tracks)
    def sig_two_bar_reversal(i):
        if i >= 2:
            body_prev = abs(ev.closes[i - 1] - ev.opens[i - 1])
            body_curr = abs(ev.closes[i] - ev.opens[i])
            if body_prev >= 0.6 * ev.atr14[i] and body_curr >= 0.6 * ev.atr14[i]:
                if (
                    ev.closes[i - 1] < ev.opens[i - 1]
                    and ev.closes[i] > ev.opens[i]
                    and ev.closes[i] >= ev.opens[i - 1]
                ):
                    return "buy"
                elif (
                    ev.closes[i - 1] > ev.opens[i - 1]
                    and ev.closes[i] < ev.opens[i]
                    and ev.closes[i] <= ev.opens[i - 1]
                ):
                    return "sell"
        return None

    sigs["two_bar_reversal"] = sig_two_bar_reversal

    # 34. EMA 50 Dynamic Trend Bounce
    def sig_ema50_trend_bounce(i):
        if ev.closes[i] > ev.ema200[i]:
            if ev.lows[i] <= ev.ema50[i] and ev.closes[i] > ev.ema50[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        elif ev.closes[i] < ev.ema200[i]:
            if ev.highs[i] >= ev.ema50[i] and ev.closes[i] < ev.ema50[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ema50_trend_bounce"] = sig_ema50_trend_bounce

    # 35. Asian Morning Continuation (03-05 UTC)
    def sig_asian_continuation(i):
        if ev.hours[i] in (3, 4, 5):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 50:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 50:
                return "sell"
        return None

    sigs["asian_continuation"] = sig_asian_continuation

    # 36. Donchian Midpoint Pullback
    def sig_donchian_midpoint(i):
        mid = (ev.donch_upper[i] + ev.donch_lower[i]) / 2.0
        if ev.closes[i] > ev.ema50[i]:
            if ev.lows[i] <= mid and ev.closes[i] > mid and ev.closes[i] > ev.opens[i]:
                return "buy"
        elif ev.closes[i] < ev.ema50[i]:
            if ev.highs[i] >= mid and ev.closes[i] < mid and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["donchian_midpoint"] = sig_donchian_midpoint

    # 37. Volume Thrust & Momentum Follow-Through
    def sig_volume_thrust(i):
        vol_surge = ev.volumes[i] >= 1.4 * ev.vol_ma20[i]
        body = abs(ev.closes[i] - ev.opens[i])
        if vol_surge and body >= 0.8 * ev.atr14[i]:
            if ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.ema20[i]:
                return "buy"
            elif ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.ema20[i]:
                return "sell"
        return None

    sigs["volume_thrust"] = sig_volume_thrust

    # 38. RSI Trend Confirmation Pullback
    def sig_rsi_trend_pullback(i):
        if ev.closes[i] > ev.ema50[i]:
            if 40 <= ev.rsi14[i] <= 50 and ev.closes[i] > ev.opens[i]:
                return "buy"
        elif ev.closes[i] < ev.ema50[i]:
            if 50 <= ev.rsi14[i] <= 60 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["rsi_trend_pullback"] = sig_rsi_trend_pullback

    # 39. London Afternoon Range Fade (15-17 UTC)
    def sig_london_afternoon_fade(i):
        if ev.hours[i] in (15, 16, 17):
            lh = np.max(ev.highs[max(0, i - 8) : i])
            ll = np.min(ev.lows[max(0, i - 8) : i])
            if ev.highs[i] >= lh and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= ll and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["london_afternoon_fade"] = sig_london_afternoon_fade

    # 40. London Fix Reversal (15-16 UTC)
    def sig_london_fix_reversal(i):
        if ev.hours[i] in (15, 16):
            if ev.rsi14[i] >= 56 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi14[i] <= 44 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["london_fix_reversal"] = sig_london_fix_reversal

    # 41. Tokyo Afternoon Push (05-07 UTC)
    def sig_tokyo_afternoon_push(i):
        if ev.hours[i] in (5, 6, 7):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 50:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 50:
                return "sell"
        return None

    sigs["tokyo_afternoon_push"] = sig_tokyo_afternoon_push

    # 42. ADR Extreme Fade
    def sig_adr_extreme_fade(i):
        dist = (ev.closes[i] - ev.opens[max(0, i - 12)]) / ev.atr14[i]
        if dist >= 1.5 and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 60:
            return "sell"
        elif dist <= -1.5 and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 40:
            return "buy"
        return None

    sigs["adr_extreme_fade"] = sig_adr_extreme_fade

    # 43. EMA Ribbon Touch
    def sig_ema_ribbon_touch(i):
        if ev.ema20[i] > ev.ema50[i]:
            if ev.lows[i] <= ev.ema20[i] and ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        elif ev.ema20[i] < ev.ema50[i]:
            if ev.highs[i] >= ev.ema20[i] and ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ema_ribbon_touch"] = sig_ema_ribbon_touch

    # 44. Asia NY Sweep
    def sig_asia_ny_sweep(i):
        if ev.hours[i] in (13, 14, 15):
            ah = ev.swing_high24[i]
            al = ev.swing_low24[i]
            if ev.highs[i] >= ah and ev.closes[i] < ah and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= al and ev.closes[i] > al and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["asia_ny_sweep"] = sig_asia_ny_sweep

    # 45. EMA Stochastic Confluence
    def sig_ema_stoch_confluence(i):
        if (
            ev.closes[i] > ev.ema50[i]
            and ev.stoch_k[i] > ev.stoch_d[i]
            and ev.stoch_k[i] <= 45
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.closes[i] < ev.ema50[i]
            and ev.stoch_k[i] < ev.stoch_d[i]
            and ev.stoch_k[i] >= 55
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["ema_stoch_confluence"] = sig_ema_stoch_confluence

    # 46. AUD US Close Reversion (20-22 UTC)
    def sig_aud_us_close_reversion(i):
        if ev.hours[i] in (20, 21, 22):
            if ev.rsi14[i] <= 42 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.rsi14[i] >= 58 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["aud_us_close_reversion"] = sig_aud_us_close_reversion

    # 47. AUD London Breakout (07-08 UTC)
    def sig_aud_london_break(i):
        if ev.hours[i] in (7, 8):
            h8 = np.max(ev.highs[max(0, i - 8) : i])
            l8 = np.min(ev.lows[max(0, i - 8) : i])
            if ev.closes[i] > h8:
                return "buy"
            elif ev.closes[i] < l8:
                return "sell"
        return None

    sigs["aud_london_break"] = sig_aud_london_break

    # 48. Tokyo Range Fade (02-05 UTC)
    def sig_tokyo_range_fade(i):
        if ev.hours[i] in (2, 3, 4, 5):
            rh = np.max(ev.highs[max(0, i - 4) : i])
            rl = np.min(ev.lows[max(0, i - 4) : i])
            if ev.highs[i] >= rh and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 55:
                return "sell"
            elif ev.lows[i] <= rl and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 45:
                return "buy"
        return None

    sigs["tokyo_range_fade"] = sig_tokyo_range_fade

    # 49. ADX / DI Trend Crossover
    up_move = ev.highs[1:] - ev.highs[:-1]
    down_move = ev.lows[:-1] - ev.lows[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = np.insert(plus_dm, 0, 0.0)
    minus_dm = np.insert(minus_dm, 0, 0.0)
    atr = np.maximum(ev.atr14, 1e-6)
    plus_di = 100.0 * (calculate_ema(plus_dm, 14) / atr)
    minus_di = 100.0 * (calculate_ema(minus_dm, 14) / atr)

    def sig_adx_di_cross(i):
        if i >= 2:
            if plus_di[i - 1] <= minus_di[i - 1] and plus_di[i] > minus_di[i] and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif plus_di[i - 1] >= minus_di[i - 1] and plus_di[i] < minus_di[i] and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["adx_di_cross"] = sig_adx_di_cross

    # 50. SuperTrend ATR Trailing Band Cross
    st_upper = ev.ema20 + 2.0 * ev.atr14
    st_lower = ev.ema20 - 2.0 * ev.atr14

    def sig_supertrend_cross(i):
        if i >= 2:
            if ev.closes[i - 1] <= st_upper[i - 1] and ev.closes[i] > st_upper[i]:
                return "buy"
            elif ev.closes[i - 1] >= st_lower[i - 1] and ev.closes[i] < st_lower[i]:
                return "sell"
        return None

    sigs["supertrend_cross"] = sig_supertrend_cross

    # 51. Williams %R Exhaustion
    wr14 = np.zeros(ev.n)
    for j in range(14, ev.n):
        hh = np.max(ev.highs[j - 14 : j])
        ll = np.min(ev.lows[j - 14 : j])
        rng = hh - ll
        wr14[j] = ((hh - ev.closes[j]) / rng) * -100.0 if rng > 1e-7 else -50.0

    def sig_williams_r(i):
        if i >= 2:
            if wr14[i - 1] <= -80 and wr14[i] > -80 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif wr14[i - 1] >= -20 and wr14[i] < -20 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["williams_r"] = sig_williams_r

    # 52. ROC Momentum Burst (6 bars)
    roc6 = np.zeros(ev.n)
    roc6[6:] = (ev.closes[6:] - ev.closes[:-6]) / np.maximum(ev.closes[:-6], 1e-6)
    roc_thresh = (
        0.003 if "USD" in ev.symbol and not any(k in ev.symbol for k in ("BTC", "XAU", "XTI", "XBR")) else 0.008
    )

    def sig_roc_burst(i):
        if ev.volumes[i] >= 1.25 * ev.vol_ma20[i]:
            if roc6[i] >= roc_thresh and ev.closes[i] > ev.ema20[i]:
                return "buy"
            elif roc6[i] <= -roc_thresh and ev.closes[i] < ev.ema20[i]:
                return "sell"
        return None

    sigs["roc_burst"] = sig_roc_burst

    # 53. Consecutive 4-Bar Exhaustion
    def sig_consecutive_exhaustion(i):
        if i >= 4:
            four_down = all(ev.closes[k] < ev.opens[k] for k in range(i - 4, i))
            four_up = all(ev.closes[k] > ev.opens[k] for k in range(i - 4, i))
            if four_down and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 40:
                return "buy"
            elif four_up and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 60:
                return "sell"
        return None

    sigs["consecutive_exhaustion"] = sig_consecutive_exhaustion

    # 54. ATR Expansion Impulse Candle
    def sig_atr_impulse(i):
        c_range = ev.highs[i] - ev.lows[i]
        body = abs(ev.closes[i] - ev.opens[i])
        if c_range >= 1.4 * ev.atr14[i] and body >= 0.7 * c_range:
            if ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["atr_impulse"] = sig_atr_impulse

    # 55. Triple Screen Elder Confluence (H4 trend + H1 Stoch pullback)
    def sig_elder_triple_screen(i):
        h4_bull = ev.h4_ema50[i] > ev.h4_ema200[i]
        h4_bear = ev.h4_ema50[i] < ev.h4_ema200[i]
        if h4_bull and ev.stoch_k[i] <= 35 and ev.stoch_k[i] > ev.stoch_d[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif h4_bear and ev.stoch_k[i] >= 65 and ev.stoch_k[i] < ev.stoch_d[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["elder_triple_screen"] = sig_elder_triple_screen

    # 56. Asian Lunch Drift (04-06 UTC)
    def sig_asian_lunch_drift(i):
        if ev.hours[i] in (4, 5, 6):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 50:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 50:
                return "sell"
        return None

    sigs["asian_lunch_drift"] = sig_asian_lunch_drift

    # 57. NY Morning Breakout (13-15 UTC)
    def sig_ny_morning_breakout(i):
        if ev.hours[i] in (13, 14, 15):
            lh = np.max(ev.highs[max(0, i - 6) : i])
            ll = np.min(ev.lows[max(0, i - 6) : i])
            if ev.closes[i] > lh and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif ev.closes[i] < ll and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["ny_morning_breakout"] = sig_ny_morning_breakout

    # 58. Donchian Retest & Bounce
    def sig_donchian_retest(i):
        mid = (ev.donch_upper[i] + ev.donch_lower[i]) / 2.0
        if ev.closes[i] > ev.ema50[i] and ev.lows[i] <= mid and ev.closes[i] > mid and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.closes[i] < ev.ema50[i] and ev.highs[i] >= mid and ev.closes[i] < mid and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["donchian_retest"] = sig_donchian_retest

    # 59. Rejection Wick at 24h Extreme
    def sig_rejection_wick_extreme(i):
        tot = ev.highs[i] - ev.lows[i]
        if tot >= 1.0 * ev.atr14[i]:
            lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
            uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
            if lw >= 0.55 * tot and ev.lows[i] <= ev.swing_low24[i]:
                return "buy"
            elif uw >= 0.55 * tot and ev.highs[i] >= ev.swing_high24[i]:
                return "sell"
        return None

    sigs["rejection_wick_extreme"] = sig_rejection_wick_extreme

    # 60. Moving Average Convergence Divergence Pullback
    def sig_macd_pullback(i):
        if ev.macd_line[i] > 0 and ev.macd_hist[i - 1] <= 0 and ev.macd_hist[i] > 0 and ev.closes[i] > ev.ema20[i]:
            return "buy"
        elif ev.macd_line[i] < 0 and ev.macd_hist[i - 1] >= 0 and ev.macd_hist[i] < 0 and ev.closes[i] < ev.ema20[i]:
            return "sell"
        return None

    sigs["macd_pullback"] = sig_macd_pullback

    # 61. Tokyo Open Liquidity Sweep (00-02 UTC)
    def sig_tokyo_open_sweep(i):
        if ev.hours[i] in (0, 1, 2):
            rh = np.max(ev.highs[max(0, i - 12) : i])
            rl = np.min(ev.lows[max(0, i - 12) : i])
            if ev.highs[i] > rh and ev.closes[i] < rh and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] < rl and ev.closes[i] > rl and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["tokyo_open_sweep"] = sig_tokyo_open_sweep

    # 62. Frankfurt Momentum Continuation (06-07 UTC)
    def sig_frankfurt_continuation(i):
        if ev.hours[i] in (6, 7):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.volumes[i] >= 1.1 * ev.vol_ma20[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.volumes[i] >= 1.1 * ev.vol_ma20[i]:
                return "sell"
        return None

    sigs["frankfurt_continuation"] = sig_frankfurt_continuation

    # 63. London Lunch Mean Reversion (11-13 UTC)
    def sig_london_lunch_fade(i):
        if ev.hours[i] in (11, 12):
            if ev.rsi14[i] >= 64 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi14[i] <= 36 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["london_lunch_fade"] = sig_london_lunch_fade

    # 64. H4 Macro Trend H1 Pullback
    def sig_h4_trend_h1_pullback(i):
        bull_htf = ev.h4_ema50[i] > ev.h4_ema200[i]
        bear_htf = ev.h4_ema50[i] < ev.h4_ema200[i]
        if bull_htf and ev.lows[i] <= ev.ema20[i] and ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif bear_htf and ev.highs[i] >= ev.ema20[i] and ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["h4_trend_h1_pullback"] = sig_h4_trend_h1_pullback

    # 65. Asian Box Compression Breakout
    def sig_asian_box_compression(i):
        if ev.hours[i] in (7, 8):
            ah = np.max(ev.highs[max(0, i - 7) : i])
            al = np.min(ev.lows[max(0, i - 7) : i])
            rng = ah - al
            if rng <= 0.9 * ev.atr14[i]:
                if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["asian_box_compression"] = sig_asian_box_compression

    # 66. Turtle Soup 20-bar False Breakout Sweep
    def sig_turtle_soup_sweep(i):
        if i >= 22:
            prev_high = np.max(ev.highs[i - 20 : i - 1])
            prev_low = np.min(ev.lows[i - 20 : i - 1])
            if ev.highs[i] > prev_high and ev.closes[i] < prev_high and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] < prev_low and ev.closes[i] > prev_low and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["turtle_soup_sweep"] = sig_turtle_soup_sweep

    # 67. VWAP 2-StdDev Extreme Fade
    def sig_vwap_band_2std_fade(i):
        diff = (ev.closes[i] - ev.vwap[i]) / max(1e-5, ev.atr14[i])
        if diff >= 1.5 and ev.closes[i] < ev.opens[i]:
            return "sell"
        elif diff <= -1.5 and ev.closes[i] > ev.opens[i]:
            return "buy"
        return None

    sigs["vwap_band_2std_fade"] = sig_vwap_band_2std_fade

    # 68. Double Inside Bar Breakout
    def sig_double_inside_bar(i):
        if i >= 3:
            ib1 = ev.highs[i - 1] <= ev.highs[i - 2] and ev.lows[i - 1] >= ev.lows[i - 2]
            ib2 = ev.highs[i - 2] <= ev.highs[i - 3] and ev.lows[i - 2] >= ev.lows[i - 3]
            if ib1 and ib2:
                if ev.closes[i] > ev.highs[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i] < ev.lows[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["double_inside_bar"] = sig_double_inside_bar

    # 69. Three Candle Institutional Momentum Thrust
    def sig_three_candle_thrust(i):
        if i >= 3:
            c1_bull = ev.closes[i - 2] > ev.opens[i - 2]
            c2_bull = ev.closes[i - 1] > ev.opens[i - 1]
            c3_bull = ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.closes[i - 1]
            if c1_bull and c2_bull and c3_bull and ev.closes[i] > ev.ema50[i]:
                return "buy"
            c1_bear = ev.closes[i - 2] < ev.opens[i - 2]
            c2_bear = ev.closes[i - 1] < ev.opens[i - 1]
            c3_bear = ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.closes[i - 1]
            if c1_bear and c2_bear and c3_bear and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["three_candle_thrust"] = sig_three_candle_thrust

    # 70. Supertrend ATR Trail Bounce
    def sig_supertrend_bounce(i):
        if ev.closes[i] > ev.ema50[i] and ev.lows[i] <= ev.ema50[i] + 0.35 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif (
            ev.closes[i] < ev.ema50[i]
            and ev.highs[i] >= ev.ema50[i] - 0.35 * ev.atr14[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["supertrend_bounce"] = sig_supertrend_bounce

    # 71. ADR Exhaustion Reversal
    def sig_adr_exhaustion_reversal(i):
        if i >= 24:
            d_high = np.max(ev.highs[i - 24 : i])
            d_low = np.min(ev.lows[i - 24 : i])
            rng = d_high - d_low
            if rng >= 1.1 * ev.atr14[i]:
                if ev.highs[i] >= d_high and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 60:
                    return "sell"
                elif ev.lows[i] <= d_low and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 40:
                    return "buy"
        return None

    sigs["adr_exhaustion_reversal"] = sig_adr_exhaustion_reversal

    # 72. FVG Discount / Premium Retest
    def sig_fvg_discount_retest(i):
        if i >= 4:
            bull_fvg = ev.lows[i - 1] > ev.highs[i - 3]
            bear_fvg = ev.highs[i - 1] < ev.lows[i - 3]
            if (
                bull_fvg
                and ev.lows[i] <= (ev.lows[i - 1] + ev.highs[i - 3]) / 2.0
                and ev.closes[i] > ev.opens[i]
                and ev.closes[i] > ev.ema50[i]
            ):
                return "buy"
            elif (
                bear_fvg
                and ev.highs[i] >= (ev.highs[i - 1] + ev.lows[i - 3]) / 2.0
                and ev.closes[i] < ev.opens[i]
                and ev.closes[i] < ev.ema50[i]
            ):
                return "sell"
        return None

    sigs["fvg_discount_retest"] = sig_fvg_discount_retest

    # 73. London / NY Transition (15-17 UTC)
    def sig_london_ny_transition(i):
        if ev.hours[i] in (15, 16):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 52:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 48:
                return "sell"
        return None

    sigs["london_ny_transition"] = sig_london_ny_transition

    # 74. AUD Asia Tokyo Drift (02-05 UTC)
    def sig_aud_asia_tokyo_drift(i):
        if ev.hours[i] in (2, 3, 4):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.volumes[i] >= 1.05 * ev.vol_ma20[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.volumes[i] >= 1.05 * ev.vol_ma20[i]:
                return "sell"
        return None

    sigs["aud_asia_tokyo_drift"] = sig_aud_asia_tokyo_drift

    # 75. GBP Cable London Open Breakout (08-09 UTC)
    def sig_gbp_cable_breakout(i):
        if ev.hours[i] in (8, 9):
            pre_h = np.max(ev.highs[max(0, i - 6) : i])
            pre_l = np.min(ev.lows[max(0, i - 6) : i])
            if ev.closes[i] > pre_h and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < pre_l and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["gbp_cable_breakout"] = sig_gbp_cable_breakout

    # 76. EMA Retest with MACD Confluence
    def sig_ema_retest_macd(i):
        if (
            ev.closes[i] > ev.ema50[i]
            and ev.lows[i] <= ev.ema21[i]
            and ev.closes[i] > ev.ema21[i]
            and ev.macd_hist[i] > 0
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.closes[i] < ev.ema50[i]
            and ev.highs[i] >= ev.ema21[i]
            and ev.closes[i] < ev.ema21[i]
            and ev.macd_hist[i] < 0
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["ema_retest_macd"] = sig_ema_retest_macd

    # 77. Two-Bar Momentum Thrust
    def sig_two_bar_thrust(i):
        if i >= 2:
            body1 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            body2 = abs(ev.closes[i] - ev.opens[i])
            if body1 >= 0.5 * ev.atr14[i] and body2 >= 0.5 * ev.atr14[i]:
                if ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.highs[i - 1]:
                    return "buy"
                elif (
                    ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.lows[i - 1]
                ):
                    return "sell"
        return None

    sigs["two_bar_thrust"] = sig_two_bar_thrust

    # 78. StochRSI Pullback in Trend
    def sig_stoch_trend_pullback(i):
        if (
            ev.closes[i] > ev.ema50[i]
            and ev.stoch_k[i - 1] <= 32
            and ev.stoch_k[i] > ev.stoch_d[i]
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.closes[i] < ev.ema50[i]
            and ev.stoch_k[i - 1] >= 68
            and ev.stoch_k[i] < ev.stoch_d[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["stoch_trend_pullback"] = sig_stoch_trend_pullback

    # 79. Asian Range Mean Revert Multibar
    def sig_asian_range_mean_revert(i):
        if ev.hours[i] in (23, 0, 1, 2, 3):
            if ev.closes[i] > ev.bb_upper[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.closes[i] < ev.bb_lower[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["asian_range_mean_revert"] = sig_asian_range_mean_revert

    # 80. Sydney Session Opening Breakout
    def sig_aud_sydney_breakout(i):
        if ev.hours[i] in (21, 22, 23):
            prev_h = np.max(ev.highs[max(0, i - 4) : i])
            prev_l = np.min(ev.lows[max(0, i - 4) : i])
            if ev.closes[i] > prev_h and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < prev_l and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["aud_sydney_breakout"] = sig_aud_sydney_breakout

    # 81. MACD Zero Line Bounce
    def sig_macd_zero_bounce(i):
        if ev.macd_line[i] > 0 and abs(ev.macd_line[i]) < 0.0008 and ev.macd_hist[i] > 0 and ev.closes[i] > ev.ema20[i]:
            return "buy"
        elif (
            ev.macd_line[i] < 0 and abs(ev.macd_line[i]) < 0.0008 and ev.macd_hist[i] < 0 and ev.closes[i] < ev.ema20[i]
        ):
            return "sell"
        return None

    sigs["macd_zero_bounce"] = sig_macd_zero_bounce

    # 82. 12-bar Donchian Tight Breakout
    def sig_donchian12_breakout(i):
        if i >= 12:
            dh = np.max(ev.highs[i - 12 : i])
            dl = np.min(ev.lows[i - 12 : i])
            if ev.closes[i] > dh and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif ev.closes[i] < dl and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["donchian12_breakout"] = sig_donchian12_breakout

    # 83. RSI Trend Zone Pullback
    def sig_rsi_trend_zone_pullback(i):
        if ev.closes[i] > ev.ema50[i] and 40 <= ev.rsi14[i] <= 48 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.closes[i] < ev.ema50[i] and 52 <= ev.rsi14[i] <= 60 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["rsi_trend_zone_pullback"] = sig_rsi_trend_zone_pullback

    # 84. EMA 9/21 Pullback Continuation
    def sig_ema9_21_pullback(i):
        if (
            ev.ema9[i] > ev.ema21[i]
            and ev.lows[i] <= ev.ema9[i]
            and ev.closes[i] > ev.ema9[i]
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.ema9[i] < ev.ema21[i]
            and ev.highs[i] >= ev.ema9[i]
            and ev.closes[i] < ev.ema9[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["ema9_21_pullback"] = sig_ema9_21_pullback

    return sigs
