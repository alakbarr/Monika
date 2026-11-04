# ==============================================================================
# File: indicators/structure.py
# ==============================================================================

"""
Market Structure Pure Domain Calculator: Swing Points, S/R Zones, Liquidity Zones, FVG.

Detects institutional market structure based on Smart Money Concepts (SMC):
1. Swing Points: Multi-bar fractal high/low levels.
2. S/R Zones: Support and resistance clusters derived from swing points.
3. Liquidity Zones: High-timeframe liquidity pools anchored at structural swing extremes.
4. FVG Zones: Fair Value Gaps (3-candle price imbalances).
5. Order Blocks: Institutional order blocks with ATR-relative impulse validation.
6. Structure Breaks: BOS (Break of Structure) and CHoCH (Change of Character) with close confirmation.

Operates purely in-memory on pandas DataFrames and arrays without database dependencies.
For persistence and loading orchestration, see monika.application.services.market_structure_service.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Structure")


def _search_ts(timestamps: list[datetime], target_ts: Any, side: str = "right") -> int:
    """Find index in sorted timestamps list using bisect, ensuring timezone alignment."""
    if not timestamps or target_ts is None:
        return 0
    ref_tz = getattr(timestamps[0], "tzinfo", None)
    t = target_ts.to_pydatetime() if hasattr(target_ts, "to_pydatetime") else target_ts
    t_tz = getattr(t, "tzinfo", None)
    if ref_tz is not None and t_tz is None:
        t = t.replace(tzinfo=timezone.utc)
    elif ref_tz is None and t_tz is not None:
        t = t.replace(tzinfo=None)
    if side == "left":
        return bisect.bisect_left(timestamps, t)
    return bisect.bisect_right(timestamps, t)


@dataclass
class FVGData:
    symbol: str
    timeframe: str
    gap_high: float
    gap_low: float
    direction: str
    formed_at: datetime
    filled_at: Optional[datetime] = None


@dataclass
class OrderBlockData:
    symbol: str
    timeframe: str
    direction: str
    price_high: float
    price_low: float
    formed_at: datetime
    mitigated_at: Optional[datetime] = None
    has_confluent_fvg: bool = False
    confirmed_at: Optional[datetime] = None


@dataclass
class LiquidityZoneData:
    symbol: str
    timeframe: str
    zone_high: float
    zone_low: float
    type: str
    identified_at: datetime


@dataclass
class StructureBreakData:
    symbol: str
    timeframe: str
    type: str
    direction: str
    price: float
    formed_at: datetime


# Batasan jarak maksimal FVG berdasarkan aset
FVG_MAX_DISTANCE: dict[str, float] = {
    "XAUUSD": 0.07,  # 7% — Emas bisa memiliki FVG lebar
    "XTIUSD": 0.10,  # 10% — Minyak lebih volatil
    "XBRUSD": 0.10,  # 10% — Minyak Brent
    "BTCUSD": 0.18,  # 18% — Kripto berfluktuasi tinggi
    "EURUSD": 0.035,  # 3.5% — Forex cenderung ketat
    "GBPUSD": 0.035,
    "USDJPY": 0.035,
    "AUDUSD": 0.030,
}


def get_fvg_max_distance(symbol: str) -> float:
    """Mengembalikan jarak toleransi maksimal FVG berdasarkan kelas aset."""
    clean = symbol.upper().replace(".M", "").replace("/", "")
    if clean in FVG_MAX_DISTANCE:
        return FVG_MAX_DISTANCE[clean]
    if any(k in clean for k in ("BTC", "ETH", "SOL")):
        return 0.18
    if any(k in clean for k in ("XAU", "GOLD")):
        return 0.07
    if any(k in clean for k in ("XTI", "XBR", "OIL", "USOIL", "UKOIL")):
        return 0.10
    if any(k in clean for k in ("US30", "NAS100", "SPX500", "GER40")):
        return 0.05
    return 0.035


# ------------------------------------------------------------------
# Pure Domain Computational Functions
# ------------------------------------------------------------------


def find_swings(df: pd.DataFrame, swing_window: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Detect swing high/low points using a symmetric fractal window (n-candle comparison).

    Returns:
        Tuple of DataFrames (swing_highs, swing_lows) containing [timestamp, price].
    """
    n = max(1, swing_window)
    columns = ["timestamp", "price", "confirmed_at", "confirmation_lag_bars"]
    if len(df) < 2 * n + 1:
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=columns)

    highs_idx: list[dict[str, Any]] = []
    lows_idx: list[dict[str, Any]] = []

    prices_high = np.asarray(df["high"], dtype=float)
    prices_low = np.asarray(df["low"], dtype=float)
    timestamps = list(df.index)
    total_len = len(df)

    # Fast path: Native Rust C-ABI accelerator
    from monika.core.native.rust_bridge import find_swings_f64

    fast_swings = find_swings_f64(prices_high, prices_low, n)
    if fast_swings is not None:
        sh_idx, sl_idx = fast_swings
        highs_idx = [
            {
                "timestamp": timestamps[i],
                "price": float(prices_high[i]),
                "confirmed_at": timestamps[i + n],
                "confirmation_lag_bars": n,
            }
            for i in sh_idx
        ]
        lows_idx = [
            {
                "timestamp": timestamps[i],
                "price": float(prices_low[i]),
                "confirmed_at": timestamps[i + n],
                "confirmation_lag_bars": n,
            }
            for i in sl_idx
        ]
        swing_highs = pd.DataFrame(highs_idx) if highs_idx else pd.DataFrame(columns=columns)
        swing_lows = pd.DataFrame(lows_idx) if lows_idx else pd.DataFrame(columns=columns)
        logger.debug(f"Found {len(swing_highs)} swing highs, {len(swing_lows)} swing lows")
        return swing_highs, swing_lows

    for i in range(n, total_len - n):
        # Task 5.1: Skip inside bars
        prev_high = prices_high[i - 1]
        prev_low = prices_low[i - 1]
        if prices_high[i] <= prev_high and prices_low[i] >= prev_low:
            continue

        h_val = prices_high[i]
        l_val = prices_low[i]

        max_surrounding_h = max(prices_high[i - n : i].max(), prices_high[i + 1 : i + n + 1].max())
        if h_val > max_surrounding_h:
            highs_idx.append(
                {
                    "timestamp": timestamps[i],
                    "price": float(h_val),
                    "confirmed_at": timestamps[i + n],
                    "confirmation_lag_bars": n,
                }
            )

        min_surrounding_l = min(prices_low[i - n : i].min(), prices_low[i + 1 : i + n + 1].min())
        if l_val < min_surrounding_l:
            lows_idx.append(
                {
                    "timestamp": timestamps[i],
                    "price": float(l_val),
                    "confirmed_at": timestamps[i + n],
                    "confirmation_lag_bars": n,
                }
            )

    swing_highs = pd.DataFrame(highs_idx) if highs_idx else pd.DataFrame(columns=columns)
    swing_lows = pd.DataFrame(lows_idx) if lows_idx else pd.DataFrame(columns=columns)

    logger.debug(f"Found {len(swing_highs)} swing highs, {len(swing_lows)} swing lows")
    return swing_highs, swing_lows


