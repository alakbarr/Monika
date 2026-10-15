import numpy as np
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR))


from scripts.empirical_alpha.baseline_signals import get_all_signal_generators


def get_ultra_signal_universe(ev):
    # Get baseline 84 signals
    sigs = get_all_signal_generators(ev)

    # Helper lambdas for session checks
    is_asian = lambda i: ev.hours[i] in (22, 23, 0, 1, 2, 3, 4, 5)
    is_tokyo_open = lambda i: ev.hours[i] in (0, 1, 2)
    is_tokyo_fix = lambda i: ev.hours[i] in (1, 2, 3)
    is_tokyo_lunch = lambda i: ev.hours[i] in (3, 4, 5)
    is_frankfurt = lambda i: ev.hours[i] in (6, 7)
    is_london_open = lambda i: ev.hours[i] in (7, 8)
    is_london_morning = lambda i: ev.hours[i] in (8, 9, 10)
    is_london_lunch = lambda i: ev.hours[i] in (11, 12)
    is_overlap = lambda i: ev.hours[i] in (13, 14, 15, 16)
    is_ny_open = lambda i: ev.hours[i] in (13, 14, 15)
    is_london_fix = lambda i: ev.hours[i] in (15, 16)
    is_europe_close = lambda i: ev.hours[i] in (16, 17)
    is_ny_afternoon = lambda i: ev.hours[i] in (17, 18, 19)
    is_us_close = lambda i: ev.hours[i] in (20, 21)
    is_sydney = lambda i: ev.hours[i] in (22, 23, 0, 1)

    # 1. Bollinger 2.0 Band Mean Reversion
    def s_bb20_revert(i):
        if ev.lows[i] <= ev.bb_lower[i] and ev.closes[i] > ev.bb_lower[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.highs[i] >= ev.bb_upper[i] and ev.closes[i] < ev.bb_upper[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_bb20_revert"] = s_bb20_revert

    # 2. Bollinger 2.5 Band Extreme Fade
    def s_bb25_fade(i):
        if ev.lows[i] <= ev.bb25_low[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.highs[i] >= ev.bb25_up[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_bb25_fade"] = s_bb25_fade

    # 3. Bollinger 1.5 Band Asian Fade
    def s_bb15_asian_fade(i):
        if is_asian(i):
            if ev.closes[i] <= ev.bb15_low[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] >= ev.bb15_up[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_bb15_asian_fade"] = s_bb15_asian_fade

    # 4. Bollinger 1.5 Band London Lunch Fade
    def s_bb15_london_lunch_fade(i):
        if is_london_lunch(i):
            if ev.closes[i] <= ev.bb15_low[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] >= ev.bb15_up[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_bb15_london_lunch_fade"] = s_bb15_london_lunch_fade

    # 5. Bollinger 1.5 Band NY Afternoon Fade
    def s_bb15_ny_afternoon_fade(i):
        if is_ny_afternoon(i):
            if ev.closes[i] <= ev.bb15_low[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] >= ev.bb15_up[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_bb15_ny_afternoon_fade"] = s_bb15_ny_afternoon_fade

    # 6. Keltner Channel Lower/Upper Fade
    def s_keltner_fade(i):
        if ev.lows[i] <= ev.kelt_lower[i] and ev.closes[i] > ev.kelt_lower[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.highs[i] >= ev.kelt_upper[i] and ev.closes[i] < ev.kelt_upper[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_keltner_fade"] = s_keltner_fade

    # 7. VWAP Deviation 1.0 Fade in Asian Session
    def s_vwap_dev10_asian(i):
        if is_asian(i):
            dev = ev.closes[i] - ev.vwap[i]
            if dev <= -0.9 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif dev >= 0.9 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_vwap_dev10_asian"] = s_vwap_dev10_asian

    # 8. VWAP Deviation 1.2 Fade in London Lunch
    def s_vwap_dev12_london_lunch(i):
        if is_london_lunch(i):
            dev = ev.closes[i] - ev.vwap[i]
            if dev <= -1.0 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif dev >= 1.0 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_vwap_dev12_london_lunch"] = s_vwap_dev12_london_lunch

    # 9. VWAP Deviation 1.2 Fade in NY Afternoon
    def s_vwap_dev12_ny_afternoon(i):
        if is_ny_afternoon(i):
            dev = ev.closes[i] - ev.vwap[i]
            if dev <= -1.0 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif dev >= 1.0 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_vwap_dev12_ny_afternoon"] = s_vwap_dev12_ny_afternoon

    # 10. RSI 14 Extreme (<=32 / >=68)
    def s_rsi14_extreme(i):
        if ev.rsi14[i] <= 32 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.rsi14[i] >= 68 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_rsi14_extreme"] = s_rsi14_extreme

    # 11. RSI 7 Fast Cycle Extreme (<=20 / >=80)
    def s_rsi7_extreme(i):
        if ev.rsi7[i] <= 20 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.rsi7[i] >= 80 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_rsi7_extreme"] = s_rsi7_extreme

    # 12. RSI 7 Asian Session Dip (<=25 / >=75)
    def s_rsi7_asian_dip(i):
        if is_asian(i):
            if ev.rsi7[i] <= 25 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.rsi7[i] >= 75 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_rsi7_asian_dip"] = s_rsi7_asian_dip

    # 13. RSI 7 London Lunch Fade
    def s_rsi7_london_lunch(i):
        if is_london_lunch(i):
            if ev.rsi7[i] <= 25 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.rsi7[i] >= 75 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_rsi7_london_lunch"] = s_rsi7_london_lunch

    # 14. RSI 7 NY Afternoon Fade
    def s_rsi7_ny_afternoon(i):
        if is_ny_afternoon(i):
            if ev.rsi7[i] <= 25 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.rsi7[i] >= 75 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_rsi7_ny_afternoon"] = s_rsi7_ny_afternoon

    # 15. Stochastic 14,3,3 Extreme Cross (<=22 / >=78)
    def s_stoch14_extreme_cross(i):
        if ev.stoch_k[i - 1] <= 22 and ev.stoch_k[i] > ev.stoch_d[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.stoch_k[i - 1] >= 78 and ev.stoch_k[i] < ev.stoch_d[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_stoch14_extreme_cross"] = s_stoch14_extreme_cross

    # 16. Fast Stochastic 8,3,3 Oversold Cross
    def s_stoch8_extreme_cross(i):
        if ev.stoch8_k[i - 1] <= 18 and ev.stoch8_k[i] > ev.stoch8_d[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.stoch8_k[i - 1] >= 82 and ev.stoch8_k[i] < ev.stoch8_d[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_stoch8_extreme_cross"] = s_stoch8_extreme_cross

    # 17. Slow Stochastic 21,5,5 Extreme Cross
    def s_stoch21_extreme_cross(i):
        if ev.stoch21_k[i - 1] <= 25 and ev.stoch21_k[i] > ev.stoch21_d[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.stoch21_k[i - 1] >= 75 and ev.stoch21_k[i] < ev.stoch21_d[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_stoch21_extreme_cross"] = s_stoch21_extreme_cross

    # 18. Consecutive 3-Bar Exhaustion Fade
    def s_consecutive3_fade(i):
        if i >= 3:
            tot = ev.closes[i] - ev.opens[i - 2]
            if tot <= -1.3 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif tot >= 1.3 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_consecutive3_fade"] = s_consecutive3_fade

    # 19. Consecutive 4-Bar Exhaustion Fade
    def s_consecutive4_fade(i):
        if i >= 4:
            tot = ev.closes[i] - ev.opens[i - 3]
            if tot <= -1.6 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif tot >= 1.6 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_consecutive4_fade"] = s_consecutive4_fade

    # 20. 12-Hour Swing Sweep and Re-entry
    def s_swing12_sweep_reenter(i):
        h12 = ev.swing_high12[i]
        l12 = ev.swing_low12[i]
        if ev.highs[i] >= h12 and ev.closes[i] < h12 and ev.closes[i] < ev.opens[i]:
            return "sell"
        elif ev.lows[i] <= l12 and ev.closes[i] > l12 and ev.closes[i] > ev.opens[i]:
            return "buy"
        return None

    sigs["s_swing12_sweep_reenter"] = s_swing12_sweep_reenter

    # 21. 24-Hour Swing Sweep and Re-entry
    def s_swing24_sweep_reenter(i):
        h24 = ev.swing_high24[i]
        l24 = ev.swing_low24[i]
        if ev.highs[i] >= h24 and ev.closes[i] < h24 and ev.closes[i] < ev.opens[i]:
            return "sell"
        elif ev.lows[i] <= l24 and ev.closes[i] > l24 and ev.closes[i] > ev.opens[i]:
            return "buy"
        return None

    sigs["s_swing24_sweep_reenter"] = s_swing24_sweep_reenter

    # 22. 48-Hour Swing Sweep and Re-entry
    def s_swing48_sweep_reenter(i):
        h48 = ev.swing_high48[i]
        l48 = ev.swing_low48[i]
        if ev.highs[i] >= h48 and ev.closes[i] < h48 and ev.closes[i] < ev.opens[i]:
            return "sell"
        elif ev.lows[i] <= l48 and ev.closes[i] > l48 and ev.closes[i] > ev.opens[i]:
            return "buy"
        return None

    sigs["s_swing48_sweep_reenter"] = s_swing48_sweep_reenter

    # 23. Pinbar at 24h Extreme
    def s_pinbar_swing24(i):
        rng = max(1e-7, ev.highs[i] - ev.lows[i])
        if rng >= 0.65 * ev.atr14[i]:
            lower_w = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
            upper_w = ev.highs[i] - max(ev.opens[i], ev.closes[i])
            if lower_w / rng >= 0.50 and ev.lows[i] <= ev.swing_low24[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif upper_w / rng >= 0.50 and ev.highs[i] >= ev.swing_high24[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_pinbar_swing24"] = s_pinbar_swing24

    # 24. Two-Bar Reversal Pattern
    def s_two_bar_reversal(i):
        if i >= 1:
            body = abs(ev.closes[i] - ev.opens[i])
            prev_b = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if body >= 0.55 * ev.atr14[i] and prev_b >= 0.55 * ev.atr14[i]:
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

    sigs["s_two_bar_reversal"] = s_two_bar_reversal

    # 25. Inside Bar False Breakout (Spring / Upthrust)
    def s_inside_bar_fakeout(i):
        if i >= 2:
            if ev.highs[i - 1] <= ev.highs[i - 2] and ev.lows[i - 1] >= ev.lows[i - 2]:
                if ev.lows[i] < ev.lows[i - 2] and ev.closes[i] > ev.lows[i - 2] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.highs[i] > ev.highs[i - 2] and ev.closes[i] < ev.highs[i - 2] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["s_inside_bar_fakeout"] = s_inside_bar_fakeout

    # 26. Morning / Evening Star Reversal
    def s_star_reversal(i):
        if i >= 2:
            b1 = abs(ev.closes[i - 2] - ev.opens[i - 2])
            b2 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            b3 = abs(ev.closes[i] - ev.opens[i])
            if b1 >= 0.55 * ev.atr14[i] and b2 <= 0.45 * b1 and b3 >= 0.45 * b1:
                if ev.closes[i - 2] < ev.opens[i - 2] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 2] > ev.opens[i - 2] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["s_star_reversal"] = s_star_reversal

    # 27. Harami Pattern Reversal
    def s_harami_reversal(i):
        if i >= 1:
            if ev.highs[i] < ev.highs[i - 1] and ev.lows[i] > ev.lows[i - 1]:
                if ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["s_harami_reversal"] = s_harami_reversal

    # 28. Tokyo Open Liquidity Sweep (00:00 - 02:00)
    def s_tokyo_open_sweep(i):
        if is_tokyo_open(i):
            h12 = ev.swing_high12[i]
            l12 = ev.swing_low12[i]
            if ev.highs[i] >= h12 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l12 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_tokyo_open_sweep"] = s_tokyo_open_sweep

    # 29. Tokyo Fix Mean Reversion (01:00 - 03:00)
    def s_tokyo_fix_fade(i):
        if is_tokyo_fix(i):
            h8 = ev.swing_high8[i]
            l8 = ev.swing_low8[i]
            if ev.highs[i] >= h8 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l8 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_tokyo_fix_fade"] = s_tokyo_fix_fade

    # 30. Tokyo Lunch Mean Revert (03:00 - 05:00)
    def s_tokyo_lunch_revert(i):
        if is_tokyo_lunch(i):
            if ev.closes[i] >= ev.bb15_up[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.closes[i] <= ev.bb15_low[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_tokyo_lunch_revert"] = s_tokyo_lunch_revert

    # 31. Frankfurt Pre-Open Range Break (06:00 - 07:00)
    def s_frankfurt_range_break(i):
        if is_frankfurt(i):
            ah = np.max(ev.highs[max(0, i - 6) : i])
            al = np.min(ev.lows[max(0, i - 6) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_frankfurt_range_break"] = s_frankfurt_range_break

    # 32. London Open Volume Breakout (07:00 - 09:00)
    def s_london_open_break(i):
        if is_london_open(i):
            ah = np.max(ev.highs[max(0, i - 7) : i])
            al = np.min(ev.lows[max(0, i - 7) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_london_open_break"] = s_london_open_break

    # 33. London Morning Drive (08:00 - 11:00)
    def s_london_morning_drive(i):
        if is_london_morning(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_london_morning_drive"] = s_london_morning_drive

    # 34. London Lunch Fade (11:00 - 13:00)
    def s_london_lunch_fade(i):
        if is_london_lunch(i):
            if ev.rsi7[i] >= 68 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi7[i] <= 32 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_london_lunch_fade"] = s_london_lunch_fade

    # 35. Overlap Momentum Surge (13:00 - 16:00)
    def s_overlap_surge(i):
        if is_overlap(i):
            if ev.ema9[i] > ev.ema21[i] and ev.closes[i] > ev.ema9[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema9[i] < ev.ema21[i] and ev.closes[i] < ev.ema9[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_overlap_surge"] = s_overlap_surge

    # 36. NY Morning Reversal (13:00 - 15:30)
    def s_ny_morning_reversal(i):
        if is_ny_open(i):
            lh = np.max(ev.highs[max(0, i - 5) : i])
            ll = np.min(ev.lows[max(0, i - 5) : i])
            if ev.highs[i] >= lh and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= ll and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_ny_morning_reversal"] = s_ny_morning_reversal

    # 37. European Close Profit Fade (15:00 - 17:00)
    def s_europe_close_fade(i):
        if is_europe_close(i):
            if ev.rsi14[i] >= 64 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi14[i] <= 36 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_europe_close_fade"] = s_europe_close_fade

    # 38. NY Afternoon Continuation (17:00 - 20:00)
    def s_ny_afternoon_continue(i):
        if is_ny_afternoon(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_ny_afternoon_continue"] = s_ny_afternoon_continue

    # 39. US Close Range Fade (20:00 - 22:00)
    def s_us_close_range_fade(i):
        if is_us_close(i):
            if ev.closes[i] >= ev.bb_upper[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.closes[i] <= ev.bb_lower[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["s_us_close_range_fade"] = s_us_close_range_fade

    # 40. Sydney Open Pulse (22:00 - 02:00)
    def s_sydney_pulse(i):
        if is_sydney(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_sydney_pulse"] = s_sydney_pulse

    # 41. EMA 9/21 Pullback
    def s_ema9_21_pullback(i):
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

    sigs["s_ema9_21_pullback"] = s_ema9_21_pullback

    # 42. EMA 20 Retest
    def s_ema20_retest(i):
        if (
            ev.closes[i] > ev.ema50[i]
            and ev.lows[i] <= ev.ema20[i]
            and ev.closes[i] > ev.ema20[i]
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.closes[i] < ev.ema50[i]
            and ev.highs[i] >= ev.ema20[i]
            and ev.closes[i] < ev.ema20[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["s_ema20_retest"] = s_ema20_retest

    # 43. EMA 50 Bounce
    def s_ema50_bounce(i):
        if (
            ev.closes[i] > ev.ema100[i]
            and ev.lows[i] <= ev.ema50[i]
            and ev.closes[i] > ev.ema50[i]
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.closes[i] < ev.ema100[i]
            and ev.highs[i] >= ev.ema50[i]
            and ev.closes[i] < ev.ema50[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["s_ema50_bounce"] = s_ema50_bounce

    # 44. RSI 14 Trend Zone Pullback (38-48 buy / 52-62 sell)
    def s_rsi14_trend_pullback(i):
        if ev.closes[i] > ev.ema50[i] and 38 <= ev.rsi14[i] <= 48 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.closes[i] < ev.ema50[i] and 52 <= ev.rsi14[i] <= 62 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_rsi14_trend_pullback"] = s_rsi14_trend_pullback

    # 45. RSI 7 Trend Dip (<=28 buy / >=72 sell)
    def s_rsi7_trend_dip(i):
        if ev.closes[i] > ev.ema50[i] and ev.rsi7[i] <= 28 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.closes[i] < ev.ema50[i] and ev.rsi7[i] >= 72 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_rsi7_trend_dip"] = s_rsi7_trend_dip

    # 46. Stochastic Trend Cross
    def s_stoch_trend_cross(i):
        if (
            ev.closes[i] > ev.ema50[i]
            and ev.stoch_k[i - 1] <= 28
            and ev.stoch_k[i] > ev.stoch_d[i]
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.closes[i] < ev.ema50[i]
            and ev.stoch_k[i - 1] >= 72
            and ev.stoch_k[i] < ev.stoch_d[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["s_stoch_trend_cross"] = s_stoch_trend_cross

    # 47. MACD Histogram Acceleration in Trend
    def s_macd_hist_accel(i):
        if i >= 2:
            if ev.macd_hist[i] > ev.macd_hist[i - 1] > ev.macd_hist[i - 2] > 0 and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif ev.macd_hist[i] < ev.macd_hist[i - 1] < ev.macd_hist[i - 2] < 0 and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["s_macd_hist_accel"] = s_macd_hist_accel

    # 48. Donchian 12 Breakout
    def s_donchian12_break(i):
        if ev.closes[i] > ev.donch12_high[i] and ev.closes[i] > ev.ema50[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.closes[i] < ev.donch12_low[i] and ev.closes[i] < ev.ema50[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_donchian12_break"] = s_donchian12_break

    # 49. Donchian 20 Breakout
    def s_donchian20_break(i):
        if ev.closes[i] > ev.donch20_high[i] and ev.closes[i] > ev.ema50[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.closes[i] < ev.donch20_low[i] and ev.closes[i] < ev.ema50[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["s_donchian20_break"] = s_donchian20_break

    # 50. Three Bar Momentum Thrust
    def s_three_bar_thrust(i):
        if i >= 3:
            if (
                ev.closes[i] > ev.opens[i]
                and ev.closes[i - 1] > ev.opens[i - 1]
                and ev.closes[i - 2] > ev.opens[i - 2]
                and ev.closes[i] > ev.ema50[i]
            ):
                return "buy"
            elif (
                ev.closes[i] < ev.opens[i]
                and ev.closes[i - 1] < ev.opens[i - 1]
                and ev.closes[i - 2] < ev.opens[i - 2]
                and ev.closes[i] < ev.ema50[i]
            ):
                return "sell"
        return None

    sigs["s_three_bar_thrust"] = s_three_bar_thrust

    # 51. EMA Cloud Bounce (13/34)
    def s_ema_cloud_bounce(i):
        if (
            ev.ema13[i] > ev.ema34[i]
            and ev.lows[i] <= ev.ema13[i]
            and ev.closes[i] > ev.ema13[i]
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.ema13[i] < ev.ema34[i]
            and ev.highs[i] >= ev.ema13[i]
            and ev.closes[i] < ev.ema13[i]
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["s_ema_cloud_bounce"] = s_ema_cloud_bounce

    # 52. FVG Imbalance Retest in Trend
    def s_fvg_trend_retest(i):
        if i >= 3:
            if ev.lows[i - 1] > ev.highs[i - 3] and ev.closes[i] > ev.ema50[i]:
                if ev.lows[i] <= ev.lows[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
            elif ev.highs[i - 1] < ev.lows[i - 3] and ev.closes[i] < ev.ema50[i]:
                if ev.highs[i] >= ev.highs[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["s_fvg_trend_retest"] = s_fvg_trend_retest

    # 53. Institutional Order Block Retest
    def s_orderblock_retest(i):
        if i >= 2:
            prev_move = ev.closes[i - 1] - ev.opens[i - 1]
            if prev_move >= 0.8 * ev.atr14[i] and ev.lows[i] <= ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif prev_move <= -0.8 * ev.atr14[i] and ev.highs[i] >= ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["s_orderblock_retest"] = s_orderblock_retest

    # 54. 36-Hour Liquidity Pool Sweep
    def s_sweep_pool36(i):
        if ev.highs[i] >= ev.swing_high36[i] and ev.closes[i] < ev.swing_high36[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        elif ev.lows[i] <= ev.swing_low36[i] and ev.closes[i] > ev.swing_low36[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        return None

    sigs["s_sweep_pool36"] = s_sweep_pool36

    # 55. Engulfing Candle at EMA 50
    def s_engulfing_ema50(i):
        if i >= 1:
            body = abs(ev.closes[i] - ev.opens[i])
            prev_b = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if body > prev_b:
                if ev.closes[i] > ev.opens[i] and ev.lows[i] <= ev.ema50[i] and ev.closes[i] > ev.ema50[i]:
                    return "buy"
                elif ev.closes[i] < ev.opens[i] and ev.highs[i] >= ev.ema50[i] and ev.closes[i] < ev.ema50[i]:
                    return "sell"
        return None

    sigs["s_engulfing_ema50"] = s_engulfing_ema50

    return sigs
