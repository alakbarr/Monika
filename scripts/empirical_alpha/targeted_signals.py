import numpy as np


def build_targeted_signals(ev, sym: str):
    sigs = {}
    s = sym.upper()

    # Time helpers
    is_asian = lambda i: ev.hours[i] in (22, 23, 0, 1, 2, 3, 4, 5)
    is_tokyo = lambda i: ev.hours[i] in (0, 1, 2, 3, 4, 5)
    is_tokyo_fix = lambda i: ev.hours[i] in (1, 2, 3)
    is_frankfurt = lambda i: ev.hours[i] in (6, 7)
    is_london = lambda i: ev.hours[i] in (7, 8, 9, 10, 11, 12)
    is_london_open = lambda i: ev.hours[i] in (7, 8, 9)
    is_london_morning = lambda i: ev.hours[i] in (8, 9, 10, 11)
    is_london_lunch = lambda i: ev.hours[i] in (11, 12, 13)
    is_ny = lambda i: ev.hours[i] in (13, 14, 15, 16, 17, 18, 19)
    is_ny_open = lambda i: ev.hours[i] in (13, 14, 15)
    is_overlap = lambda i: ev.hours[i] in (13, 14, 15, 16)
    is_london_fix = lambda i: ev.hours[i] in (15, 16)
    is_ny_afternoon = lambda i: ev.hours[i] in (17, 18, 19)
    is_sydney = lambda i: ev.hours[i] in (21, 22, 23, 0, 1)

    # ---------------------------------------------------------
    # 1. GBPUSD TARGETED SIGNALS
    # ---------------------------------------------------------
    if s == "GBPUSD":
        # Asian session Bollinger fades
        for sd, (u_arr, l_arr) in [
            (1.5, (ev.bb15_up, ev.bb15_low)),
            (2.0, (ev.bb_upper, ev.bb_lower)),
            (2.5, (ev.bb25_up, ev.bb25_low)),
        ]:
            sd_tag = str(sd).replace(".", "")

            def make_gbp_bb(u, l):
                def fn(i):
                    if is_asian(i):
                        if ev.lows[i] <= l[i] and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.highs[i] >= u[i] and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"gbp_asian_bb_{sd_tag}_fade"] = make_gbp_bb(u_arr, l_arr)

        # Asian session Donchian fades
        for dp in [4, 6, 8, 10, 12]:

            def make_gbp_asia_dch(p):
                def fn(i):
                    if is_asian(i) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.highs[i] >= dh and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= dl and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"gbp_asian_dch{dp}_fade"] = make_gbp_asia_dch(dp)

        # Asian session RSI fades
        for rp, (low_th, high_th) in [
            (5, (22, 78)),
            (7, (28, 72)),
            (9, (32, 68)),
            (10, (33, 67)),
            (12, (35, 65)),
            (14, (35, 65)),
        ]:
            rarr = getattr(ev, f"rsi{rp}", None)
            if rarr is not None:

                def make_gbp_rsi(a, lt, ht):
                    def fn(i):
                        if is_asian(i):
                            if a[i] <= lt and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif a[i] >= ht and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_asian_rsi{rp}_fade"] = make_gbp_rsi(rarr, low_th, high_th)

        # Asian session Fast Stochastics
        for sp in [5, 8, 10, 14]:
            ka = getattr(ev, f"stoch{sp}_k" if sp != 14 else "stoch_k", None)
            da = getattr(ev, f"stoch{sp}_d" if sp != 14 else "stoch_d", None)
            if ka is not None:

                def make_gbp_stoch(k, d):
                    def fn(i):
                        if is_asian(i):
                            if k[i - 1] <= 24 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif k[i - 1] >= 76 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_asian_stoch{sp}_cross"] = make_gbp_stoch(ka, da)

        # Asian EMA fades
        for ep in [15, 20, 25, 34]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_gbp_a_ema(ea):
                    def fn(i):
                        if is_asian(i):
                            if ev.lows[i] <= ea[i] and ev.closes[i] > ea[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ev.highs[i] >= ea[i] and ev.closes[i] < ea[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_asian_ema{ep}_fade"] = make_gbp_a_ema(earr)

        # Asian Pinbars
        for sp in [6, 10]:

            def make_gbp_asia_pin(p):
                ha = getattr(ev, f"swing_high{p}" if p != 10 else "swing_high8", ev.swing_high8)
                la = getattr(ev, f"swing_low{p}" if p != 10 else "swing_low8", ev.swing_low8)

                def fn(i):
                    if is_asian(i):
                        rng = max(1e-7, ev.highs[i] - ev.lows[i])
                        if rng >= 0.45 * ev.atr14[i]:
                            lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                            uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                            if lw / rng >= 0.45 and ev.lows[i] <= la[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif uw / rng >= 0.45 and ev.highs[i] >= ha[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                    return None

                return fn

            sigs[f"gbp_asian_pinbar{sp}"] = make_gbp_asia_pin(sp)

        # Frankfurt pre-market drift (06:00 - 07:00 UTC)
        def gbp_frankfurt(i):
            if is_frankfurt(i):
                if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
            return None

        sigs["gbp_frankfurt_drift"] = gbp_frankfurt

        # London Open momentum breakouts
        for dp in [4, 6, 8, 10]:

            def make_gbp_lon_dch(p):
                def fn(i):
                    if is_london_open(i) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"gbp_lon_open_dch{dp}"] = make_gbp_lon_dch(dp)

        # London Open EMA momentum
        for ep in [8, 13, 21]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_gbp_lon_ema(ea):
                    def fn(i):
                        if is_london_open(i):
                            if (
                                ev.closes[i] > ea[i]
                                and ev.closes[i] > ev.opens[i]
                                and ev.volumes[i] >= 1.05 * ev.vol_ma20[i]
                            ):
                                return "buy"
                            elif (
                                ev.closes[i] < ea[i]
                                and ev.closes[i] < ev.opens[i]
                                and ev.volumes[i] >= 1.05 * ev.vol_ma20[i]
                            ):
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_lon_open_ema{ep}_thrust"] = make_gbp_lon_ema(earr)

        # London Lunch Mean Reversions (11:00 - 13:00 UTC)
        for sd, (u_arr, l_arr) in [(1.5, (ev.bb15_up, ev.bb15_low)), (2.0, (ev.bb_upper, ev.bb_lower))]:
            sd_tag = str(sd).replace(".", "")

            def make_gbp_lunch_bb(u, l):
                def fn(i):
                    if is_london_lunch(i):
                        if ev.lows[i] <= l[i] and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.highs[i] >= u[i] and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"gbp_lunch_bb_{sd_tag}_fade"] = make_gbp_lunch_bb(u_arr, l_arr)

        for sp in [5, 8, 10]:
            ka = getattr(ev, f"stoch{sp}_k" if sp != 14 else "stoch_k", None)
            da = getattr(ev, f"stoch{sp}_d" if sp != 14 else "stoch_d", None)
            if ka is not None:

                def make_gbp_lunch_stoch(k, d):
                    def fn(i):
                        if is_london_lunch(i):
                            if k[i - 1] <= 25 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif k[i - 1] >= 75 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_lunch_stoch{sp}_cross"] = make_gbp_lunch_stoch(ka, da)

        for rp in [5, 7, 9]:
            rarr = getattr(ev, f"rsi{rp}", None)
            if rarr is not None:

                def make_gbp_lunch_rsi(ra):
                    def fn(i):
                        if is_london_lunch(i):
                            if ra[i] <= 26 and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ra[i] >= 74 and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_lunch_rsi{rp}_dip"] = make_gbp_lunch_rsi(rarr)

        # London Morning Trend Pullbacks (08:00 - 11:00 UTC)
        for ep in [9, 13, 15, 21, 25]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_gbp_morn_pb(ea):
                    def fn(i):
                        if is_london_morning(i):
                            if (
                                ev.closes[i] > ev.ema50[i]
                                and ev.lows[i] <= ea[i]
                                and ev.closes[i] > ea[i]
                                and ev.closes[i] > ev.opens[i]
                            ):
                                return "buy"
                            elif (
                                ev.closes[i] < ev.ema50[i]
                                and ev.highs[i] >= ea[i]
                                and ev.closes[i] < ea[i]
                                and ev.closes[i] < ev.opens[i]
                            ):
                                return "sell"
                        return None

                    return fn

                sigs[f"gbp_morn_ema{ep}_pb"] = make_gbp_morn_pb(earr)

        # NY Open Breakouts (13:00 - 15:00 UTC)
        for dp in [6, 8, 10]:

            def make_gbp_ny_dch(p):
                def fn(i):
                    if is_ny_open(i) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"gbp_ny_open_dch{dp}"] = make_gbp_ny_dch(dp)

        # NY Overlap Surge (13:00 - 16:00 UTC)
        def gbp_ny_surge(i):
            if is_overlap(i):
                if ev.closes[i] > ev.ema13[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 52:
                    return "buy"
                elif ev.closes[i] < ev.ema13[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 48:
                    return "sell"
            return None

        sigs["gbp_ny_overlap_surge"] = gbp_ny_surge

        # London Fix Reversal (15:00 - 16:00 UTC)
        def gbp_fix_reversal(i):
            if is_london_fix(i):
                if ev.rsi14[i] <= 38 and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.rsi14[i] >= 62 and ev.closes[i] < ev.opens[i]:
                    return "sell"
            return None

        sigs["gbp_london_fix_rev"] = gbp_fix_reversal

        # NY Afternoon Trend Drift (16:00 - 19:00 UTC)
        def gbp_ny_drift(i):
            if is_ny_afternoon(i):
                if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 50:
                    return "buy"
                elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 50:
                    return "sell"
            return None

        sigs["gbp_ny_afternoon_drift"] = gbp_ny_drift

        # Asian 2-bar and 3-bar exhaustion fades
        for nb in [2, 3]:

            def make_gbp_consec(n):
                mult = 0.40 * n

                def fn(i):
                    if is_asian(i) and i >= n:
                        tot = ev.closes[i] - ev.opens[i - n + 1]
                        if tot <= -mult * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif tot >= mult * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"gbp_asian_consec_{nb}bar_fade"] = make_gbp_consec(nb)

        # Asian Range Fades with variable lookbacks
        for lb in [3, 4, 5, 6, 7, 9, 10, 12, 14, 16]:

            def make_gbp_asia_w_fade(w):
                def fn(i):
                    if is_asian(i) and i >= w:
                        ah = np.max(ev.highs[i - w : i])
                        al = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= ah * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= al * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"gbp_asian_range_w{lb}_fade"] = make_gbp_asia_w_fade(lb)

        # London Lunch Range Fades
        for lb in [4, 6, 8, 10, 12]:

            def make_gbp_lunch_fade(w):
                def fn(i):
                    if is_london_lunch(i) and i >= w:
                        lh = np.max(ev.highs[i - w : i])
                        ll = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= lh * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= ll * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"gbp_lunch_range_w{lb}_fade"] = make_gbp_lunch_fade(lb)

        # NY Afternoon Fades
        for lb in [4, 6, 8, 10]:

            def make_gbp_ny_fade(w):
                def fn(i):
                    if is_ny_afternoon(i) and i >= w:
                        nh = np.max(ev.highs[i - w : i])
                        nl = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= nh * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= nl * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"gbp_ny_afternoon_w{lb}_fade"] = make_gbp_ny_fade(lb)

    # ---------------------------------------------------------
    # 2. USDJPY TARGETED SIGNALS
    # ---------------------------------------------------------
    if s == "USDJPY":
        # Tokyo session Bollinger fades
        for sd, (u_arr, l_arr) in [
            (1.5, (ev.bb15_up, ev.bb15_low)),
            (2.0, (ev.bb_upper, ev.bb_lower)),
            (2.5, (ev.bb25_up, ev.bb25_low)),
        ]:
            sd_tag = str(sd).replace(".", "")

            def make_jpy_bb(u, l):
                def fn(i):
                    if is_tokyo(i):
                        if ev.lows[i] <= l[i] and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.highs[i] >= u[i] and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"jpy_tokyo_bb_{sd_tag}_fade"] = make_jpy_bb(u_arr, l_arr)

        # Tokyo Fix Fades & Sweeps (01:00 - 03:00 UTC)
        def jpy_tokyo_fix_swing(i):
            if is_tokyo_fix(i):
                if ev.lows[i] <= ev.swing_low8[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.highs[i] >= ev.swing_high8[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
            return None

        sigs["jpy_tokyo_fix_sweep"] = jpy_tokyo_fix_swing

        # Tokyo Donchian Fades
        for dp in [4, 6, 8, 10, 12]:

            def make_jpy_t_fade(p):
                def fn(i):
                    if is_tokyo(i) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.highs[i] >= dh and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= dl and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"jpy_tokyo_dch{dp}_fade"] = make_jpy_t_fade(dp)

        # Tokyo Trend continuation (Close > EMA, bounce)
        for ep in [8, 10, 13, 15, 20, 25, 34]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_jpy_t_ema(ea):
                    def fn(i):
                        if is_tokyo(i):
                            if ev.closes[i] > ea[i] and ev.lows[i] <= ea[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ev.closes[i] < ea[i] and ev.highs[i] >= ea[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"jpy_tokyo_ema{ep}_bounce"] = make_jpy_t_ema(earr)

        # Tokyo Fast Stochastics
        for sp in [5, 8, 10, 14]:
            ka = getattr(ev, f"stoch{sp}_k" if sp != 14 else "stoch_k", None)
            da = getattr(ev, f"stoch{sp}_d" if sp != 14 else "stoch_d", None)
            if ka is not None:

                def make_jpy_stoch(k, d):
                    def fn(i):
                        if is_tokyo(i):
                            if k[i - 1] <= 24 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif k[i - 1] >= 76 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"jpy_tokyo_stoch{sp}_cross"] = make_jpy_stoch(ka, da)

        # Tokyo RSI dips
        for rp in [5, 7, 9, 10, 12, 14]:
            rarr = getattr(ev, f"rsi{rp}", None)
            if rarr is not None:

                def make_jpy_rsi(ra):
                    def fn(i):
                        if is_tokyo(i):
                            if ra[i] <= 28 and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ra[i] >= 72 and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"jpy_tokyo_rsi{rp}_dip"] = make_jpy_rsi(rarr)

        # Tokyo Donchian Breakouts
        for dp in [4, 6, 8, 10]:

            def make_jpy_t_dch(p):
                def fn(i):
                    if is_tokyo(i) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"jpy_tokyo_dch{dp}_break"] = make_jpy_t_dch(dp)

        # London & NY sessions for USDJPY
        for dp in [4, 6, 8, 12]:

            def make_jpy_lon_dch(p):
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

            sigs[f"jpy_lon_dch{dp}_break"] = make_jpy_lon_dch(dp)

        # USDJPY London open momentum thrust
        for ep in [9, 21]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_jpy_lon_ema(ea):
                    def fn(i):
                        if is_london_open(i):
                            if ev.closes[i] > ea[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ev.closes[i] < ea[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"jpy_lon_open_ema{ep}"] = make_jpy_lon_ema(earr)

        # USDJPY Consecutive Exhaustion Fades (2, 3 bars)
        for nb in [2, 3]:

            def make_jpy_consec(n):
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

            sigs[f"jpy_consec_{nb}bar_fade"] = make_jpy_consec(nb)

        # USDJPY Tokyo / Asian Range Fades with variable lookbacks
        for lb in [3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16]:

            def make_jpy_asia_w_fade(w):
                def fn(i):
                    if is_tokyo(i) and i >= w:
                        ah = np.max(ev.highs[i - w : i])
                        al = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= ah * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= al * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"jpy_tokyo_range_w{lb}_fade"] = make_jpy_asia_w_fade(lb)

        # USDJPY London lunch fades
        for lb in [4, 6, 8, 10]:

            def make_jpy_lunch_fade(w):
                def fn(i):
                    if is_london_lunch(i) and i >= w:
                        lh = np.max(ev.highs[i - w : i])
                        ll = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= lh * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= ll * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"jpy_lunch_range_w{lb}_fade"] = make_jpy_lunch_fade(lb)

    # ---------------------------------------------------------
    # 3. AUDUSD TARGETED SIGNALS
    # ---------------------------------------------------------
    if s == "AUDUSD":
        # Sydney / Asian Session momentum & fades
        for sd, (u_arr, l_arr) in [(1.5, (ev.bb15_up, ev.bb15_low)), (2.0, (ev.bb_upper, ev.bb_lower))]:
            sd_tag = str(sd).replace(".", "")

            def make_aud_bb(u, l):
                def fn(i):
                    if is_asian(i) or is_sydney(i):
                        if ev.lows[i] <= l[i] and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.highs[i] >= u[i] and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"aud_asian_bb_{sd_tag}_fade"] = make_aud_bb(u_arr, l_arr)

        for ep in [9, 15, 21, 34]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_aud_ema(ea):
                    def fn(i):
                        if is_sydney(i) or is_tokyo(i):
                            if ev.closes[i] > ea[i] and ev.lows[i] <= ea[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ev.closes[i] < ea[i] and ev.highs[i] >= ea[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"aud_ses_ema{ep}_bounce"] = make_aud_ema(earr)

        # London Open Breakouts
        for dp in [4, 6, 8, 10]:

            def make_aud_lon_dch(p):
                def fn(i):
                    if is_london_open(i) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.closes[i] > dh and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ev.closes[i] < dl and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"aud_lon_dch{dp}_break"] = make_aud_lon_dch(dp)

        # Tokyo Drift
        def aud_tokyo(i):
            if is_tokyo(i):
                if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
            return None

        sigs["aud_tokyo_drift"] = aud_tokyo

        # Asian Stochastics
        for sp in [5, 8, 10]:
            ka = getattr(ev, f"stoch{sp}_k" if sp != 14 else "stoch_k", None)
            da = getattr(ev, f"stoch{sp}_d" if sp != 14 else "stoch_d", None)
            if ka is not None:

                def make_aud_stoch(k, d):
                    def fn(i):
                        if is_asian(i):
                            if k[i - 1] <= 25 and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif k[i - 1] >= 75 and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"aud_asian_stoch{sp}_cross"] = make_aud_stoch(ka, da)

        # 2-bar and 4-bar exhaustion fades
        for nb in [2, 4]:

            def make_aud_consec(n):
                mult = 0.42 * n

                def fn(i):
                    if i >= n:
                        tot = ev.closes[i] - ev.opens[i - n + 1]
                        if tot <= -mult * ev.atr14[i] and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif tot >= mult * ev.atr14[i] and ev.closes[i] < ev.opens[i]:
                            return "sell"
                    return None

                return fn

            sigs[f"aud_consec_{nb}bar_fade"] = make_aud_consec(nb)

        # Asian / Sydney Range Fades with variable lookbacks
        for lb in [3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16]:

            def make_aud_asia_w_fade(w):
                def fn(i):
                    if (is_asian(i) or is_sydney(i)) and i >= w:
                        ah = np.max(ev.highs[i - w : i])
                        al = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= ah * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= al * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"aud_asian_range_w{lb}_fade"] = make_aud_asia_w_fade(lb)

        # London Lunch Range Fades for AUDUSD
        for lb in [4, 6, 8, 10]:

            def make_aud_lunch_fade(w):
                def fn(i):
                    if is_london_lunch(i) and i >= w:
                        lh = np.max(ev.highs[i - w : i])
                        ll = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= lh * 0.9995 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= ll * 1.0005 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"aud_lunch_range_w{lb}_fade"] = make_aud_lunch_fade(lb)

        # Tokyo Range Fades with variable lookbacks
        for tw in [3, 4, 5, 6, 7, 8]:

            def make_aud_tokyo_fade(w):
                def fn(i):
                    if ev.hours[i] in (1, 2, 3, 4, 5) and i >= w:
                        rh = np.max(ev.highs[i - w : i])
                        rl = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= rh and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 53:
                            return "sell"
                        elif ev.lows[i] <= rl and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 47:
                            return "buy"
                    return None

                return fn

            sigs[f"aud_tokyo_w{tw}_fade"] = make_aud_tokyo_fade(tw)

        # Tokyo EMA Bounces for AUDUSD
        for ep in [20, 25, 34, 40, 60]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_aud_tokyo_ema(ea):
                    def fn(i):
                        if ev.hours[i] in (0, 1, 2, 3, 4, 5):
                            if ev.closes[i] > ea[i] and ev.lows[i] <= ea[i] and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ev.closes[i] < ea[i] and ev.highs[i] >= ea[i] and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"aud_tokyo_ema{ep}_bounce"] = make_aud_tokyo_ema(earr)

        # Sydney Range Fades with variable lookbacks
        for sw in [3, 4, 5, 6, 8]:

            def make_aud_syd_fade(w):
                def fn(i):
                    if ev.hours[i] in (21, 22, 23, 0, 1) and i >= w:
                        rh = np.max(ev.highs[i - w : i])
                        rl = np.min(ev.lows[i - w : i])
                        if ev.highs[i] >= rh and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 53:
                            return "sell"
                        elif ev.lows[i] <= rl and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 47:
                            return "buy"
                    return None

                return fn

            sigs[f"aud_sydney_w{sw}_fade"] = make_aud_syd_fade(sw)

        # AUDUSD Asian Session RSI Dips
        for rp, (lt, ht) in [(7, (28, 72)), (10, (32, 68)), (12, (34, 66))]:
            rarr = getattr(ev, f"rsi{rp}", None)
            if rarr is not None:

                def make_aud_rsi(ra, l_th, h_th):
                    def fn(i):
                        if is_asian(i) or is_sydney(i):
                            if ra[i] <= l_th and ev.closes[i] > ev.opens[i]:
                                return "buy"
                            elif ra[i] >= h_th and ev.closes[i] < ev.opens[i]:
                                return "sell"
                        return None

                    return fn

                sigs[f"aud_asian_rsi{rp}_dip"] = make_aud_rsi(rarr, lt, ht)

        # AUDUSD Asian Donchian Fades
        for dp in [4, 6, 8, 10]:

            def make_aud_asia_dch(p):
                def fn(i):
                    if (is_asian(i) or is_sydney(i)) and i >= p:
                        dh = np.max(ev.highs[i - p : i])
                        dl = np.min(ev.lows[i - p : i])
                        if ev.highs[i] >= dh and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        elif ev.lows[i] <= dl and ev.closes[i] > ev.opens[i]:
                            return "buy"
                    return None

                return fn

            sigs[f"aud_asian_dch{dp}_fade"] = make_aud_asia_dch(dp)

    # ---------------------------------------------------------
    # 4. BTCUSD TARGETED SIGNALS
    # ---------------------------------------------------------
    if s == "BTCUSD":
        # 24/7 Multi-period Donchian breakouts
        for dp in [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 22, 28, 36]:

            def make_btc_dch(p):
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

            sigs[f"btc_donchian_{dp}_break"] = make_btc_dch(dp)

        # 24/7 EMA trend bounces
        for ep in [8, 9, 13, 15, 20, 21, 25, 34, 50, 80]:
            earr = getattr(ev, f"ema{ep}", None)
            if earr is not None:

                def make_btc_ema(ea):
                    def fn(i):
                        if (
                            ev.closes[i] > ev.ema50[i]
                            and ev.lows[i] <= ea[i]
                            and ev.closes[i] > ea[i]
                            and ev.closes[i] > ev.opens[i]
                        ):
                            return "buy"
                        elif (
                            ev.closes[i] < ev.ema50[i]
                            and ev.highs[i] >= ea[i]
                            and ev.closes[i] < ea[i]
                            and ev.closes[i] < ev.opens[i]
                        ):
                            return "sell"
                        return None

                    return fn

                sigs[f"btc_ema{ep}_trend_bounce"] = make_btc_ema(earr)

        # Fast RSI momentum
        for rp in [5, 7, 9, 10]:
            rarr = getattr(ev, f"rsi{rp}", None)
            if rarr is not None:

                def make_btc_rsi(ra):
                    def fn(i):
                        if ra[i] <= 22 and ev.closes[i] > ev.opens[i]:
                            return "buy"
                        elif ra[i] >= 78 and ev.closes[i] < ev.opens[i]:
                            return "sell"
                        return None

                    return fn

                sigs[f"btc_rsi{rp}_extreme"] = make_btc_rsi(rarr)

        # Weekend momentum surge (days 5 = Saturday, 6 = Sunday)
        def btc_weekend_surge(i):
            if ev.days[i] in (5, 6):
                if ev.closes[i] > ev.ema20[i] and ev.closes[i] > ev.opens[i] and ev.rsi14[i] >= 52:
                    return "buy"
                elif ev.closes[i] < ev.ema20[i] and ev.closes[i] < ev.opens[i] and ev.rsi14[i] <= 48:
                    return "sell"
            return None

        sigs["btc_weekend_momentum"] = btc_weekend_surge

    return sigs