def find_sr_zones(
    swing_highs: pd.DataFrame,
    swing_lows: pd.DataFrame,
    df: pd.DataFrame,
    tolerance: float = 0.002,
    min_touches: int = 2,
) -> list[dict[str, Any]]:
    """
    Mengelompokkan swing points berdekatan menjadi S/R zones berdasarkan toleransi harga dan recency.

    Returns:
        List dict zone (price_high, price_low, strength, last_touched).
    """
    all_points: list[tuple[float, Any]] = []
    if not swing_highs.empty and "price" in swing_highs.columns:
        prices_h = swing_highs["price"].to_numpy(dtype=float)
        ts_h = swing_highs["timestamp"].tolist()
        for p, t in zip(prices_h, ts_h):
            all_points.append((float(p), t))
    if not swing_lows.empty and "price" in swing_lows.columns:
        prices_l = swing_lows["price"].to_numpy(dtype=float)
        ts_l = swing_lows["timestamp"].tolist()
        for p, t in zip(prices_l, ts_l):
            all_points.append((float(p), t))

    if not all_points:
        return []

    now_utc = datetime.now(timezone.utc)

    # Fast-path via native Rust C-ABI kernel (monika_core_rs)
    from monika.core.native.rust_bridge import find_sr_zones_f64

    prices = [p for p, _ in all_points]
    epoch_ts = [
        (t.replace(tzinfo=timezone.utc).timestamp() if getattr(t, "tzinfo", None) is None else t.timestamp())
        for _, t in all_points
    ]
    rust_sr = find_sr_zones_f64(prices, epoch_ts, tolerance=tolerance, min_touches=min_touches)
    if rust_sr is not None:
        p_high, p_low, touches, last_ts = rust_sr
        zones = []
        for k in range(len(p_high)):
            t_sec = float(last_ts[k])
            last_touch_ts = datetime.fromtimestamp(t_sec, tz=timezone.utc)
            recency_hours = (now_utc - last_touch_ts).total_seconds() / 3600
            recency_factor = max(0.3, min(1.0, 1.0 - (recency_hours / (30 * 24))))
            weighted_strength = round(int(touches[k]) * recency_factor, 2)
            zones.append(
                {
                    "price_high": float(p_high[k]),
                    "price_low": float(p_low[k]),
                    "strength": weighted_strength,
                    "touches": int(touches[k]),
                    "last_touched": last_touch_ts,
                }
            )
        logger.debug(f"Found {len(zones)} S/R zones")
        return zones

    # Sort by price
    all_points.sort(key=lambda x: x[0])

    zones: list[dict[str, Any]] = []
    used = [False] * len(all_points)

    for i in range(len(all_points)):
        if used[i]:
            continue

        price_i, ts_i = all_points[i]
        cluster = [(price_i, ts_i)]
        used[i] = True

        for j in range(i + 1, len(all_points)):
            if used[j]:
                continue
            price_j, ts_j = all_points[j]
            # Tolerance relative to price
            if abs(price_j - price_i) / max(1e-8, price_i) <= tolerance:
                cluster.append((price_j, ts_j))
                used[j] = True
            else:
                break  # sorted, no more nearby

        if len(cluster) >= min_touches:
            cluster_prices = [p for p, _ in cluster]
            cluster_times = [t for _, t in cluster]
            last_touch_ts = max(cluster_times)
            last_touch_aware = (
                last_touch_ts.replace(tzinfo=timezone.utc)
                if getattr(last_touch_ts, "tzinfo", None) is None
                else last_touch_ts
            )
            recency_hours = (now_utc - last_touch_aware).total_seconds() / 3600
            recency_factor = max(0.3, min(1.0, 1.0 - (recency_hours / (30 * 24))))
            weighted_strength = round(len(cluster) * recency_factor, 2)

            zones.append(
                {
                    "price_high": max(cluster_prices),
                    "price_low": min(cluster_prices),
                    "strength": weighted_strength,
                    "touches": len(cluster),
                    "last_touched": last_touch_ts,
                }
            )

    logger.debug(f"Found {len(zones)} S/R zones")
    return zones


