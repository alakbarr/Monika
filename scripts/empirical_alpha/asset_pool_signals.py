import numpy as np


def generate_asset_signal_pool(ev):
    sigs = {}

    # 1. Modular Trend Pullback Family (TPB)
    for ema_p in [9, 13, 20, 21, 34, 50]:
        ema_arr = getattr(ev, f"ema{ema_p}", None)
        if ema_arr is None:
            continue

        # Buy on low <= ema and close > ema, Sell on high >= ema and close < ema
        def make_ema_pb(arr, p):
            def fn(i):
                if (
                    ev.closes[i] > ev.ema50[i]
                    and ev.lows[i] <= arr[i]
                    and ev.closes[i] > arr[i]
                    and ev.closes[i] > ev.opens[i]
                ):
                    return "buy"
                elif (
                    ev.closes[i] < ev.ema50[i]
                    and ev.highs[i] >= arr[i]
                    and ev.closes[i] < arr[i]
                    and ev.closes[i] < ev.opens[i]
                ):
                    return "sell"
                return None

            return fn

        sigs[f"ema{ema_p}_trend_bounce"] = make_ema_pb(ema_arr, ema_p)

    # 2. Modular Donchian Breakout Family (DCH)
    for d_period in [8, 10, 12, 16, 20, 24]:

        def make_donch(p):
            def fn(i):
                if i >= p:
                    dh = np.max(ev.highs[i - p : i])
                    dl = np.min(ev.lows[i - p : i])
                    if ev.closes[i] > dh and ev.closes[i] > ev.ema50[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < dl and ev.closes[i] < ev.ema50[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"donchian_{d_period}_breakout"] = make_donch(d_period)

    # 3. Modular Bollinger Mean Reversion Family (BBM)
    for num_sd in [1.5, 2.0, 2.5]:
        sd_tag = str(num_sd).replace(".", "")
        if num_sd == 1.5:
            up, low = ev.bb15_up, ev.bb15_low
        elif num_sd == 2.0:
            up, low = ev.bb_upper, ev.bb_lower
        else:
            up, low = ev.bb25_up, ev.bb25_low

        def make_bb(u_arr, l_arr):
            def fn(i):
                if ev.lows[i] <= l_arr[i] and ev.closes[i] > l_arr[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.highs[i] >= u_arr[i] and ev.closes[i] < u_arr[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"bb_{sd_tag}_reversion"] = make_bb(up, low)

    # 4. Modular RSI Extreme Family (RSI)
    for rsi_name, thresh_low, thresh_high in [
        ("rsi7", 18, 82),
        ("rsi7", 22, 78),
        ("rsi7", 26, 74),
        ("rsi9", 22, 78),
        ("rsi9", 28, 72),
        ("rsi14", 28, 72),
        ("rsi14", 32, 68),
        ("rsi14", 35, 65),
        ("rsi21", 36, 64),
        ("rsi21", 40, 60),
    ]:
        rsi_arr = getattr(ev, rsi_name)

        def make_rsi(arr, tl, th):
            def fn(i):
                if arr[i] <= tl and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif arr[i] >= th and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"{rsi_name}_{thresh_low}_{thresh_high}_extreme"] = make_rsi(rsi_arr, thresh_low, thresh_high)

    # 5. Modular Stochastic Extreme Cross Family (STC)
    for stoch_name, k_lvl in [
        ("stoch8", 18),
        ("stoch8", 22),
        ("stoch", 20),
        ("stoch", 25),
        ("stoch21", 22),
        ("stoch21", 28),
    ]:
        if stoch_name == "stoch8":
            k_arr, d_arr = ev.stoch8_k, ev.stoch8_d
        elif stoch_name == "stoch21":
            k_arr, d_arr = ev.stoch21_k, ev.stoch21_d
        else:
            k_arr, d_arr = ev.stoch_k, ev.stoch_d

        def make_stoch(k_a, d_a, lvl):
            def fn(i):
                if k_a[i - 1] <= lvl and k_a[i] > d_a[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif k_a[i - 1] >= (100 - lvl) and k_a[i] < d_a[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"{stoch_name}_{k_lvl}_cross"] = make_stoch(k_arr, d_arr, k_lvl)

    # 6. Modular VWAP Deviation Family (VWP)
    for dev_mult in [0.8, 1.0, 1.2, 1.5]:
        d_tag = str(dev_mult).replace(".", "")

        def make_vwap(mult):
            def fn(i):
                dev = ev.closes[i] - ev.vwap[i]
                if dev <= -mult * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif dev >= mult * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"vwap_dev_{d_tag}_fade"] = make_vwap(dev_mult)

    # 7. Session Window Exploits (SES)
    # Tokyo Open (00:00 - 02:00)
    def s_tokyo_sweep(i):
        if ev.hours[i] in (0, 1, 2):
            h = ev.swing_high12[i]
            l = ev.swing_low12[i]
            if ev.highs[i] >= h and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_tokyo_sweep"] = s_tokyo_sweep

    # Tokyo Fix (01:00 - 03:00)
    def s_tokyo_fix(i):
        if ev.hours[i] in (1, 2, 3):
            h = ev.swing_high8[i]
            l = ev.swing_low8[i]
            if ev.highs[i] >= h and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_tokyo_fix"] = s_tokyo_fix

    # Asian Range Fade (22:00 - 05:00)
    def s_asian_fade(i):
        if ev.hours[i] in (22, 23, 0, 1, 2, 3, 4, 5):
            if ev.closes[i] >= ev.bb_upper[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.closes[i] <= ev.bb_lower[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_asian_fade"] = s_asian_fade

    # Frankfurt Open Drive (06:00 - 07:00)
    def s_frankfurt_drive(i):
        if ev.hours[i] in (6, 7):
            ah = np.max(ev.highs[max(0, i - 6) : i])
            al = np.min(ev.lows[max(0, i - 6) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["session_frankfurt_drive"] = s_frankfurt_drive

    # London Open Volume Breakout (07:00 - 09:00)
    def s_london_open(i):
        if ev.hours[i] in (7, 8):
            ah = np.max(ev.highs[max(0, i - 7) : i])
            al = np.min(ev.lows[max(0, i - 7) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["session_london_open"] = s_london_open

    # London Morning Drive (08:00 - 11:00)
    def s_london_morning(i):
        if ev.hours[i] in (8, 9, 10):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 50:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 50:
                return "sell"
        return None

    sigs["session_london_morning"] = s_london_morning

    # London Lunch Mean Revert (11:00 - 13:00)
    def s_london_lunch(i):
        if ev.hours[i] in (11, 12):
            if ev.rsi7[i] >= 68 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi7[i] <= 32 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_london_lunch"] = s_london_lunch

    # London/NY Overlap Surge (13:00 - 16:00)
    def s_overlap_surge(i):
        if ev.hours[i] in (13, 14, 15, 16):
            if ev.ema9[i] > ev.ema21[i] and ev.closes[i] > ev.ema9[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema9[i] < ev.ema21[i] and ev.closes[i] < ev.ema9[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["session_overlap_surge"] = s_overlap_surge

    # NY Open Reversal (13:00 - 15:30)
    def s_ny_reversal(i):
        if ev.hours[i] in (13, 14, 15):
            lh = np.max(ev.highs[max(0, i - 5) : i])
            ll = np.min(ev.lows[max(0, i - 5) : i])
            if ev.highs[i] >= lh and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= ll and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_ny_reversal"] = s_ny_reversal

    # London Close Fade (15:00 - 17:00)
    def s_london_close(i):
        if ev.hours[i] in (15, 16, 17):
            if ev.rsi14[i] >= 64 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi14[i] <= 36 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_london_close"] = s_london_close

    # NY Afternoon Trend (17:00 - 20:00)
    def s_ny_afternoon(i):
        if ev.hours[i] in (17, 18, 19):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 50:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 50:
                return "sell"
        return None

    sigs["session_ny_afternoon"] = s_ny_afternoon

    # US Close Range Fade (20:00 - 22:00)
    def s_us_close(i):
        if ev.hours[i] in (20, 21):
            if ev.closes[i] >= ev.bb_upper[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.closes[i] <= ev.bb_lower[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["session_us_close"] = s_us_close

    # Sydney Open Pulse (22:00 - 02:00)
    def s_sydney_pulse(i):
        if ev.hours[i] in (22, 23, 0, 1):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["session_sydney_pulse"] = s_sydney_pulse

    # 8. Price Action / SMC Modular Setups (PAC)
    # Pinbars at 12h / 24h / 48h
    for sw_name in ["swing_low12", "swing_low24", "swing_low48"]:
        tag = sw_name.replace("swing_low", "")
        sh_arr = getattr(ev, f"swing_high{tag}")
        sl_arr = getattr(ev, sw_name)

        def make_pinbar(h_arr, l_arr):
            def fn(i):
                rng = max(1e-7, ev.highs[i] - ev.lows[i])
                if rng >= 0.6 * ev.atr14[i]:
                    lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                    uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                    if lw / rng >= 0.50 and ev.lows[i] <= l_arr[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif uw / rng >= 0.50 and ev.highs[i] >= h_arr[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"pinbar_swing{tag}"] = make_pinbar(sh_arr, sl_arr)

    # Rejection Wick at 12h / 24h / 48h
    for sw_name in ["swing_low12", "swing_low24", "swing_low48"]:
        tag = sw_name.replace("swing_low", "")
        sh_arr = getattr(ev, f"swing_high{tag}")
        sl_arr = getattr(ev, sw_name)

        def make_rejection(h_arr, l_arr):
            def fn(i):
                if ev.highs[i] >= h_arr[i] and ev.closes[i] < h_arr[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                elif ev.lows[i] <= l_arr[i] and ev.closes[i] > l_arr[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                return None

            return fn

        sigs[f"rejection_swing{tag}"] = make_rejection(sh_arr, sl_arr)

    # Consecutive Exhaustion 2, 3, 4 bars
    for n_bars in [2, 3, 4]:

        def make_consec(nb):
            mult = 0.5 * nb

            def fn(i):
                if i >= nb:
                    tot = ev.closes[i] - ev.opens[i - nb + 1]
                    if tot <= -mult * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif tot >= mult * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"consecutive_{n_bars}bar_exhaustion"] = make_consec(n_bars)

    # Two-Bar Reversal
    def s_two_bar_rev(i):
        if i >= 1:
            b1 = abs(ev.closes[i] - ev.opens[i])
            b0 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if b1 >= 0.5 * ev.atr14[i] and b0 >= 0.5 * ev.atr14[i]:
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

    sigs["two_bar_reversal_pattern"] = s_two_bar_rev

    # Inside Bar Fakeout
    def s_ib_fakeout(i):
        if i >= 2:
            if ev.highs[i - 1] <= ev.highs[i - 2] and ev.lows[i - 1] >= ev.lows[i - 2]:
                if ev.lows[i] < ev.lows[i - 2] and ev.closes[i] > ev.lows[i - 2] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.highs[i] > ev.highs[i - 2] and ev.closes[i] < ev.highs[i - 2] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["inside_bar_fakeout_spring"] = s_ib_fakeout

    # Star Pattern Reversal
    def s_star(i):
        if i >= 2:
            b1 = abs(ev.closes[i - 2] - ev.opens[i - 2])
            b2 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            b3 = abs(ev.closes[i] - ev.opens[i])
            if b1 >= 0.5 * ev.atr14[i] and b2 <= 0.45 * b1 and b3 >= 0.45 * b1:
                if ev.closes[i - 2] < ev.opens[i - 2] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 2] > ev.opens[i - 2] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["star_reversal_pattern"] = s_star

    # Harami Pattern Reversal
    def s_harami(i):
        if i >= 1:
            if ev.highs[i] < ev.highs[i - 1] and ev.lows[i] > ev.lows[i - 1]:
                if ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["harami_reversal_pattern"] = s_harami

    # FVG Trend Retest
    def s_fvg(i):
        if i >= 3:
            if ev.lows[i - 1] > ev.highs[i - 3] and ev.closes[i] > ev.ema50[i]:
                if ev.lows[i] <= ev.lows[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
            elif ev.highs[i - 1] < ev.lows[i - 3] and ev.closes[i] < ev.ema50[i]:
                if ev.highs[i] >= ev.highs[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["fvg_trend_retest"] = s_fvg

    # Order Block Retest
    def s_ob(i):
        if i >= 2:
            prev_move = ev.closes[i - 1] - ev.opens[i - 1]
            if prev_move >= 0.8 * ev.atr14[i] and ev.lows[i] <= ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif prev_move <= -0.8 * ev.atr14[i] and ev.highs[i] >= ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["orderblock_retest"] = s_ob

    # Engulfing at EMA 50
    def s_engulf_ema50(i):
        if i >= 1:
            b1 = abs(ev.closes[i] - ev.opens[i])
            b0 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if b1 > b0:
                if ev.closes[i] > ev.opens[i] and ev.lows[i] <= ev.ema50[i] and ev.closes[i] > ev.ema50[i]:
                    return "buy"
                elif ev.closes[i] < ev.opens[i] and ev.highs[i] >= ev.ema50[i] and ev.closes[i] < ev.ema50[i]:
                    return "sell"
        return None

    sigs["engulfing_ema50"] = s_engulf_ema50

    return sigs
