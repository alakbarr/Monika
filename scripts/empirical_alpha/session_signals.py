import numpy as np
from scripts.empirical_alpha.evaluator import calculate_ema


def get_asset_specific_signals(ev, sym: str):
    sigs = {}
    s = sym.upper()

    # Session masks
    is_asian = lambda i: ev.hours[i] in (22, 23, 0, 1, 2, 3, 4, 5)
    is_london = lambda i: ev.hours[i] in (7, 8, 9, 10, 11, 12)
    is_ny = lambda i: ev.hours[i] in (13, 14, 15, 16, 17, 18, 19)
    is_tokyo = lambda i: ev.hours[i] in (0, 1, 2, 3, 4, 5)
    is_sydney = lambda i: ev.hours[i] in (21, 22, 23, 0, 1, 2)
    is_overlap = lambda i: ev.hours[i] in (13, 14, 15, 16)
    is_energy = lambda i: ev.hours[i] in (12, 13, 14, 15, 16, 17, 18)

    # -------------------------------------------------------------
    # 1. EUROPEAN & US SESSIONS (EURUSD & GBPUSD & COMMODITIES)
    # -------------------------------------------------------------
    # London Trend Setups (07:00 - 12:00 UTC)
    def lon_ema9_21(i):
        if is_london(i):
            if ev.ema9[i] > ev.ema21[i] and ev.closes[i] > ev.ema9[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema9[i] < ev.ema21[i] and ev.closes[i] < ev.ema9[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["lon_ema9_21_trend"] = lon_ema9_21

    def lon_ema20_bounce(i):
        if is_london(i):
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

    sigs["lon_ema20_bounce"] = lon_ema20_bounce

    def lon_ema50_bounce(i):
        if is_london(i):
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

    sigs["lon_ema50_bounce"] = lon_ema50_bounce

    def lon_donchian8(i):
        if is_london(i) and i >= 8:
            dh = np.max(ev.highs[i - 8 : i])
            dl = np.min(ev.lows[i - 8 : i])
            if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["lon_donchian8_break"] = lon_donchian8

    def lon_donchian12(i):
        if is_london(i) and i >= 12:
            dh = np.max(ev.highs[i - 12 : i])
            dl = np.min(ev.lows[i - 12 : i])
            if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["lon_donchian12_break"] = lon_donchian12

    def lon_three_bar(i):
        if is_london(i) and i >= 3:
            if ev.closes[i] > ev.opens[i] and ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i - 2] > ev.opens[i - 2]:
                return "buy"
            elif (
                ev.closes[i] < ev.opens[i] and ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i - 2] < ev.opens[i - 2]
            ):
                return "sell"
        return None

    sigs["lon_three_bar_thrust"] = lon_three_bar

    def lon_rsi7_dip(i):
        if is_london(i):
            if ev.closes[i] > ev.ema50[i] and ev.rsi7[i] <= 26 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema50[i] and ev.rsi7[i] >= 74 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["lon_rsi7_dip"] = lon_rsi7_dip

    def lon_stoch_cross(i):
        if is_london(i):
            if (
                ev.closes[i] > ev.ema50[i]
                and ev.stoch_k[i - 1] <= 25
                and ev.stoch_k[i] > ev.stoch_d[i]
                and ev.closes[i] > ev.opens[i]
            ):
                return "buy"
            elif (
                ev.closes[i] < ev.ema50[i]
                and ev.stoch_k[i - 1] >= 75
                and ev.stoch_k[i] < ev.stoch_d[i]
                and ev.closes[i] < ev.opens[i]
            ):
                return "sell"
        return None

    sigs["lon_stoch_cross"] = lon_stoch_cross

    def lon_pinbar12(i):
        if is_london(i):
            rng = max(1e-7, ev.highs[i] - ev.lows[i])
            if rng >= 0.6 * ev.atr14[i]:
                lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                if lw / rng >= 0.50 and ev.lows[i] <= ev.swing_low12[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif uw / rng >= 0.50 and ev.highs[i] >= ev.swing_high12[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["lon_pinbar12_swing"] = lon_pinbar12

    def lon_fvg_retest(i):
        if is_london(i) and i >= 3:
            if ev.lows[i - 1] > ev.highs[i - 3] and ev.closes[i] > ev.ema50[i]:
                if ev.lows[i] <= ev.lows[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
            elif ev.highs[i - 1] < ev.lows[i - 3] and ev.closes[i] < ev.ema50[i]:
                if ev.highs[i] >= ev.highs[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["lon_fvg_retest"] = lon_fvg_retest

    # -------------------------------------------------------------
    # NY Session Setups (13:00 - 19:00 UTC)
    # -------------------------------------------------------------
    def ny_ema9_21(i):
        if is_ny(i):
            if ev.ema9[i] > ev.ema21[i] and ev.closes[i] > ev.ema9[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema9[i] < ev.ema21[i] and ev.closes[i] < ev.ema9[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ny_ema9_21_trend"] = ny_ema9_21

    def ny_ema20_bounce(i):
        if is_ny(i):
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

    sigs["ny_ema20_bounce"] = ny_ema20_bounce

    def ny_donchian10(i):
        if is_ny(i) and i >= 10:
            dh = np.max(ev.highs[i - 10 : i])
            dl = np.min(ev.lows[i - 10 : i])
            if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ny_donchian10_break"] = ny_donchian10

    def ny_donchian16(i):
        if is_ny(i) and i >= 16:
            dh = np.max(ev.highs[i - 16 : i])
            dl = np.min(ev.lows[i - 16 : i])
            if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ny_donchian16_break"] = ny_donchian16

    def ny_three_bar(i):
        if is_ny(i) and i >= 3:
            if ev.closes[i] > ev.opens[i] and ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i - 2] > ev.opens[i - 2]:
                return "buy"
            elif (
                ev.closes[i] < ev.opens[i] and ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i - 2] < ev.opens[i - 2]
            ):
                return "sell"
        return None

    sigs["ny_three_bar_thrust"] = ny_three_bar

    def ny_rsi7_dip(i):
        if is_ny(i):
            if ev.closes[i] > ev.ema50[i] and ev.rsi7[i] <= 26 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema50[i] and ev.rsi7[i] >= 74 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ny_rsi7_dip"] = ny_rsi7_dip

    def ny_stoch_cross(i):
        if is_ny(i):
            if (
                ev.closes[i] > ev.ema50[i]
                and ev.stoch_k[i - 1] <= 25
                and ev.stoch_k[i] > ev.stoch_d[i]
                and ev.closes[i] > ev.opens[i]
            ):
                return "buy"
            elif (
                ev.closes[i] < ev.ema50[i]
                and ev.stoch_k[i - 1] >= 75
                and ev.stoch_k[i] < ev.stoch_d[i]
                and ev.closes[i] < ev.opens[i]
            ):
                return "sell"
        return None

    sigs["ny_stoch_cross"] = ny_stoch_cross

    def ny_pinbar24(i):
        if is_ny(i):
            rng = max(1e-7, ev.highs[i] - ev.lows[i])
            if rng >= 0.65 * ev.atr14[i]:
                lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                if lw / rng >= 0.50 and ev.lows[i] <= ev.swing_low24[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif uw / rng >= 0.50 and ev.highs[i] >= ev.swing_high24[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["ny_pinbar24_swing"] = ny_pinbar24

    def ny_fvg_retest(i):
        if is_ny(i) and i >= 3:
            if ev.lows[i - 1] > ev.highs[i - 3] and ev.closes[i] > ev.ema50[i]:
                if ev.lows[i] <= ev.lows[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
            elif ev.highs[i - 1] < ev.lows[i - 3] and ev.closes[i] < ev.ema50[i]:
                if ev.highs[i] >= ev.highs[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["ny_fvg_retest"] = ny_fvg_retest

    # -------------------------------------------------------------
    # Asian Session Range Fades (22:00 - 05:00 UTC)
    # -------------------------------------------------------------
    def asia_bb15_fade(i):
        if is_asian(i):
            if ev.closes[i] <= ev.bb15_low[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] >= ev.bb15_up[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_bb15_fade"] = asia_bb15_fade

    def asia_bb20_fade(i):
        if is_asian(i):
            if ev.lows[i] <= ev.bb_lower[i] and ev.closes[i] > ev.bb_lower[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.highs[i] >= ev.bb_upper[i] and ev.closes[i] < ev.bb_upper[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_bb20_fade"] = asia_bb20_fade

    def asia_vwap_dev10(i):
        if is_asian(i):
            dev = ev.closes[i] - ev.vwap[i]
            if dev <= -0.9 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif dev >= 0.9 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_vwap_dev10"] = asia_vwap_dev10

    def asia_vwap_dev13(i):
        if is_asian(i):
            dev = ev.closes[i] - ev.vwap[i]
            if dev <= -1.2 * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif dev >= 1.2 * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_vwap_dev13"] = asia_vwap_dev13

    def asia_rsi7_fade(i):
        if is_asian(i):
            if ev.rsi7[i] <= 24 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.rsi7[i] >= 76 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_rsi7_fade"] = asia_rsi7_fade

    def asia_rsi14_fade(i):
        if is_asian(i):
            if ev.rsi14[i] <= 32 and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.rsi14[i] >= 68 and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_rsi14_fade"] = asia_rsi14_fade

    def asia_stoch_cross(i):
        if is_asian(i):
            if ev.stoch_k[i - 1] <= 22 and ev.stoch_k[i] > ev.stoch_d[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.stoch_k[i - 1] >= 78 and ev.stoch_k[i] < ev.stoch_d[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["asia_stoch_cross"] = asia_stoch_cross

    def asia_pinbar12(i):
        if is_asian(i):
            rng = max(1e-7, ev.highs[i] - ev.lows[i])
            if rng >= 0.55 * ev.atr14[i]:
                lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                if lw / rng >= 0.50 and ev.lows[i] <= ev.swing_low12[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif uw / rng >= 0.50 and ev.highs[i] >= ev.swing_high12[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["asia_pinbar12_fade"] = asia_pinbar12

    def asia_two_bar_rev(i):
        if is_asian(i) and i >= 1:
            b1 = abs(ev.closes[i] - ev.opens[i])
            b0 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if b1 >= 0.5 * ev.atr14[i] and b0 >= 0.5 * ev.atr14[i]:
                if ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["asia_two_bar_rev"] = asia_two_bar_rev

    def asia_harami_fade(i):
        if is_asian(i) and i >= 1:
            if ev.highs[i] < ev.highs[i - 1] and ev.lows[i] > ev.lows[i - 1]:
                if ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["asia_harami_fade"] = asia_harami_fade

    # -------------------------------------------------------------
    # Tokyo Specific Setups (00:00 - 05:00 UTC)
    # -------------------------------------------------------------
    def tokyo_sweep_12(i):
        if is_tokyo(i):
            h = ev.swing_high12[i]
            l = ev.swing_low12[i]
            if ev.highs[i] >= h and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["tokyo_sweep_12"] = tokyo_sweep_12

    def tokyo_drift_ema20(i):
        if is_tokyo(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["tokyo_drift_ema20"] = tokyo_drift_ema20

    def tokyo_fix_rsi(i):
        if ev.hours[i] in (1, 2, 3):
            if ev.rsi7[i] >= 72 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi7[i] <= 28 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["tokyo_fix_rsi_fade"] = tokyo_fix_rsi

    # -------------------------------------------------------------
    # Sydney Specific Setups (21:00 - 02:00 UTC)
    # -------------------------------------------------------------
    def sydney_pulse_ema20(i):
        if is_sydney(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["sydney_pulse_ema20"] = sydney_pulse_ema20

    def sydney_fade_bb15(i):
        if is_sydney(i):
            if ev.closes[i] <= ev.bb15_low[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] >= ev.bb15_up[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["sydney_fade_bb15"] = sydney_fade_bb15

    # -------------------------------------------------------------
    # Energy Cash Session Setups (12:00 - 18:00 UTC)
    # -------------------------------------------------------------
    def energy_ema20_drive(i):
        if is_energy(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["energy_ema20_drive"] = energy_ema20_drive

    def energy_donchian8(i):
        if is_energy(i) and i >= 8:
            dh = np.max(ev.highs[i - 8 : i])
            dl = np.min(ev.lows[i - 8 : i])
            if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["energy_donchian8_break"] = energy_donchian8

    def energy_three_bar(i):
        if is_energy(i) and i >= 3:
            if ev.closes[i] > ev.opens[i] and ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i - 2] > ev.opens[i - 2]:
                return "buy"
            elif (
                ev.closes[i] < ev.opens[i] and ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i - 2] < ev.opens[i - 2]
            ):
                return "sell"
        return None

    sigs["energy_three_bar_thrust"] = energy_three_bar

    # -------------------------------------------------------------
    # Pure 24/7 Technical Setups (BTC & All Assets)
    # -------------------------------------------------------------
    for f, sl in [(5, 13), (8, 21), (9, 21), (13, 34), (20, 50)]:
        f_ema = calculate_ema(ev.closes, f)
        sl_ema = calculate_ema(ev.closes, sl)

        def make_ema_x(fa, sa):
            def fn(i):
                if fa[i] > sa[i] and fa[i - 1] <= sa[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif fa[i] < sa[i] and fa[i - 1] >= sa[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"cross_ema_{f}_{sl}"] = make_ema_x(f_ema, sl_ema)

    return sigs
