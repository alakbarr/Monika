import numpy as np


def build_omni_signals(ev, sym: str):
    sigs = {}
    s = sym.upper()

    # Session helper lambdas
    is_asian = lambda i: ev.hours[i] in (22, 23, 0, 1, 2, 3, 4, 5)
    is_tokyo = lambda i: ev.hours[i] in (0, 1, 2, 3, 4, 5)
    is_london = lambda i: ev.hours[i] in (7, 8, 9, 10, 11, 12)
    is_ny = lambda i: ev.hours[i] in (13, 14, 15, 16, 17, 18, 19)
    is_sydney = lambda i: ev.hours[i] in (21, 22, 23, 0, 1, 2)
    is_overlap = lambda i: ev.hours[i] in (13, 14, 15, 16)
    is_europe_mid = lambda i: ev.hours[i] in (11, 12, 15, 16)

    # 1. FAMILY: EMA TREND BOUNCES (24/7 & In-Session)
    for ep in [5, 8, 9, 10, 13, 15, 20, 21, 25, 34, 40, 50]:
        arr = getattr(ev, f"ema{ep}", None)
        if arr is None:
            continue

        # 24/7
        def make_t_ema(a, p):
            def fn(i):
                if (
                    ev.closes[i] > ev.ema50[i]
                    and ev.lows[i] <= a[i]
                    and ev.closes[i] > a[i]
                    and ev.closes[i] > ev.opens[i]
                ):
                    return "buy"
                elif (
                    ev.closes[i] < ev.ema50[i]
                    and ev.highs[i] >= a[i]
                    and ev.closes[i] < a[i]
                    and ev.closes[i] < ev.opens[i]
                ):
                    return "sell"
                return None

            return fn

        sigs[f"t_ema{ep}_bounce"] = make_t_ema(arr, ep)

        # In London
        def make_lon_ema(a, p):
            def fn(i):
                if is_london(i):
                    if ev.closes[i] > a[i] and ev.lows[i] <= a[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < a[i] and ev.highs[i] >= a[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"lon_ema{ep}_bounce"] = make_lon_ema(arr, ep)

        # In NY
        def make_ny_ema(a, p):
            def fn(i):
                if is_ny(i):
                    if ev.closes[i] > a[i] and ev.lows[i] <= a[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < a[i] and ev.highs[i] >= a[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"ny_ema{ep}_bounce"] = make_ny_ema(arr, ep)

        # In Tokyo / Sydney
        def make_tokyo_ema(a, p):
            def fn(i):
                if is_tokyo(i) or is_sydney(i):
                    if ev.closes[i] > a[i] and ev.lows[i] <= a[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < a[i] and ev.highs[i] >= a[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"tokyo_ema{ep}_bounce"] = make_tokyo_ema(arr, ep)

    # 2. FAMILY: DONCHIAN BREAKOUTS (24/7 & In-Session)
    for dp in [6, 8, 10, 12, 14, 16, 20, 24, 28]:

        def make_dch(p):
            def fn(i):
                if i >= p:
                    dh = np.max(ev.highs[i - p : i])
                    dl = np.min(ev.lows[i - p : i])
                    if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"dch_{dp}_break"] = make_dch(dp)

        def make_lon_dch(p):
            def fn(i):
                if is_london(i) and i >= p:
                    dh = np.max(ev.highs[i - p : i])
                    dl = np.min(ev.lows[i - p : i])
                    if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"lon_dch_{dp}_break"] = make_lon_dch(dp)

        def make_ny_dch(p):
            def fn(i):
                if is_ny(i) and i >= p:
                    dh = np.max(ev.highs[i - p : i])
                    dl = np.min(ev.lows[i - p : i])
                    if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"ny_dch_{dp}_break"] = make_ny_dch(dp)

    # 3. FAMILY: BOLLINGER MEAN REVERSION (24/7 & Sessions)
    for sd in [1.5, 2.0, 2.5]:
        sd_tag = str(sd).replace(".", "")
        if sd == 1.5:
            u, l = ev.bb15_up, ev.bb15_low
        elif sd == 2.0:
            u, l = ev.bb_upper, ev.bb_lower
        else:
            u, l = ev.bb25_up, ev.bb25_low

        def make_bb_all(u_a, l_a):
            def fn(i):
                if ev.lows[i] <= l_a[i] and ev.closes[i] > l_a[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.highs[i] >= u_a[i] and ev.closes[i] < u_a[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"bb_{sd_tag}_fade_all"] = make_bb_all(u, l)

        def make_bb_asian(u_a, l_a):
            def fn(i):
                if is_asian(i):
                    if ev.lows[i] <= l_a[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.highs[i] >= u_a[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"bb_{sd_tag}_fade_asian"] = make_bb_asian(u, l)

        def make_bb_mid(u_a, l_a):
            def fn(i):
                if is_europe_mid(i):
                    if ev.lows[i] <= l_a[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif ev.highs[i] >= u_a[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"bb_{sd_tag}_fade_mid"] = make_bb_mid(u, l)

    # 4. FAMILY: RSI EXTREMES & PULLBACKS
    for rp in [5, 7, 9, 12, 14, 18, 21]:
        arr = getattr(ev, f"rsi{rp}", None)
        if arr is None:
            continue

        # Oversold / Overbought reversal
        def make_rsi_rev(a, p):
            lvl_l = 25 if p <= 7 else 30
            lvl_h = 75 if p <= 7 else 70

            def fn(i):
                if a[i] <= lvl_l and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif a[i] >= lvl_h and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"rsi{rp}_rev_all"] = make_rsi_rev(arr, rp)

        # In Asian session
        def make_rsi_asia(a, p):
            lvl_l = 28 if p <= 7 else 35
            lvl_h = 72 if p <= 7 else 65

            def fn(i):
                if is_asian(i):
                    if a[i] <= lvl_l and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif a[i] >= lvl_h and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"rsi{rp}_rev_asia"] = make_rsi_asia(arr, rp)

        # In Trend Pullback (Uptrend dip / Downtrend rally)
        def make_rsi_trend(a, p):
            def fn(i):
                if ev.closes[i] > ev.ema50[i] and 38 <= a[i] <= 48 and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i] < ev.ema50[i] and 52 <= a[i] <= 62 and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"rsi{rp}_trend_dip"] = make_rsi_trend(arr, rp)

    # 5. FAMILY: STOCHASTIC CROSSES (Fast / Standard / Slow)
    for sp in [5, 8, 10, 14, 21]:
        ka = getattr(ev, f"stoch{sp}_k" if sp != 14 else "stoch_k", None)
        da = getattr(ev, f"stoch{sp}_d" if sp != 14 else "stoch_d", None)
        if ka is None:
            continue

        # Reversal cross
        def make_st_rev(k, d, p):
            def fn(i):
                if k[i - 1] <= 22 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif k[i - 1] >= 78 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"stoch{sp}_rev_all"] = make_st_rev(ka, da, sp)

        # In Asian session
        def make_st_asia(k, d, p):
            def fn(i):
                if is_asian(i):
                    if k[i - 1] <= 25 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif k[i - 1] >= 75 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"stoch{sp}_rev_asia"] = make_st_asia(ka, da, sp)

        # In Trend
        def make_st_trend(k, d, p):
            def fn(i):
                if ev.closes[i] > ev.ema50[i] and k[i - 1] <= 28 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i] < ev.ema50[i] and k[i - 1] >= 72 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"stoch{sp}_trend_cross"] = make_st_trend(ka, da, sp)

    # 6. FAMILY: PINBARS & REJECTION WICKS (6, 12, 18, 24, 30, 48 bars)
    for sw in [6, 12, 18, 24, 30, 48]:
        ha = getattr(ev, f"swing_high{sw}", None)
        la = getattr(ev, f"swing_low{sw}", None)
        if ha is None or la is None:
            continue

        def make_pin(h, l, p):
            def fn(i):
                rng = max(1e-7, ev.highs[i] - ev.lows[i])
                if rng >= 0.55 * ev.atr14[i]:
                    lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                    uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                    if lw / rng >= 0.48 and ev.lows[i] <= l[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif uw / rng >= 0.48 and ev.highs[i] >= h[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"pinbar_sw{sw}"] = make_pin(ha, la, sw)

        def make_sweep(h, l, p):
            def fn(i):
                if ev.highs[i] >= h[i] and ev.closes[i] < h[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                elif ev.lows[i] <= l[i] and ev.closes[i] > l[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                return None

            return fn

        sigs[f"sweep_sw{sw}"] = make_sweep(ha, la, sw)

    # 7. FAMILY: CONSECUTIVE EXHAUSTION FADES (2, 3, 4 bars)
    for nb in [2, 3, 4]:

        def make_consec(n):
            mult = 0.45 * n

            def fn(i):
                if i >= n:
                    tot = ev.closes[i] - ev.opens[i - n + 1]
                    if tot <= -mult * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif tot >= mult * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"consec_{nb}bar_fade"] = make_consec(nb)

    # 8. FAMILY: CANDLESTICK PRICE ACTION (Two-Bar, Star, Harami, Engulfing)
    def two_bar_all(i):
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

    sigs["pa_two_bar_reversal"] = two_bar_all

    def star_all(i):
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

    sigs["pa_star_pattern"] = star_all

    def harami_all(i):
        if i >= 1:
            if ev.highs[i] < ev.highs[i - 1] and ev.lows[i] > ev.lows[i - 1]:
                if ev.closes[i - 1] < ev.opens[i - 1] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i - 1] > ev.opens[i - 1] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["pa_harami_reversal"] = harami_all

    def engulf_ema20(i):
        if i >= 1:
            b1 = abs(ev.closes[i] - ev.opens[i])
            b0 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if b1 > b0:
                if ev.closes[i] > ev.opens[i] and ev.lows[i] <= ev.ema20[i] and ev.closes[i] > ev.ema20[i]:
                    return "buy"
                elif ev.closes[i] < ev.opens[i] and ev.highs[i] >= ev.ema20[i] and ev.closes[i] < ev.ema20[i]:
                    return "sell"
        return None

    sigs["pa_engulfing_ema20"] = engulf_ema20

    def engulf_ema50(i):
        if i >= 1:
            b1 = abs(ev.closes[i] - ev.opens[i])
            b0 = abs(ev.closes[i - 1] - ev.opens[i - 1])
            if b1 > b0:
                if ev.closes[i] > ev.opens[i] and ev.lows[i] <= ev.ema50[i] and ev.closes[i] > ev.ema50[i]:
                    return "buy"
                elif ev.closes[i] < ev.opens[i] and ev.highs[i] >= ev.ema50[i] and ev.closes[i] < ev.ema50[i]:
                    return "sell"
        return None

    sigs["pa_engulfing_ema50"] = engulf_ema50

    def ib_fakeout(i):
        if i >= 2:
            if ev.highs[i - 1] <= ev.highs[i - 2] and ev.lows[i - 1] >= ev.lows[i - 2]:
                if ev.lows[i] < ev.lows[i - 2] and ev.closes[i] > ev.lows[i - 2] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.highs[i] > ev.highs[i - 2] and ev.closes[i] < ev.highs[i - 2] and ev.closes[i] < ev.opens[i]:
                    return "sell"
        return None

    sigs["pa_inside_bar_fakeout"] = ib_fakeout

    def double_ib_break(i):
        if i >= 2:
            if (
                ev.highs[i - 1] <= ev.highs[i - 2]
                and ev.lows[i - 1] >= ev.lows[i - 2]
                and ev.highs[i] <= ev.highs[i - 1]
                and ev.lows[i] >= ev.lows[i - 1]
            ):
                if ev.closes[i] > ev.ema20[i]:
                    return "buy"
                elif ev.closes[i] < ev.ema20[i]:
                    return "sell"
        return None

    sigs["pa_double_ib_break"] = double_ib_break

    # 9. FAMILY: VWAP SESSIONS (Asian / London Lunch / NY Afternoon)
    for dev in [0.7, 0.9, 1.1, 1.4]:
        dev_tag = str(dev).replace(".", "")

        def make_vwp_asia(d):
            def fn(i):
                if is_asian(i):
                    diff = ev.closes[i] - ev.vwap[i]
                    if diff <= -d * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif diff >= d * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"vwp_{dev_tag}_asia"] = make_vwp_asia(dev)

        def make_vwp_mid(d):
            def fn(i):
                if is_europe_mid(i):
                    diff = ev.closes[i] - ev.vwap[i]
                    if diff <= -d * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif diff >= d * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"vwp_{dev_tag}_mid"] = make_vwp_mid(dev)

    # 10. FAMILY: SESSIONS & TIME WINDOWS
    def ses_tokyo_open(i):
        if ev.hours[i] in (0, 1, 2):
            h = ev.swing_high12[i]
            l = ev.swing_low12[i]
            if ev.highs[i] >= h and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["ses_tokyo_open_sweep"] = ses_tokyo_open

    def ses_tokyo_fix(i):
        if ev.hours[i] in (1, 2, 3):
            h = ev.swing_high8[i]
            l = ev.swing_low8[i]
            if ev.highs[i] >= h and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= l and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["ses_tokyo_fix_fade"] = ses_tokyo_fix

    def ses_london_open(i):
        if ev.hours[i] in (7, 8):
            ah = np.max(ev.highs[max(0, i - 7) : i])
            al = np.min(ev.lows[max(0, i - 7) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ses_london_open_break"] = ses_london_open

    def ses_overlap(i):
        if is_overlap(i):
            if ev.ema9[i] > ev.ema21[i] and ev.closes[i] > ev.ema9[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema9[i] < ev.ema21[i] and ev.closes[i] < ev.ema9[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ses_overlap_surge"] = ses_overlap

    def ses_ny_reversal(i):
        if ev.hours[i] in (13, 14, 15):
            lh = np.max(ev.highs[max(0, i - 5) : i])
            ll = np.min(ev.lows[max(0, i - 5) : i])
            if ev.highs[i] >= lh and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= ll and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["ses_ny_open_reversal"] = ses_ny_reversal

    def ses_london_close(i):
        if ev.hours[i] in (15, 16, 17):
            if ev.rsi14[i] >= 63 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi14[i] <= 37 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["ses_london_close_fade"] = ses_london_close

    def ses_sydney_pulse(i):
        if is_sydney(i):
            if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ses_sydney_open_pulse"] = ses_sydney_pulse

    return sigs