def find_liquidity_zones(
    swing_highs: pd.DataFrame,
    swing_lows: pd.DataFrame,
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
) -> list[LiquidityZoneData]:
    """
    Mengidentifikasi pool likuiditas (swing points yang belum disapu harga) dengan dynamic ATR buffer.
    """
    zones: list[LiquidityZoneData] = []
    now = datetime.now(timezone.utc)

    if len(df) == 0:
        if not swing_highs.empty and "price" in swing_highs.columns:
            prices = swing_highs["price"].to_numpy(dtype=float)
            for p in prices:
                price = float(p)
                zones.append(
                    LiquidityZoneData(
                        symbol=symbol,
                        timeframe=timeframe,
                        zone_high=round(price + price * 0.001, 5),
                        zone_low=price,
                        type="above_swing_high",
                        identified_at=now,
                    )
                )
        if not swing_lows.empty and "price" in swing_lows.columns:
            prices = swing_lows["price"].to_numpy(dtype=float)
            for p in prices:
                price = float(p)
                zones.append(
                    LiquidityZoneData(
                        symbol=symbol,
                        timeframe=timeframe,
                        zone_high=price,
                        zone_low=round(price - price * 0.001, 5),
                        type="below_swing_low",
                        identified_at=now,
                    )
                )
        return zones[-10:]

    highs = np.asarray(df["high"], dtype=float)
    lows = np.asarray(df["low"], dtype=float)
    closes = np.asarray(df["close"], dtype=float) if "close" in df.columns else highs
    timestamps = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in df.index]

    # Dynamic buffer based on ATR
    atr_val = 0.0
    if len(df) >= 14:
        tr_1 = highs[1:] - lows[1:]
        tr_2 = np.abs(highs[1:] - closes[:-1])
        tr_3 = np.abs(lows[1:] - closes[:-1])
        tr_series = np.maximum(tr_1, np.maximum(tr_2, tr_3))
        atr_val = float(np.mean(tr_series[-14:])) if len(tr_series) >= 14 else 0.0

    # Unswept highs
    if not swing_highs.empty and "price" in swing_highs.columns:
        sh_prices = swing_highs["price"].to_numpy(dtype=float)
        sh_timestamps = swing_highs["timestamp"].tolist()
        for ts, price_val in zip(sh_timestamps, sh_prices):
            price = float(price_val)
            buffer = (atr_val * 0.15) if atr_val > 0 else (price * 0.001)
            idx = _search_ts(timestamps, ts, side="right")
            if idx >= len(highs) or float(highs[idx:].max()) <= price:
                zones.append(
                    LiquidityZoneData(
                        symbol=symbol,
                        timeframe=timeframe,
                        zone_high=round(price + buffer, 5),
                        zone_low=price,
                        type="above_swing_high",
                        identified_at=now,
                    )
                )

    # Unswept lows
    if not swing_lows.empty and "price" in swing_lows.columns:
        sl_prices = swing_lows["price"].to_numpy(dtype=float)
        sl_timestamps = swing_lows["timestamp"].tolist()
        for ts, price_val in zip(sl_timestamps, sl_prices):
            price = float(price_val)
            buffer = (atr_val * 0.15) if atr_val > 0 else (price * 0.001)
            idx = _search_ts(timestamps, ts, side="right")
            if idx >= len(lows) or float(lows[idx:].min()) >= price:
                zones.append(
                    LiquidityZoneData(
                        symbol=symbol,
                        timeframe=timeframe,
                        zone_high=price,
                        zone_low=round(price - buffer, 5),
                        type="below_swing_low",
                        identified_at=now,
                    )
                )

    logger.debug(f"Found {len(zones)} liquidity zones")
    return zones[-10:]  # Return up to 10 most recent unswept zones


