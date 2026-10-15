# ==============================================================================
# File: scripts/empirical_alpha/evaluator.py
# High-speed precomputed indicator engine and vectorized trade simulator
# ==============================================================================

import math
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

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


def calculate_bollinger_bands(
    closes: np.ndarray, period: int = 20, num_std: float = 2.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mid = calculate_sma(closes, period)
    upper = np.zeros(len(closes))
    lower = np.zeros(len(closes))
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        std = float(np.std(window))
        upper[i] = mid[i] + num_std * std
        lower[i] = mid[i] - num_std * std
    upper[: period - 1] = closes[: period - 1]
    lower[: period - 1] = closes[: period - 1]
    return upper, mid, lower


def calculate_keltner_channels(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 20, atr_mult: float = 1.5
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mid = calculate_ema(closes, period)
    atr = calculate_atr(highs, lows, closes, period)
    upper = mid + atr_mult * atr
    lower = mid - atr_mult * atr
    return upper, mid, lower


def calculate_vwap(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    datetimes: pd.DatetimeIndex,
) -> np.ndarray:
    n = len(closes)
    typical_price = (highs + lows + closes) / 3.0
    vwap = np.zeros(n)
    cum_pv = 0.0
    cum_vol = 0.0
    current_day = -1
    for i in range(n):
        day = datetimes[i].day
        if day != current_day:
            cum_pv = 0.0
            cum_vol = 0.0
            current_day = day
        vol = max(1.0, volumes[i])
        cum_pv += typical_price[i] * vol
        cum_vol += vol
        vwap[i] = cum_pv / cum_vol if cum_vol > 0 else closes[i]
    return vwap


def calculate_macd(
    closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calculate_stochastic(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, k_period: int = 14, d_period: int = 3
) -> Tuple[np.ndarray, np.ndarray]:
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


class EmpiricalEvaluator:
    """Precomputes indicators across multiple time horizons and executes zero-lookahead backtests."""

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
        self.days = self.datetimes.dayofweek

        # Volatility & ATR
        self.atr14 = calculate_atr(self.highs, self.lows, self.closes, 14)
        self.atr20 = calculate_atr(self.highs, self.lows, self.closes, 20)

        # EMAs
        self.ema5 = calculate_ema(self.closes, 5)
        self.ema8 = calculate_ema(self.closes, 8)
        self.ema9 = calculate_ema(self.closes, 9)
        self.ema10 = calculate_ema(self.closes, 10)
        self.ema13 = calculate_ema(self.closes, 13)
        self.ema15 = calculate_ema(self.closes, 15)
        self.ema20 = calculate_ema(self.closes, 20)
        self.ema21 = calculate_ema(self.closes, 21)
        self.ema25 = calculate_ema(self.closes, 25)
        self.ema34 = calculate_ema(self.closes, 34)
        self.ema40 = calculate_ema(self.closes, 40)
        self.ema50 = calculate_ema(self.closes, 50)
        self.ema55 = calculate_ema(self.closes, 55)
        self.ema60 = calculate_ema(self.closes, 60)
        self.ema80 = calculate_ema(self.closes, 80)
        self.ema100 = calculate_ema(self.closes, 100)
        self.ema120 = calculate_ema(self.closes, 120)
        self.ema200 = calculate_ema(self.closes, 200)

        # SMAs
        self.sma20 = calculate_sma(self.closes, 20)
        self.sma50 = calculate_sma(self.closes, 50)
        self.sma200 = calculate_sma(self.closes, 200)
        self.vol_ma20 = calculate_sma(self.volumes, 20)

        # RSIs
        self.rsi5 = calculate_rsi(self.closes, 5)
        self.rsi7 = calculate_rsi(self.closes, 7)
        self.rsi9 = calculate_rsi(self.closes, 9)
        self.rsi10 = calculate_rsi(self.closes, 10)
        self.rsi12 = calculate_rsi(self.closes, 12)
        self.rsi14 = calculate_rsi(self.closes, 14)
        self.rsi18 = calculate_rsi(self.closes, 18)
        self.rsi21 = calculate_rsi(self.closes, 21)

        # Stochastics
        self.stoch5_k, self.stoch5_d = calculate_stochastic(self.highs, self.lows, self.closes, 5, 3)
        self.stoch8_k, self.stoch8_d = calculate_stochastic(self.highs, self.lows, self.closes, 8, 3)
        self.stoch10_k, self.stoch10_d = calculate_stochastic(self.highs, self.lows, self.closes, 10, 3)
        self.stoch_k, self.stoch_d = calculate_stochastic(self.highs, self.lows, self.closes, 14, 3)
        self.stoch21_k, self.stoch21_d = calculate_stochastic(self.highs, self.lows, self.closes, 21, 5)

        # Bollinger Bands
        self.bb14_up, _, self.bb14_low = calculate_bollinger_bands(self.closes, 14, 2.0)
        self.bb15_up, _, self.bb15_low = calculate_bollinger_bands(self.closes, 20, 1.5)
        self.bb_upper, self.bb_mid, self.bb_lower = calculate_bollinger_bands(self.closes, 20, 2.0)
        self.bb25_up, _, self.bb25_low = calculate_bollinger_bands(self.closes, 20, 2.5)
        self.bb28_up, _, self.bb28_low = calculate_bollinger_bands(self.closes, 28, 2.0)

        # Keltner & VWAP & MACD
        self.kelt_upper, self.kelt_mid, self.kelt_lower = calculate_keltner_channels(
            self.highs, self.lows, self.closes, 20, 1.5
        )
        self.vwap = calculate_vwap(self.highs, self.lows, self.closes, self.volumes, self.datetimes)
        self.macd_line, self.macd_sig, self.macd_hist = calculate_macd(self.closes, 12, 26, 9)

        # HTF Resampled EMA (H4 ~ 4 bars)
        self.h4_ema50 = calculate_ema(self.closes, 50 * 4)
        self.h4_ema200 = calculate_ema(self.closes, 200 * 4)

        # Rolling Swings
        for p in (4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 18, 20, 24, 25, 30, 36, 48, 60):
            sh = np.zeros(self.n)
            sl = np.zeros(self.n)
            for i in range(p + 2, self.n):
                sh[i] = np.max(self.highs[i - p : i - 1])
                sl[i] = np.min(self.lows[i - p : i - 1])
            setattr(self, f"swing_high{p}", sh)
            setattr(self, f"swing_low{p}", sl)

        # Donchian Channels
        for p in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 20, 22, 24, 28, 36):
            dh = np.zeros(self.n)
            dl = np.zeros(self.n)
            for i in range(p, self.n):
                dh[i] = np.max(self.highs[i - p : i])
                dl[i] = np.min(self.lows[i - p : i])
            setattr(self, f"donch{p}_high", dh)
            setattr(self, f"donch{p}_low", dl)

        self.donch_upper = self.donch24_high
        self.donch_lower = self.donch24_low

        # Friction profile
        self.pip_size = get_pip_size(self.symbol)
        f_info = ASSET_FRICTION_PROFILE.get(self.symbol, {"spread_pips": 1.5, "slippage_pips": 0.5})
        self.spread_cost = f_info.get("spread_pips", 1.5) * self.pip_size
        self.slippage_cost = f_info.get("slippage_pips", 0.5) * self.pip_size

    def fast_simulate(
        self, raw_signals: List[Optional[str]], sl_mult: float, tp_mult: float, max_hold: int
    ) -> Dict[str, Any]:
        """Ultra-fast trade simulator over precomputed raw signals."""
        trade_returns = []
        trades = []
        i = 60
        n = self.n
        opens = self.opens
        highs = self.highs
        lows = self.lows
        closes = self.closes
        atr14 = self.atr14
        pip_size = self.pip_size
        spread_cost = self.spread_cost
        slippage_cost = self.slippage_cost

        while i < n - 5:
            direction = raw_signals[i]
            if direction is None:
                i += 1
                continue

            fill_bar = i + 1
            if fill_bar >= n:
                break

            base_open = opens[fill_bar]
            atr = max(atr14[i], pip_size * 5.0)
            sl_dist = sl_mult * atr
            tp_dist = tp_mult * atr

            if direction == "buy":
                entry_price = base_open + (spread_cost / 2.0) + slippage_cost
                sl = entry_price - sl_dist
                tp = entry_price + tp_dist
            else:
                entry_price = base_open - (spread_cost / 2.0) - slippage_cost
                sl = entry_price + sl_dist
                tp = entry_price - tp_dist

            exit_price = entry_price
            bars_held = 0
            max_eval = min(fill_bar + max_hold, n)

            for f in range(fill_bar, max_eval):
                bars_held += 1
                f_open = opens[f]
                f_high = highs[f]
                f_low = lows[f]

                if direction == "buy":
                    if f_open <= sl:
                        exit_price = f_open - slippage_cost
                        break
                    if f_low <= sl and f_high >= tp:
                        exit_price = sl - slippage_cost
                        break
                    elif f_low <= sl:
                        exit_price = sl - slippage_cost
                        break
                    elif f_high >= tp:
                        exit_price = tp
                        break
                else:
                    if f_open >= sl:
                        exit_price = f_open + slippage_cost
                        break
                    if f_high >= sl and f_low <= tp:
                        exit_price = sl + slippage_cost
                        break
                    elif f_high >= sl:
                        exit_price = sl + slippage_cost
                        break
                    elif f_low <= tp:
                        exit_price = tp
                        break
            else:
                exit_price = closes[max_eval - 1]

            price_diff = (exit_price - entry_price) if direction == "buy" else (entry_price - exit_price)
            risk_dist = abs(entry_price - sl)
            r_mult = price_diff / risk_dist if risk_dist > 1e-7 else 0.0
            trade_returns.append(r_mult * 0.01)
            trades.append({"direction": direction, "r_mult": r_mult, "bars_held": bars_held})
            i = fill_bar + max(1, bars_held)

        return self._compute_metrics(trade_returns, trades)

    def _compute_metrics(self, trade_returns: List[float], trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not trade_returns:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "total_pnl_pct": 0.0,
                "trades": [],
            }

        wins = [r for r in trade_returns if r > 0]
        losses = [r for r in trade_returns if r < 0]
        win_rate = (len(wins) / len(trade_returns)) * 100.0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 1e-7 else (3.0 if gross_profit > 0 else 0.0)

        # Cumulative equity curve & Max Drawdown
        cum_ret = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in trade_returns:
            cum_ret *= 1.0 + r
            if cum_ret > peak:
                peak = cum_ret
            dd = (peak - cum_ret) / peak
            if dd > max_dd:
                max_dd = dd

        total_pnl_pct = round((cum_ret - 1.0) * 100.0, 1)
        max_drawdown_pct = round(max_dd * 100.0, 1)

        # Sharpe Ratio (annualized for H1 ~ 6000 bars/year)
        arr = np.array(trade_returns)
        mean_r = np.mean(arr)
        std_r = np.std(arr)
        sharpe = round(float((mean_r / std_r) * math.sqrt(252 * 24)), 2) if std_r > 1e-7 else 0.0

        return {
            "total_trades": len(trade_returns),
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_drawdown_pct,
            "total_pnl_pct": total_pnl_pct,
            "trades": trades,
        }
