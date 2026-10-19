"""
High-Precision M15 Empirical Strategy Engine for Monika Playbooks.
Tests institutional setups across 15,000 M15 bars directly from active MT5 terminal.
Strict Gating:
- Profit Factor >= 1.25
- Total PnL >= +15.0%
- Win Rate >= 40.0%
- Max Drawdown <= 15.0%
- Total Trades >= 15
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from monika.application.backtest.outcome_evaluator import ASSET_FRICTION_PROFILE


def get_pip_size(symbol: str) -> float:
    sym = symbol.upper()
    if any(c in sym for c in ("JPY", "XAU", "XTI", "XBR")):
        return 0.01
    elif any(c in sym for c in ("BTC", "ETH", "SOL")):
        return 1.0
    else:
        return 0.0001


def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    atr = np.zeros(n)
    if n < 2:
        return atr
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    if n < period:
        atr[:] = np.mean(tr)
        return atr
    atr[period - 1] = np.mean(tr[:period])
    alpha = 1.0 / period
    for i in range(period, n):
        atr[i] = alpha * tr[i] + (1.0 - alpha) * atr[i - 1]
    return atr


def calculate_ema(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    ema = np.zeros(n)
    if n < period:
        ema[:] = data
        return ema
    ema[period - 1] = np.mean(data[:period])
    alpha = 2.0 / (period + 1.0)
    for i in range(period, n):
        ema[i] = alpha * data[i] + (1.0 - alpha) * ema[i - 1]
    return ema


def calculate_sma(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    sma = np.zeros(n)
    if n < period:
        sma[:] = data
        return sma
    csum = np.cumsum(np.insert(data, 0, 0))
    sma[period - 1 :] = (csum[period:] - csum[:-period]) / float(period)
    sma[: period - 1] = data[: period - 1]
    return sma


def calculate_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(closes)
    rsi = np.full(n, 50.0)
    if n <= period:
        return rsi
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, n):
        d_idx = i - 1
        avg_gain = (avg_gain * (period - 1) + gains[d_idx]) / period
        avg_loss = (avg_loss * (period - 1) + losses[d_idx]) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calculate_bollinger_bands(closes: np.ndarray, period: int = 20, num_std: float = 2.0):
    mid = calculate_sma(closes, period)
    upper = np.zeros(len(closes))
    lower = np.zeros(len(closes))
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        std = np.std(window)
        upper[i] = mid[i] + num_std * std
        lower[i] = mid[i] - num_std * std
    upper[: period - 1] = closes[: period - 1]
    lower[: period - 1] = closes[: period - 1]
    return upper, mid, lower


def calculate_keltner_channels(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 20, atr_mult: float = 1.5
):
    mid = calculate_ema(closes, period)
    atr = calculate_atr(highs, lows, closes, period)
    return mid + atr_mult * atr, mid, mid - atr_mult * atr


def calculate_vwap(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray, datetimes: pd.DatetimeIndex
) -> np.ndarray:
    n = len(closes)
    vwap = np.zeros(n)
    cum_vol = 0.0
    cum_pv = 0.0
    current_day = None
    for i in range(n):
        day = datetimes[i].date()
        if day != current_day:
            current_day = day
            cum_vol = 0.0
            cum_pv = 0.0
        typical_price = (highs[i] + lows[i] + closes[i]) / 3.0
        v = max(1.0, volumes[i])
        cum_vol += v
        cum_pv += typical_price * v
        vwap[i] = cum_pv / cum_vol
    return vwap


def calculate_macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calculate_stochastic(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, k_period: int = 14, d_period: int = 3
):
    n = len(closes)
    k_line = np.full(n, 50.0)
    for i in range(k_period - 1, n):
        highest_high = np.max(highs[i - k_period + 1 : i + 1])
        lowest_low = np.min(lows[i - k_period + 1 : i + 1])
        rng = highest_high - lowest_low
        if rng > 1e-7:
            k_line[i] = ((closes[i] - lowest_low) / rng) * 100.0
        else:
            k_line[i] = 50.0
    d_line = calculate_sma(k_line, d_period)
    return k_line, d_line


class M15Evaluator:
    def __init__(self, symbol: str, df: pd.DataFrame):
        self.symbol = symbol.upper()
        self.df = df
        self.n = len(df)
        self.closes = df["close"].values
        self.highs = df["high"].values
        self.lows = df["low"].values
        self.opens = df["open"].values
        self.volumes = df["tick_volume"].values.astype(float)
        self.datetimes = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s", utc=True))
        self.hours = self.datetimes.hour
        self.minutes = self.datetimes.minute

        # M15 Indicators
        self.atr14 = calculate_atr(self.highs, self.lows, self.closes, 14)
        self.ema9 = calculate_ema(self.closes, 9)
        self.ema20 = calculate_ema(self.closes, 20)
        self.ema21 = calculate_ema(self.closes, 21)
        self.ema50 = calculate_ema(self.closes, 50)
        self.ema200 = calculate_ema(self.closes, 200)
        self.vol_ma20 = calculate_sma(self.volumes, 20)
        self.rsi14 = calculate_rsi(self.closes, 14)
        self.bb_upper, self.bb_mid, self.bb_lower = calculate_bollinger_bands(self.closes, 20, 2.0)
        self.kelt_upper, self.kelt_mid, self.kelt_lower = calculate_keltner_channels(
            self.highs, self.lows, self.closes, 20, 1.5
        )
        self.vwap = calculate_vwap(self.highs, self.lows, self.closes, self.volumes, self.datetimes)
        self.macd_line, self.macd_sig, self.macd_hist = calculate_macd(self.closes, 12, 26, 9)
        self.stoch_k, self.stoch_d = calculate_stochastic(self.highs, self.lows, self.closes, 14, 3)

        # Higher Timeframe Resampled (H1 equivalent ~ 4 M15 bars, H4 equivalent ~ 16 M15 bars)
        self.h1_ema50 = calculate_ema(self.closes, 50 * 4)
        self.h1_ema200 = calculate_ema(self.closes, 200 * 4)
        self.h4_ema50 = calculate_ema(self.closes, 50 * 16)

        # Rolling 24-hour Swing (96 bars on M15)
        self.swing_high96 = np.zeros(self.n)
        self.swing_low96 = np.zeros(self.n)
        for i in range(100, self.n):
            self.swing_high96[i] = np.max(self.highs[i - 96 : i - 2])
            self.swing_low96[i] = np.min(self.lows[i - 96 : i - 2])

        # Rolling 6-hour Swing (24 bars on M15)
        self.swing_high24 = np.zeros(self.n)
        self.swing_low24 = np.zeros(self.n)
        for i in range(26, self.n):
            self.swing_high24[i] = np.max(self.highs[i - 24 : i - 2])
            self.swing_low24[i] = np.min(self.lows[i - 24 : i - 2])

        # Donchian 48 (12 hours)
        self.donch_upper = np.zeros(self.n)
        self.donch_lower = np.zeros(self.n)
        for i in range(48, self.n):
            self.donch_upper[i] = np.max(self.highs[i - 48 : i])
            self.donch_lower[i] = np.min(self.lows[i - 48 : i])

        # Friction profile
        self.pip_size = get_pip_size(self.symbol)
        f_info = ASSET_FRICTION_PROFILE.get(self.symbol, {"spread_pips": 1.5, "slippage_pips": 0.5})
        self.spread_cost = f_info.get("spread_pips", 1.5) * self.pip_size
        self.slippage_cost = f_info.get("slippage_pips", 0.5) * self.pip_size

    def simulate_signals(self, signal_fn, sl_mult: float, tp_mult: float, max_hold: int) -> dict:
        trade_returns = []
        trades = []
        i = 100
        while i < self.n - 5:
            direction = signal_fn(i)
            if not direction:
                i += 1
                continue

            fill_bar = i + 1
            if fill_bar >= self.n:
                break

            base_open = self.opens[fill_bar]
            atr = max(self.atr14[i], self.pip_size * 5.0)
            sl_dist = sl_mult * atr
            tp_dist = tp_mult * atr

            if direction == "buy":
                entry_price = base_open + (self.spread_cost / 2.0) + self.slippage_cost
                sl = entry_price - sl_dist
                tp = entry_price + tp_dist
            else:
                entry_price = base_open - (self.spread_cost / 2.0) - self.slippage_cost
                sl = entry_price + sl_dist
                tp = entry_price - tp_dist

            exit_price = entry_price
            exit_reason = "time_exit"
            bars_held = 0

            max_eval = min(fill_bar + max_hold, self.n)
            for f in range(fill_bar, max_eval):
                bars_held += 1
                f_open = self.opens[f]
                f_high = self.highs[f]
                f_low = self.lows[f]

                if direction == "buy":
                    if f_open <= sl:
                        exit_price = f_open - self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    if f_low <= sl and f_high >= tp:
                        exit_price = sl - self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    elif f_low <= sl:
                        exit_price = sl - self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    elif f_high >= tp:
                        exit_price = tp
                        exit_reason = "take_profit"
                        break
                else:  # sell
                    if f_open >= sl:
                        exit_price = f_open + self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    if f_high >= sl and f_low <= tp:
                        exit_price = sl + self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    elif f_high >= sl:
                        exit_price = sl + self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    elif f_low <= tp:
                        exit_price = tp
                        exit_reason = "take_profit"
                        break
            else:
                exit_price = self.closes[max_eval - 1]
                exit_reason = "time_exit"

            price_diff = (exit_price - entry_price) if direction == "buy" else (entry_price - exit_price)
            risk_dist = abs(entry_price - sl)
            r_mult = price_diff / risk_dist if risk_dist > 1e-7 else 0.0
            trade_returns.append(r_mult * 0.01)

            trades.append(
                {
                    "direction": direction,
                    "r_mult": r_mult,
                    "bars_held": bars_held,
                    "exit_reason": exit_reason,
                }
            )
            i = fill_bar + max(1, bars_held)

        return self._compute_metrics(trade_returns, trades)

    def _compute_metrics(self, returns: list, trades: list) -> dict:
        if not returns:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "total_pnl_pct": 0.0,
            }

        total_trades = len(returns)
        wins = [r for r in returns if r > 0.0]
        losses = [r for r in returns if r < 0.0]
        win_rate_pct = round((len(wins) / total_trades) * 100.0, 1)

        sum_wins = sum(wins)
        sum_losses = abs(sum(losses))
        profit_factor = round(sum_wins / sum_losses, 2) if sum_losses > 1e-9 else (10.0 if sum_wins > 0 else 0.0)

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1)) if len(returns) > 1 else 1e-6
        avg_bars = np.mean([t["bars_held"] for t in trades]) if trades else 1.0
        ann_factor = math.sqrt(252.0 * 24.0 * 4.0 / max(1.0, avg_bars))
        sharpe_ratio = round(float((mean_ret / (std_ret + 1e-9)) * ann_factor), 2)

        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in returns:
            equity *= 1.0 + r
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        total_pnl_pct = round((equity - 1.0) * 100.0, 2)
        return {
            "total_trades": total_trades,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown_pct": round(max_dd, 2),
            "total_pnl_pct": total_pnl_pct,
        }


def get_m15_signals(ev: M15Evaluator):
    sigs = {}

    # 1. London Open Expansion (07:00-09:00 UTC)
    def sig_london_expansion(i):
        if ev.hours[i] in (7, 8):
            rh = np.max(ev.highs[max(0, i - 16) : i])
            rl = np.min(ev.lows[max(0, i - 16) : i])
            if ev.closes[i] > rh and ev.closes[i] > ev.ema50[i]:
                return "buy"
            elif ev.closes[i] < rl and ev.closes[i] < ev.ema50[i]:
                return "sell"
        return None

    sigs["london_expansion"] = sig_london_expansion

    # 2. Asian Box Breakout (07:00-08:30 UTC)
    def sig_asian_breakout(i):
        if ev.hours[i] in (7, 8):
            ah = np.max(ev.highs[max(0, i - 28) : i])
            al = np.min(ev.lows[max(0, i - 28) : i])
            if ev.closes[i] > ah and ev.closes[i] > ev.h1_ema50[i]:
                return "buy"
            elif ev.closes[i] < al and ev.closes[i] < ev.h1_ema50[i]:
                return "sell"
        return None

    sigs["asian_breakout"] = sig_asian_breakout

    # 3. NY Opening Reversal (13:00-15:30 UTC)
    def sig_ny_reversal(i):
        if ev.hours[i] in (13, 14, 15):
            lh = np.max(ev.highs[max(0, i - 24) : i])
            ll = np.min(ev.lows[max(0, i - 24) : i])
            if ev.highs[i] >= lh and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 58:
                return "sell"
            elif ev.lows[i] <= ll and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 42:
                return "buy"
        return None

    sigs["ny_reversal"] = sig_ny_reversal

    # 4. Asian Range Fade (00:00-05:00 UTC)
    def sig_asian_fade(i):
        if ev.hours[i] in (0, 1, 2, 3, 4, 5):
            ah = np.max(ev.highs[max(0, i - 20) : i])
            al = np.min(ev.lows[max(0, i - 20) : i])
            if ev.highs[i] >= ah and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.lows[i] <= al and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["asian_fade"] = sig_asian_fade

    # 5. Bollinger Band Mean Reversion
    def sig_bb_reversion(i):
        if (
            ev.lows[i] <= ev.bb_lower[i]
            and ev.closes[i] > ev.bb_lower[i]
            and ev.rsi14[i] <= 40
            and ev.closes[i] > ev.opens[i]
        ):
            return "buy"
        elif (
            ev.highs[i] >= ev.bb_upper[i]
            and ev.closes[i] < ev.bb_upper[i]
            and ev.rsi14[i] >= 60
            and ev.closes[i] < ev.opens[i]
        ):
            return "sell"
        return None

    sigs["bb_reversion"] = sig_bb_reversion

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

    # 7. Donchian Volatility Breakout
    def sig_donchian_breakout(i):
        if ev.closes[i] > ev.donch_upper[i] and ev.closes[i] > ev.ema50[i]:
            return "buy"
        elif ev.closes[i] < ev.donch_lower[i] and ev.closes[i] < ev.ema50[i]:
            return "sell"
        return None

    sigs["donchian_breakout"] = sig_donchian_breakout

    # 8. 24h Liquidity Sweep & Displacement
    def sig_liquidity_sweep(i):
        body = abs(ev.closes[i] - ev.opens[i])
        if (
            ev.lows[i] < ev.swing_low96[i]
            and ev.closes[i] > ev.swing_low96[i]
            and ev.closes[i] > ev.opens[i]
            and body >= 0.5 * ev.atr14[i]
        ):
            return "buy"
        elif (
            ev.highs[i] > ev.swing_high96[i]
            and ev.closes[i] < ev.swing_high96[i]
            and ev.closes[i] < ev.opens[i]
            and body >= 0.5 * ev.atr14[i]
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

    # 10. SMT & RSI Divergence
    def sig_smt_divergence(i):
        if i >= 20:
            price_lower = ev.lows[i] < ev.lows[i - 12]
            rsi_higher = ev.rsi14[i] > ev.rsi14[i - 12] + 3.0
            if price_lower and rsi_higher and ev.closes[i] > ev.opens[i]:
                return "buy"
            price_higher = ev.highs[i] > ev.highs[i - 12]
            rsi_lower = ev.rsi14[i] < ev.rsi14[i - 12] - 3.0
            if price_higher and rsi_lower and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["smt_divergence"] = sig_smt_divergence

    # 11. 9/21 EMA Trend Cross
    def sig_ema9_21_cross(i):
        if i >= 2:
            cross_up = ev.ema9[i - 1] <= ev.ema21[i - 1] and ev.ema9[i] > ev.ema21[i]
            cross_down = ev.ema9[i - 1] >= ev.ema21[i - 1] and ev.ema9[i] < ev.ema21[i]
            if cross_up and ev.closes[i] > ev.h1_ema50[i]:
                return "buy"
            elif cross_down and ev.closes[i] < ev.h1_ema50[i]:
                return "sell"
        return None

    sigs["ema9_21_cross"] = sig_ema9_21_cross

    # 12. Multi-Timeframe H1 Trend & M15 CHoCH
    def sig_mtf_choch(i):
        h1_bull = ev.h1_ema50[i] > ev.h1_ema200[i]
        h1_bear = ev.h1_ema50[i] < ev.h1_ema200[i]
        rh = np.max(ev.highs[max(0, i - 8) : i])
        rl = np.min(ev.lows[max(0, i - 8) : i])
        if h1_bull and ev.closes[i] > rh and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif h1_bear and ev.closes[i] < rl and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["mtf_choch"] = sig_mtf_choch

    # 13. VWAP Stretch Mean Reversion
    def sig_vwap_stretch(i):
        dist = (ev.closes[i] - ev.vwap[i]) / ev.atr14[i]
        if dist <= -1.5 and ev.closes[i] > ev.opens[i] and ev.rsi14[i] <= 38:
            return "buy"
        elif dist >= 1.5 and ev.closes[i] < ev.opens[i] and ev.rsi14[i] >= 62:
            return "sell"
        return None

    sigs["vwap_stretch"] = sig_vwap_stretch

    # 14. Two-Bar Swing Reversal
    def sig_two_bar_reversal(i):
        if i >= 2:
            bp = abs(ev.closes[i - 1] - ev.opens[i - 1])
            bc = abs(ev.closes[i] - ev.opens[i])
            if bp >= 0.6 * ev.atr14[i] and bc >= 0.6 * ev.atr14[i]:
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

    # 15. Institutional Orderblock Mitigation
    def sig_orderblock_mitigation(i):
        if i >= 6:
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

    # 16. London 4PM Fix Reversal (15:00-16:00 UTC)
    def sig_london_fix_reversal(i):
        if ev.hours[i] in (15, 16):
            if ev.rsi14[i] >= 58 and ev.closes[i] < ev.opens[i]:
                return "sell"
            elif ev.rsi14[i] <= 42 and ev.closes[i] > ev.opens[i]:
                return "buy"
        return None

    sigs["london_fix_reversal"] = sig_london_fix_reversal

    # 17. EMA 50 Dynamic Trend Bounce
    def sig_ema50_trend_bounce(i):
        if ev.closes[i] > ev.ema200[i]:
            if ev.lows[i] <= ev.ema50[i] and ev.closes[i] > ev.ema50[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
        elif ev.closes[i] < ev.ema200[i]:
            if ev.highs[i] >= ev.ema50[i] and ev.closes[i] < ev.ema50[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["ema50_trend_bounce"] = sig_ema50_trend_bounce

    # 18. RSI Extreme Reversal
    def sig_rsi_extreme(i):
        if ev.rsi14[i] <= 30 and ev.closes[i] > ev.opens[i]:
            return "buy"
        elif ev.rsi14[i] >= 70 and ev.closes[i] < ev.opens[i]:
            return "sell"
        return None

    sigs["rsi_extreme"] = sig_rsi_extreme

    # 19. Tokyo Fix Trend Continuation (00:00-02:00 UTC)
    def sig_tokyo_fix(i):
        if ev.hours[i] in (0, 1, 2):
            if ev.closes[i] > ev.opens[i] and ev.closes[i] > ev.ema20[i] and ev.rsi14[i] >= 52:
                return "buy"
            elif ev.closes[i] < ev.opens[i] and ev.closes[i] < ev.ema20[i] and ev.rsi14[i] <= 48:
                return "sell"
        return None

    sigs["tokyo_fix"] = sig_tokyo_fix

    # 20. London Lunch Retest & Continuation (11:00-13:00 UTC)
    def sig_london_lunch(i):
        if ev.hours[i] in (11, 12):
            if ev.ema20[i] > ev.ema50[i] and ev.lows[i] <= ev.ema20[i] and ev.closes[i] > ev.opens[i]:
                return "buy"
            elif ev.ema20[i] < ev.ema50[i] and ev.highs[i] >= ev.ema20[i] and ev.closes[i] < ev.opens[i]:
                return "sell"
        return None

    sigs["london_lunch"] = sig_london_lunch

    return sigs


def test_symbols():
    if not mt5.initialize():
        print("MT5 Failed")
        return

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
    param_grid = [
        {"sl": 1.0, "tp": 1.8, "hold": 16},
        {"sl": 1.0, "tp": 2.0, "hold": 20},
        {"sl": 1.2, "tp": 2.2, "hold": 24},
        {"sl": 1.2, "tp": 2.4, "hold": 28},
        {"sl": 1.4, "tp": 2.8, "hold": 32},
        {"sl": 1.5, "tp": 3.0, "hold": 36},
    ]

    for sym in symbols:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 15000)
        df = pd.DataFrame(rates)
        ev = M15Evaluator(sym, df)
        sigs = get_m15_signals(ev)
        strict_passing = []
        for name, fn in sigs.items():
            best_m = None
            best_p = None
            for p in param_grid:
                m = ev.simulate_signals(fn, p["sl"], p["tp"], p["hold"])
                if (
                    m["total_trades"] >= 15
                    and m["profit_factor"] >= 1.25
                    and m["total_pnl_pct"] >= 15.0
                    and m["win_rate_pct"] >= 40.0
                    and m["max_drawdown_pct"] <= 15.0
                ):
                    if best_m is None or m["total_pnl_pct"] > best_m["total_pnl_pct"]:
                        best_m = m
                        best_p = p
            if best_m is not None:
                strict_passing.append((name, best_m, best_p))

        print(f"\n[{sym} M15] Strict Passing: {len(strict_passing)} / {len(sigs)}")
        for name, m, p in strict_passing:
            print(
                f"  {name:25}: PnL=+{m['total_pnl_pct']:5.1f}% | PF={m['profit_factor']:4.2f} | WR={m['win_rate_pct']:4.1f}% | DD={m['max_drawdown_pct']:4.1f}% | N={m['total_trades']:3d}"
            )

    mt5.shutdown()


if __name__ == "__main__":
    test_symbols()