def check_fvg_filled(
    ohlcv: pd.DataFrame,
    start_idx: int,
    gap_high: float,
    gap_low: float,
    direction: str,
) -> Optional[datetime]:
    """Mengecek apakah FVG sudah terisi (50% mitigated) oleh pergerakan candle sesudahnya."""
    gap_mid = (gap_high + gap_low) / 2.0
    n = len(ohlcv)
    if start_idx >= n:
        return None

    lows = np.asarray(ohlcv["low"], dtype=float)
    highs = np.asarray(ohlcv["high"], dtype=float)

    def _get_ts(idx: int) -> Optional[datetime]:
        if "timestamp" in ohlcv.columns:
            raw = ohlcv["timestamp"].iloc[idx]
        else:
            raw = ohlcv.index.values[idx]
        ts = pd.to_datetime(raw, utc=True)
        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()
        return None

    if direction == "bullish":
        hits = np.flatnonzero(lows[start_idx:] <= gap_mid)
        if len(hits) > 0:
            return _get_ts(start_idx + int(hits[0]))
    else:
        hits = np.flatnonzero(highs[start_idx:] >= gap_mid)
        if len(hits) > 0:
            return _get_ts(start_idx + int(hits[0]))
    return None


def find_fvg(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    existing_fvgs: Optional[Sequence[Any]] = None,
) -> list[FVGData]:
    """
    Detect Fair Value Gaps (FVG) from 3-candle imbalance patterns.
    An FVG is marked filled when price retraces into the gap.
    """
    zones: list[FVGData] = []
    n = len(df)
    if n < 3:
        return zones

    highs = np.asarray(df["high"], dtype=float)
    lows = np.asarray(df["low"], dtype=float)
    timestamps = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in df.index]
    ts_array = np.asarray(df.index)

    # Compute ATR (14-period rolling mean of true range)
    high_low = highs - lows
    atr_series = pd.Series(high_low, dtype=float).rolling(window=14, min_periods=1).mean()
    atr = np.asarray(atr_series, dtype=float)

    # Check if existing old FVGs are filled by current dataframe
    if existing_fvgs:
        for item in existing_fvgs:
            g_high = float(item.gap_high)
            g_low = float(item.gap_low)
            direction = str(item.direction)
            formed_at = item.formed_at
            filled_at = item.filled_at
            if filled_at is None:
                start_idx = _search_ts(timestamps, formed_at, side="right")
                if start_idx < n:
                    gap_mid = (g_high + g_low) / 2.0
                    if direction == "bullish":
                        hits = np.flatnonzero(lows[start_idx:] <= gap_mid)
                        if len(hits) > 0:
                            filled_at = timestamps[start_idx + int(hits[0])]
                    else:
                        hits = np.flatnonzero(highs[start_idx:] >= gap_mid)
                        if len(hits) > 0:
                            filled_at = timestamps[start_idx + int(hits[0])]
            zones.append(
                FVGData(
                    symbol=symbol,
                    timeframe=timeframe,
                    gap_high=g_high,
                    gap_low=g_low,
                    direction=direction,
                    formed_at=formed_at,
                    filled_at=filled_at,
                )
            )

    from monika.core.native.rust_bridge import find_fvg_f64

    rust_fvg = find_fvg_f64(highs, lows, atr, min_atr_factor=0.3)
    if rust_fvg is not None:
        f_indices, f_types, f_gap_high, f_gap_low, f_filled = rust_fvg
        for k in range(len(f_indices)):
            form_idx = int(f_indices[k])
            dir_str = "bullish" if f_types[k] == 1 else "bearish"
            fill_idx = int(f_filled[k])
            f_at = timestamps[fill_idx] if fill_idx >= 0 else None
            zones.append(
                FVGData(
                    symbol=symbol,
                    timeframe=timeframe,
                    gap_high=float(f_gap_high[k]),
                    gap_low=float(f_gap_low[k]),
                    direction=dir_str,
                    formed_at=timestamps[form_idx],
                    filled_at=f_at,
                )
            )
        logger.debug(f"Found {len(zones)} FVG zones")
        return zones

    for i in range(n - 2):
        candle_1_high = highs[i]
        candle_1_low = lows[i]
        candle_3_high = highs[i + 2]
        candle_3_low = lows[i + 2]
        formed_dt = timestamps[i + 2]
        current_atr = atr[i + 2] if (i + 2) < len(atr) else (atr[-1] if len(atr) > 0 else 0.0)

        # Bullish FVG
        if candle_3_low > candle_1_high:
            gap_low = float(candle_1_high)
            gap_high = float(candle_3_low)
            gap_size = gap_high - gap_low

            # Only persist if gap size >= 30% of current ATR
            if gap_size >= current_atr * 0.3:
                gap_mid = (gap_high + gap_low) / 2.0
                sub_lows = lows[i + 3 :]
                hits = np.flatnonzero(sub_lows <= gap_mid)
                filled_at = timestamps[i + 3 + int(hits[0])] if len(hits) > 0 else None

                zones.append(
                    FVGData(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_high=gap_high,
                        gap_low=gap_low,
                        direction="bullish",
                        formed_at=formed_dt,
                        filled_at=filled_at,
                    )
                )

        # Bearish FVG
        elif candle_3_high < candle_1_low:
            gap_high = float(candle_1_low)
            gap_low = float(candle_3_high)
            gap_size = gap_high - gap_low

            if gap_size >= current_atr * 0.3:
                gap_mid = (gap_high + gap_low) / 2.0
                sub_highs = highs[i + 3 :]
                hits = np.flatnonzero(sub_highs >= gap_mid)
                filled_at = timestamps[i + 3 + int(hits[0])] if len(hits) > 0 else None

                zones.append(
                    FVGData(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_high=gap_high,
                        gap_low=gap_low,
                        direction="bearish",
                        formed_at=formed_dt,
                        filled_at=filled_at,
                    )
                )

    logger.debug(f"Found {len(zones)} FVG zones")
    return zones


