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

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Structure")


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
    highs_idx: list[dict[str, Any]] = []
    lows_idx: list[dict[str, Any]] = []

    prices_high = np.asarray(df["high"], dtype=float)
    prices_low = np.asarray(df["low"], dtype=float)
    timestamps = df.index.tolist()

    for i in range(n, len(df) - n):
        # Task 5.1: Skip inside bars
        prev_high = prices_high[i - 1]
        prev_low = prices_low[i - 1]
        is_inside = bool(prices_high[i] <= prev_high and prices_low[i] >= prev_low)

        if is_inside:
            continue

        window_h = list(prices_high[i - n : i]) + list(prices_high[i + 1 : i + n + 1])
        window_l = list(prices_low[i - n : i]) + list(prices_low[i + 1 : i + n + 1])

        if prices_high[i] > max(window_h):
            highs_idx.append(
                {
                    "timestamp": timestamps[i],
                    "price": float(prices_high[i]),
                    "confirmed_at": timestamps[i + n],
                    "confirmation_lag_bars": n,
                }
            )
        if prices_low[i] < min(window_l):
            lows_idx.append(
                {
                    "timestamp": timestamps[i],
                    "price": float(prices_low[i]),
                    "confirmed_at": timestamps[i + n],
                    "confirmation_lag_bars": n,
                }
            )

    columns = ["timestamp", "price", "confirmed_at", "confirmation_lag_bars"]
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
        prices_h = [float(p) for p in swing_highs["price"].astype(float).tolist()]
        ts_h = swing_highs["timestamp"].tolist()
        for p, t in zip(prices_h, ts_h):
            all_points.append((p, t))
    if not swing_lows.empty and "price" in swing_lows.columns:
        prices_l = [float(p) for p in swing_lows["price"].astype(float).tolist()]
        ts_l = swing_lows["timestamp"].tolist()
        for p, t in zip(prices_l, ts_l):
            all_points.append((p, t))

    if not all_points:
        return []

    # Sort by price
    all_points.sort(key=lambda x: x[0])

    zones: list[dict[str, Any]] = []
    used = [False] * len(all_points)
    now_utc = datetime.now(timezone.utc)

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

    # Dynamic buffer based on ATR
    atr_val = 0.0
    if len(df) >= 14:
        tr_series = np.maximum(
            df["high"] - df["low"],
            np.maximum((df["high"] - df["close"].shift(1)).abs(), (df["low"] - df["close"].shift(1)).abs()),
        )
        atr_val = float(np.mean(tr_series[-14:]))

    # Unswept highs
    if not swing_highs.empty:
        for _, row in swing_highs.iterrows():
            ts = row["timestamp"]
            price = float(np.asarray(row["price"]).item())
            buffer = (atr_val * 0.15) if atr_val > 0 else (price * 0.001)
            subsequent_df = df[df.index > ts]
            if subsequent_df.empty or subsequent_df["high"].max() <= price:
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
    if not swing_lows.empty:
        for _, row in swing_lows.iterrows():
            ts = row["timestamp"]
            price = float(np.asarray(row["price"]).item())
            buffer = (atr_val * 0.15) if atr_val > 0 else (price * 0.001)
            subsequent_df = df[df.index > ts]
            if subsequent_df.empty or subsequent_df["low"].min() >= price:
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
    for i in range(start_idx, len(ohlcv)):
        candle = ohlcv.iloc[i]
        if direction == "bullish":
            # Filled when price trades down into 50% of the gap
            if candle["low"] <= gap_mid:
                ts = candle["timestamp"]
                return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        else:  # bearish
            # Filled when price trades up into 50% of the gap
            if candle["high"] >= gap_mid:
                ts = candle["timestamp"]
                return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
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
    ohlcv = df.reset_index()  # bring timestamp into column
    n = len(ohlcv)

    if n < 3:
        return zones

    # Compute ATR (14-period rolling mean of true range)
    high_low = df["high"] - df["low"]
    atr = high_low.rolling(window=14, min_periods=1).mean().bfill().reset_index(drop=True)

    # Check if existing old FVGs are filled by current dataframe
    if existing_fvgs:
        for item in existing_fvgs:
            g_high = float(item.gap_high)
            g_low = float(item.gap_low)
            direction = str(item.direction)
            formed_at = item.formed_at
            filled_at = item.filled_at
            if filled_at is None:
                # Find if any candle strictly after formed_at in df fills it
                ts_formed = pd.Timestamp(formed_at)
                after_mask = ohlcv["timestamp"] > ts_formed
                if after_mask.any():
                    start_idx = int(after_mask.idxmax())
                    check_filled = check_fvg_filled(ohlcv, start_idx, g_high, g_low, direction)
                    if check_filled:
                        filled_at = check_filled
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

    for i in range(n - 2):
        candle_1 = ohlcv.iloc[i]
        candle_3 = ohlcv.iloc[i + 2]

        ts_formed = candle_3["timestamp"]
        formed_dt = ts_formed.to_pydatetime() if hasattr(ts_formed, "to_pydatetime") else ts_formed
        current_atr = atr.iloc[i + 2] if (i + 2) < len(atr) else (atr.iloc[-1] if len(atr) > 0 else 0.0)

        # Bullish FVG
        if candle_3["low"] > candle_1["high"]:
            gap_low = float(candle_1["high"])
            gap_high = float(candle_3["low"])
            gap_size = gap_high - gap_low

            # Only persist if gap size >= 30% of current ATR
            if gap_size >= current_atr * 0.3:
                filled_at = check_fvg_filled(ohlcv, i + 3, gap_high, gap_low, "bullish")

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
        elif candle_3["high"] < candle_1["low"]:
            gap_high = float(candle_1["low"])
            gap_low = float(candle_3["high"])
            gap_size = gap_high - gap_low

            if gap_size >= current_atr * 0.3:
                filled_at = check_fvg_filled(ohlcv, i + 3, gap_high, gap_low, "bearish")

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

    ohlcv = df.reset_index()
    n = len(ohlcv)
    if n < 10:
        return bullish_obs + bearish_obs

    highs = np.asarray(ohlcv["high"], dtype=float)
    lows = np.asarray(ohlcv["low"], dtype=float)
    closes = np.asarray(ohlcv["close"], dtype=float)

    trs = []
    for i in range(1, len(closes)):
        tr = max(float(highs[i] - lows[i]), abs(float(highs[i] - closes[i - 1])), abs(float(lows[i] - closes[i - 1])))
        trs.append(tr)
    atr = sum(trs[-14:]) / min(14, len(trs)) if trs else 0.0

    if atr == 0.0:
        return bullish_obs + bearish_obs

    max_ob_per_side = 3  # Limit to top 3 most recent OBs per direction
    new_bullish: list[OrderBlockData] = []
    new_bearish: list[OrderBlockData] = []

    for i in range(2, n - 5):
        candle = ohlcv.iloc[i]
        impulse_end = min(i + 5, n - 1)

        # Bullish OB: bearish candle followed by impulse bullish move
        if candle["close"] < candle["open"]:
            body_size = candle["open"] - candle["close"]
            impulse_high = ohlcv.iloc[i + 1 : impulse_end + 1]["high"].max()
            impulse_move = impulse_high - candle["high"]

            if impulse_move > max(body_size * 2, atr * 1.5):
                confirm_idx = min(i + 10, n - 1)
                post_impulse_low = ohlcv.iloc[i + 1 : confirm_idx + 1]["low"].min()
                if post_impulse_low > candle["low"]:
                    formed_dt = (
                        candle["timestamp"].to_pydatetime()
                        if hasattr(candle["timestamp"], "to_pydatetime")
                        else candle["timestamp"]
                    )
                    confirmed_dt = (
                        ohlcv.iloc[confirm_idx]["timestamp"].to_pydatetime()
                        if hasattr(ohlcv.iloc[confirm_idx]["timestamp"], "to_pydatetime")
                        else ohlcv.iloc[confirm_idx]["timestamp"]
                    )
                    new_bullish.append(
                        OrderBlockData(
                            symbol=symbol,
                            timeframe=timeframe,
                            direction="bullish",
                            price_high=float(candle["high"]),
                            price_low=float(candle["low"]),
                            formed_at=formed_dt,
                            confirmed_at=confirmed_dt,
                        )
                    )

        # Bearish OB: bullish candle followed by impulse bearish move
        if candle["close"] > candle["open"]:
            body_size = candle["close"] - candle["open"]
            impulse_low = ohlcv.iloc[i + 1 : impulse_end + 1]["low"].min()
            impulse_move = candle["low"] - impulse_low

            if impulse_move > max(body_size * 2, atr * 1.5):
                confirm_idx = min(i + 10, n - 1)
                post_impulse_high = ohlcv.iloc[i + 1 : confirm_idx + 1]["high"].max()
                if post_impulse_high < candle["high"]:
                    formed_dt = (
                        candle["timestamp"].to_pydatetime()
                        if hasattr(candle["timestamp"], "to_pydatetime")
                        else candle["timestamp"]
                    )
                    confirmed_dt = (
                        ohlcv.iloc[confirm_idx]["timestamp"].to_pydatetime()
                        if hasattr(ohlcv.iloc[confirm_idx]["timestamp"], "to_pydatetime")
                        else ohlcv.iloc[confirm_idx]["timestamp"]
                    )
                    new_bearish.append(
                        OrderBlockData(
                            symbol=symbol,
                            timeframe=timeframe,
                            direction="bearish",
                            price_high=float(candle["high"]),
                            price_low=float(candle["low"]),
                            formed_at=formed_dt,
                            confirmed_at=confirmed_dt,
                        )
                    )

    # Mitigation check (penetration into 50% of the OB zone)
    bullish_obs += new_bullish
    bearish_obs += new_bearish
    all_obs = bullish_obs + bearish_obs
    for ob in all_obs:
        ob_ts = pd.Timestamp(ob.formed_at)
        if ob_ts.tzinfo is None:
            ob_ts = ob_ts.tz_localize("UTC")

        ts_series = pd.to_datetime(ohlcv["timestamp"], utc=True)
        future_bars = ohlcv[ts_series > ob_ts]
        ob_mid = (ob.price_high + ob.price_low) / 2.0

        for _, bar in future_bars.iterrows():
            bar_ts = pd.Timestamp(str(bar["timestamp"])).to_pydatetime()
            if isinstance(bar_ts, datetime):
                if ob.direction == "bullish" and bar["low"] <= ob_mid:
                    ob.mitigated_at = bar_ts
                    break
                elif ob.direction == "bearish" and bar["high"] >= ob_mid:
                    ob.mitigated_at = bar_ts
                    break

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
    for _, row in swing_highs.iterrows():
        swings.append((row["timestamp"], float(np.asarray(row["price"]).item()), "high"))
    for _, row in swing_lows.iterrows():
        swings.append((row["timestamp"], float(np.asarray(row["price"]).item()), "low"))

    swings.sort(key=lambda x: x[0])
    current_trend = "ranging"
    last_high: Optional[float] = None
    last_high_ts: Any = None
    last_low: Optional[float] = None
    last_low_ts: Any = None

    for ts, price, typ in swings:
        if typ == "high":
            if last_high and price > last_high:
                subsequent = df.loc[df.index >= last_high_ts] if last_high_ts is not None else df.loc[df.index <= ts]
                breaking_candles = subsequent.loc[(subsequent.index <= ts) & (subsequent["close"] > last_high)]
                if breaking_candles.empty:
                    breaking_candles = subsequent.loc[subsequent["close"] > last_high]
                if not breaking_candles.empty:
                    break_ts = pd.to_datetime(breaking_candles.index[0]).to_pydatetime()
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
                subsequent = df.loc[df.index >= last_low_ts] if last_low_ts is not None else df.loc[df.index <= ts]
                breaking_candles = subsequent.loc[(subsequent.index <= ts) & (subsequent["close"] < last_low)]
                if breaking_candles.empty:
                    breaking_candles = subsequent.loc[subsequent["close"] < last_low]
                if not breaking_candles.empty:
                    break_ts = pd.to_datetime(breaking_candles.index[0]).to_pydatetime()
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
