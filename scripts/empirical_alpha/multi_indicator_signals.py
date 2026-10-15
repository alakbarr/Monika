import numpy as np


def get_mega_signal_pool(ev, sym: str):
    sigs = {}

    # Add 50 more modular alpha triggers
    # 1. EMA 5, 10, 15, 25, 40, 60 bounces
    for ep in [5, 10, 15, 25, 40, 60]:
        arr = getattr(ev, f"ema{ep}")

        def make_m_ema_b(a, p):
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

        sigs[f"mega_ema{ep}_bounce"] = make_m_ema_b(arr, ep)

    # 2. RSI 5, 10, 12, 18 extremes
    for rp, (low, high) in [(5, (15, 85)), (5, (20, 80)), (10, (25, 75)), (12, (30, 70)), (18, (35, 65))]:
        rarr = getattr(ev, f"rsi{rp}")

        def make_m_rsi(a, l, h):
            def fn(i):
                if a[i] <= l and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif a[i] >= h and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"mega_rsi{rp}_{low}_{high}"] = make_m_rsi(rarr, low, high)

    # 3. Fast Stochastic 5 & 10 crosses
    for sp, lvl in [(5, 15), (5, 20), (10, 20), (10, 25)]:
        ka = getattr(ev, f"stoch{sp}_k")
        da = getattr(ev, f"stoch{sp}_d")

        def make_m_stoch(k, d, l):
            def fn(i):
                if k[i - 1] <= l and k[i] > d[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                elif k[i - 1] >= (100 - l) and k[i] < d[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                return None

            return fn

        sigs[f"mega_stoch{sp}_{lvl}_cross"] = make_m_stoch(ka, da, lvl)

    # 4. Donchian 6, 14, 18, 28 breakouts
    for dp in [6, 14, 18, 28]:

        def make_m_donch(p):
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

        sigs[f"mega_donchian_{dp}_break"] = make_m_donch(dp)

    # 5. Fast/Slow BB 14 & 28 fades
    def bb14_fade(i):
        if ev.lows[i] <= ev.bb14_low[i] and ev.closes[i] > ev.bb14_low[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.highs[i] >= ev.bb14_up[i] and ev.closes[i] < ev.bb14_up[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["mega_bb14_reversion"] = bb14_fade

    def bb28_fade(i):
        if ev.lows[i] <= ev.bb28_low[i] and ev.closes[i] > ev.bb28_low[i] and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.highs[i] >= ev.bb28_up[i] and ev.closes[i] < ev.bb28_up[i] and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["mega_bb28_reversion"] = bb28_fade

    # 6. Swing 6, 18, 30 Pinbars
    for sp in [6, 18, 30]:
        h_arr = getattr(ev, f"swing_high{sp}")
        l_arr = getattr(ev, f"swing_low{sp}")

        def make_sw_pin(ha, la):
            def fn(i):
                rng = max(1e-7, ev.highs[i] - ev.lows[i])
                if rng >= 0.55 * ev.atr14[i]:
                    lw = min(ev.opens[i], ev.closes[i]) - ev.lows[i]
                    uw = ev.highs[i] - max(ev.opens[i], ev.closes[i])
                    if lw / rng >= 0.48 and ev.lows[i] <= la[i] and ev.closes[i] > ev.opens[i]:
                        return "buy"
                    elif uw / rng >= 0.48 and ev.highs[i] >= ha[i] and ev.closes[i] < ev.opens[i]:
                        return "sell"
                return None

            return fn

        sigs[f"mega_pinbar_swing{sp}"] = make_sw_pin(h_arr, l_arr)

    # 7. Swing 6, 18, 30 Sweep & Re-entries
    for sp in [6, 18, 30]:
        h_arr = getattr(ev, f"swing_high{sp}")
        l_arr = getattr(ev, f"swing_low{sp}")

        def make_sw_sweep(ha, la):
            def fn(i):
                if ev.highs[i] >= ha[i] and ev.closes[i] < ha[i] and ev.closes[i] < ev.opens[i]:
                    return "sell"
                elif ev.lows[i] <= la[i] and ev.closes[i] > la[i] and ev.closes[i] > ev.opens[i]:
                    return "buy"
                return None

            return fn

        sigs[f"mega_sweep_swing{sp}"] = make_sw_sweep(h_arr, l_arr)

    return sigs