def find_order_blocks(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    existing_obs: Optional[Sequence[Any]] = None,
) -> list[OrderBlockData]:
    """
    Detect order blocks using ATR impulse qualification and 50% penetration mitigation.
    """
    bullish_obs: list[OrderBlockData] = []
    bearish_obs: list[OrderBlockData] = []

    if existing_obs:
        for item in existing_obs:
            ob_data = OrderBlockData(
                symbol=symbol,
                timeframe=timeframe,
                direction=str(item.direction),
                price_high=float(item.price_high),
                price_low=float(item.price_low),
                formed_at=item.formed_at,
                mitigated_at=item.mitigated_at,
            )
            if ob_data.direction == "bullish":
                bullish_obs.append(ob_data)
            else:
                bearish_obs.append(ob_data)

    n = len(df)
    if n < 10:
        return bullish_obs + bearish_obs

    opens = np.asarray(df["open"], dtype=float)
    highs = np.asarray(df["high"], dtype=float)
    lows = np.asarray(df["low"], dtype=float)
    closes = np.asarray(df["close"], dtype=float)
    timestamps = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in df.index]
    ts_array = np.asarray(df.index)

    tr_1 = highs[1:] - lows[1:]
    tr_2 = np.abs(highs[1:] - closes[:-1])
    tr_3 = np.abs(lows[1:] - closes[:-1])
    trs = np.maximum(tr_1, np.maximum(tr_2, tr_3))
    atr = float(np.mean(trs[-14:])) if len(trs) >= 14 else (float(np.mean(trs)) if len(trs) > 0 else 0.0)

    if atr == 0.0:
        return bullish_obs + bearish_obs

    max_ob_per_side = 3  # Limit to top 3 most recent OBs per direction
    new_bullish: list[OrderBlockData] = []
    new_bearish: list[OrderBlockData] = []

    # Fast-path via native Rust C-ABI kernel (monika_core_rs)
    from monika.core.native.rust_bridge import find_order_blocks_f64

    rust_ob = find_order_blocks_f64(opens, highs, lows, closes, atr)
    if rust_ob is not None:
        ob_indices, ob_directions, ob_p_high, ob_p_low, ob_confirmed, ob_mitigated = rust_ob
        for k in range(len(ob_indices)):
            form_idx = int(ob_indices[k])
            dir_str = "bullish" if ob_directions[k] == 1 else "bearish"
            conf_idx = int(ob_confirmed[k])
            mit_idx = int(ob_mitigated[k])

            formed_dt = timestamps[form_idx]
            confirmed_dt = timestamps[conf_idx]
            mitigated_dt = timestamps[mit_idx] if mit_idx >= 0 else None

            ob_item = OrderBlockData(
                symbol=symbol,
                timeframe=timeframe,
                direction=dir_str,
                price_high=float(ob_p_high[k]),
                price_low=float(ob_p_low[k]),
                formed_at=formed_dt,
                confirmed_at=confirmed_dt,
                mitigated_at=mitigated_dt,
            )
            if dir_str == "bullish":
                new_bullish.append(ob_item)
            else:
                new_bearish.append(ob_item)
    else:
        for i in range(2, n - 5):
            c_open = opens[i]
            c_close = closes[i]
            c_high = highs[i]
            c_low = lows[i]
            impulse_end = min(i + 5, n - 1)

            # Bullish OB: bearish candle followed by impulse bullish move
            if c_close < c_open:
                body_size = c_open - c_close
                impulse_high = highs[i + 1 : impulse_end + 1].max()
                impulse_move = impulse_high - c_high

                if impulse_move > max(body_size * 2, atr * 1.5):
                    confirm_idx = min(i + 10, n - 1)
                    post_impulse_low = lows[i + 1 : confirm_idx + 1].min()
                    if post_impulse_low > c_low:
                        formed_dt = timestamps[i]
                        confirmed_dt = timestamps[confirm_idx]
                        new_bullish.append(
                            OrderBlockData(
                                symbol=symbol,
                                timeframe=timeframe,
                                direction="bullish",
                                price_high=float(c_high),
                                price_low=float(c_low),
                                formed_at=formed_dt,
                                confirmed_at=confirmed_dt,
                            )
                        )

            # Bearish OB: bullish candle followed by impulse bearish move
            if c_close > c_open:
                body_size = c_close - c_open
                impulse_low = lows[i + 1 : impulse_end + 1].min()
                impulse_move = c_low - impulse_low

                if impulse_move > max(body_size * 2, atr * 1.5):
                    confirm_idx = min(i + 10, n - 1)
                    post_impulse_high = highs[i + 1 : confirm_idx + 1].max()
                    if post_impulse_high < c_high:
                        formed_dt = timestamps[i]
                        confirmed_dt = timestamps[confirm_idx]
                        new_bearish.append(
                            OrderBlockData(
                                symbol=symbol,
                                timeframe=timeframe,
                                direction="bearish",
                                price_high=float(c_high),
                                price_low=float(c_low),
                                formed_at=formed_dt,
                                confirmed_at=confirmed_dt,
                            )
                        )

    # Mitigation check (penetration into 50% of the OB zone)
    bullish_obs += new_bullish
    bearish_obs += new_bearish
    all_obs = bullish_obs + bearish_obs

    for ob in all_obs:
        idx = _search_ts(timestamps, ob.formed_at, side="right")
        if idx < n:
            ob_mid = (ob.price_high + ob.price_low) / 2.0
            if ob.direction == "bullish":
                hits = np.flatnonzero(lows[idx:] <= ob_mid)
                if len(hits) > 0:
                    ob.mitigated_at = timestamps[idx + int(hits[0])]
            elif ob.direction == "bearish":
                hits = np.flatnonzero(highs[idx:] >= ob_mid)
                if len(hits) > 0:
                    ob.mitigated_at = timestamps[idx + int(hits[0])]

    unmitigated_bullish = [
        ob for ob in sorted(bullish_obs, key=lambda x: x.formed_at, reverse=True) if ob.mitigated_at is None
    ][:max_ob_per_side]
    unmitigated_bearish = [
        ob for ob in sorted(bearish_obs, key=lambda x: x.formed_at, reverse=True) if ob.mitigated_at is None
    ][:max_ob_per_side]

    mitigated = [ob for ob in all_obs if ob.mitigated_at is not None]
    blocks = unmitigated_bullish + unmitigated_bearish + mitigated[-4:]

    logger.debug(
        f"OB detection {symbol}/{timeframe}: {len(unmitigated_bullish)} bull, {len(unmitigated_bearish)} bear unmitigated"
    )
    return blocks


def detect_structure_breaks(
    df: pd.DataFrame,
    swing_highs: pd.DataFrame,
    swing_lows: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> list[StructureBreakData]:
    """
    Detects BOS (Break of Structure) and CHoCH (Change of Character) with candle close confirmation.
    """
    breaks: list[StructureBreakData] = []
    swings: list[tuple[Any, float, str]] = []
    if not swing_highs.empty and "timestamp" in swing_highs.columns:
        p_h = swing_highs["price"].to_numpy(dtype=float)
        t_h = swing_highs["timestamp"].tolist()
        for t, p in zip(t_h, p_h):
            swings.append((t, float(p), "high"))
    if not swing_lows.empty and "timestamp" in swing_lows.columns:
        p_l = swing_lows["price"].to_numpy(dtype=float)
        t_l = swing_lows["timestamp"].tolist()
        for t, p in zip(t_l, p_l):
            swings.append((t, float(p), "low"))

    if not swings:
        return []

    swings.sort(key=lambda x: x[0])
    closes = np.asarray(df["close"], dtype=float)
    ts_array = np.asarray(df.index)
    timestamps = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in df.index]

    # Fast-path via native Rust C-ABI kernel (monika_core_rs)
    from monika.core.native.rust_bridge import detect_structure_breaks_f64

    s_indices = [_search_ts(timestamps, t, side="left") for t, _, _ in swings]
    s_prices = [p for _, p, _ in swings]
    s_types = [1 if typ == "high" else 2 for _, _, typ in swings]

    rust_breaks = detect_structure_breaks_f64(closes, s_indices, s_prices, s_types)
    if rust_breaks is not None:
        b_indices, b_types, b_dirs, b_prices = rust_breaks
        for k in range(len(b_indices)):
            b_idx = int(b_indices[k])
            b_type = "ChoCH" if b_types[k] == 2 else "BOS"
            b_dir = "bullish" if b_dirs[k] == 1 else "bearish"
            breaks.append(
                StructureBreakData(
                    symbol=symbol,
                    timeframe=timeframe,
                    type=b_type,
                    direction=b_dir,
                    price=float(b_prices[k]),
                    formed_at=timestamps[b_idx],
                )
            )
        return breaks

    current_trend = "ranging"
    last_high: Optional[float] = None
    last_high_ts: Any = None
    last_low: Optional[float] = None
    last_low_ts: Any = None

    for ts, price, typ in swings:
        if typ == "high":
            if last_high and price > last_high:
                if last_high_ts is not None:
                    start_i = _search_ts(timestamps, last_high_ts, side="left")
                else:
                    start_i = 0
                end_i = _search_ts(timestamps, ts, side="right")

                hits = np.flatnonzero(closes[start_i:end_i] > last_high)
                break_idx = None
                if len(hits) > 0:
                    break_idx = start_i + int(hits[0])
                else:
                    hits_fallback = np.flatnonzero(closes[start_i:] > last_high)
                    if len(hits_fallback) > 0:
                        break_idx = start_i + int(hits_fallback[0])

                if break_idx is not None and break_idx < len(timestamps):
                    break_ts = timestamps[break_idx]
                    break_type = "ChoCH" if current_trend == "bearish" else "BOS"
                    breaks.append(
                        StructureBreakData(
                            symbol=symbol,
                            timeframe=timeframe,
                            type=break_type,
                            direction="bullish",
                            price=last_high,
                            formed_at=break_ts,
                        )
                    )
                    current_trend = "bullish"
            elif last_high and price < last_high:
                current_trend = "bearish"
            last_high = price
            last_high_ts = ts
        else:
            if last_low and price < last_low:
                if last_low_ts is not None:
                    start_i = _search_ts(timestamps, last_low_ts, side="left")
                else:
                    start_i = 0
                end_i = _search_ts(timestamps, ts, side="right")

                hits = np.flatnonzero(closes[start_i:end_i] < last_low)
                break_idx = None
                if len(hits) > 0:
                    break_idx = start_i + int(hits[0])
                else:
                    hits_fallback = np.flatnonzero(closes[start_i:] < last_low)
                    if len(hits_fallback) > 0:
                        break_idx = start_i + int(hits_fallback[0])

                if break_idx is not None and break_idx < len(timestamps):
                    break_ts = timestamps[break_idx]
                    break_type = "ChoCH" if current_trend == "bullish" else "BOS"
                    breaks.append(
                        StructureBreakData(
                            symbol=symbol,
                            timeframe=timeframe,
                            type=break_type,
                            direction="bearish",
                            price=last_low,
                            formed_at=break_ts,
                        )
                    )
                    current_trend = "bearish"
            elif last_low and price > last_low:
                current_trend = "bullish"
            last_low = price
            last_low_ts = ts

    return breaks[-10:]  # Limit to last 10 for context compactness


# ------------------------------------------------------------------
# Pure Domain MarketStructureAnalyzer Class
# ------------------------------------------------------------------


class MarketStructureAnalyzer:
    """
    Pure Domain Market Structure Detector for OHLCV data.
    Operates in-memory on pandas DataFrames without database dependencies.
    For database-backed persistence and loading, use MarketStructureService
    in monika.application.services.market_structure_service.
    """

    def __init__(self, session: Any = None, settings: Optional[dict] = None):
        """
        Args:
            session: Optional session (ignored in pure domain detector, kept for signature compatibility).
            settings: Trading/indicators configuration dictionary.
        """
        self.session = session
        self.settings = settings or {}
        indicators_cfg = self.settings.get("trading", {}).get("indicators", {}) or self.settings.get("indicators", {})
        self.swing_window: int = indicators_cfg.get("swing_window", 5)
        self.sr_tolerance: float = indicators_cfg.get("sr_tolerance", 0.002)
        self.sr_min_touches: int = indicators_cfg.get("sr_min_touches", 2)

    def _find_swings(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        return find_swings(df, swing_window=self.swing_window)

    def _find_sr_zones(
        self,
        swing_highs: pd.DataFrame,
        swing_lows: pd.DataFrame,
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        return find_sr_zones(swing_highs, swing_lows, df, tolerance=self.sr_tolerance, min_touches=self.sr_min_touches)

    def _find_liquidity_zones(
        self,
        swing_highs: pd.DataFrame,
        swing_lows: pd.DataFrame,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> list[LiquidityZoneData]:
        return find_liquidity_zones(swing_highs, swing_lows, symbol, timeframe, df)

    def _find_fvg(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        existing_fvgs: Optional[Sequence[Any]] = None,
    ) -> list[FVGData]:
        return find_fvg(df, symbol, timeframe, existing_fvgs=existing_fvgs)

    def _find_order_blocks(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        existing_obs: Optional[Sequence[Any]] = None,
    ) -> list[OrderBlockData]:
        return find_order_blocks(df, symbol, timeframe, existing_obs=existing_obs)

    def _detect_structure_breaks(
        self,
        df: pd.DataFrame,
        swing_highs: pd.DataFrame,
        swing_lows: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> list[StructureBreakData]:
        return detect_structure_breaks(df, swing_highs, swing_lows, symbol, timeframe)

    _check_fvg_filled = staticmethod(check_fvg_filled)

    def analyze_dataframe(self, df: pd.DataFrame, symbol: str, timeframe: str) -> dict[str, Any]:
        """
        Pure in-memory analysis of OHLCV DataFrame.
        Returns a dictionary of extracted market structure features.
        """
        sh, sl = self._find_swings(df)
        sr = self._find_sr_zones(sh, sl, df)
        lq = self._find_liquidity_zones(sh, sl, symbol, timeframe, df)
        fv = self._find_fvg(df, symbol, timeframe)
        ob = self._find_order_blocks(df, symbol, timeframe)
        sb = self._detect_structure_breaks(df, sh, sl, symbol, timeframe)
        return {
            "swing_highs": sh,
            "swing_lows": sl,
            "sr_zones": sr,
            "liquidity_zones": lq,
            "fvg_zones": fv,
            "order_blocks": ob,
            "structure_breaks": sb,
        }

    async def analyze(self, symbol: str, timeframe: str) -> dict[str, int]:
        """Contract stub for analyzing structure. Overridden by MarketStructureService."""
        return {
            "swing_points": 0,
            "sr_zones": 0,
            "liquidity_zones": 0,
            "fvg_zones": 0,
            "order_blocks": 0,
            "struct_breaks": 0,
        }

    async def analyze_all(self, symbols: list[str], timeframes: list[str]) -> dict[str, dict[str, int]]:
        """Contract stub for batch structure analysis. Overridden by MarketStructureService."""
        return {s: await self.analyze(s, "H1") for s in symbols}

    async def get_structure_snapshot(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Contract stub for snapshot retrieval. Overridden by MarketStructureService."""
        return {}


# Alias for backward compatibility
MarketStructureCalculator = MarketStructureAnalyzer
