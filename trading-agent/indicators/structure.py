# ==============================================================================
# File: indicators/structure.py
# ==============================================================================

"""
Market Structure Analyzer: Swing Points, S/R Zones, Liquidity Zones, FVG.

Detects institutional market structure based on Smart Money Concepts (SMC):
1. Swing Points: Multi-bar fractal high/low levels.
2. S/R Zones: Support and resistance clusters derived from swing points.
3. Liquidity Zones: High-timeframe liquidity pools anchored at structural swing extremes.
4. FVG Zones: Fair Value Gaps (3-candle price imbalances).

Persists extracted structural features to relational storage.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence, Union, Any

import numpy as np
import pandas as pd
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    PriceOHLCV, SwingPoint, SRZone, LiquidityZone, FVGZone,
    OrderBlock, StructureBreak
)

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
FVG_MAX_DISTANCE = {
    "XAUUSD": 0.07,   # 7% — Emas bisa memiliki FVG lebar
    "XTIUSD": 0.10,   # 10% — Minyak lebih volatil
    "XBRUSD": 0.10,   # 10% — Minyak Brent
    "BTCUSD": 0.18,   # 18% — Kripto berfluktuasi tinggi
    "EURUSD": 0.035,  # 3.5% — Forex cenderung ketat
    "GBPUSD": 0.035,
    "USDJPY": 0.035,
    "AUDUSD": 0.030,
}


class MarketStructureAnalyzer:
    """
    Detects and persists market structure primitives from historical and real-time OHLCV.

    Usage:
        analyzer = MarketStructureAnalyzer(session, settings)
        await analyzer.analyze("XAUUSD", "H4")
    """

    def __init__(self, session: AsyncSession, settings: dict):
        """
        Args:
            session: Async SQLAlchemy session.
            settings: Dictionary konfigurasi lengkap atau khusus trading.
        """
        self.session = session
        self.settings = settings
        # Kompatibilitas untuk dict konfigurasi penuh atau khusus trading
        indicators_cfg = settings.get("trading", {}).get("indicators", {}) or settings.get("indicators", {})
        self.swing_window: int = indicators_cfg.get("swing_window", 5)
        self.sr_tolerance: float = indicators_cfg.get("sr_tolerance", 0.002)  # 0.2%
        self.sr_min_touches: int = indicators_cfg.get("sr_min_touches", 2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, symbol: str, timeframe: str) -> dict[str, int]:
        """
        Menjalankan analisis struktur pasar (Swing, S/R, Liq, FVG, OB, BOS).

        Returns:
            Dict metrik jumlah data yang tersimpan.
        """
        try:
            await self._prune_old_data(symbol, timeframe)
            
            df = await self._load_ohlcv(symbol, timeframe)
            if df is None or len(df) < (self.swing_window * 2 + 3):
                logger.warning(f"Insufficient data for structure analysis: {symbol}/{timeframe}")
                return {"swing_points": 0, "sr_zones": 0, "liquidity_zones": 0, "fvg_zones": 0, "order_blocks": 0, "struct_breaks": 0}

            # Fetch existing unfilled FVGs as DTOs (decoupled from session/thread)
            raw_fvgs = (await self.session.execute(
                select(FVGZone).where(FVGZone.symbol == symbol, FVGZone.timeframe == timeframe, FVGZone.filled_at.is_(None))
            )).scalars().all()
            existing_fvgs = [
                FVGData(
                    symbol=f.symbol,
                    timeframe=f.timeframe,
                    gap_high=float(f.gap_high),
                    gap_low=float(f.gap_low),
                    direction=str(f.direction),
                    formed_at=f.formed_at,
                    filled_at=f.filled_at,
                )
                for f in raw_fvgs
            ]
            
            # Fetch existing unmitigated OBs as DTOs (decoupled from session/thread)
            raw_obs = (await self.session.execute(
                select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe, OrderBlock.mitigated_at.is_(None))
            )).scalars().all()
            existing_obs = [
                OrderBlockData(
                    symbol=o.symbol,
                    timeframe=o.timeframe,
                    direction=str(o.direction),
                    price_high=float(o.price_high),
                    price_low=float(o.price_low),
                    formed_at=o.formed_at,
                    mitigated_at=o.mitigated_at,
                )
                for o in raw_obs
            ]

            import asyncio
            def _cpu_compute():
                sh, sl = self._find_swings(df)
                sr = self._find_sr_zones(sh, sl, df)
                lq = self._find_liquidity_zones(sh, sl, symbol, timeframe, df)
                fv = self._find_fvg(df, symbol, timeframe, existing_fvgs)
                ob = self._find_order_blocks(df, symbol, timeframe, existing_obs)
                sb = self._detect_structure_breaks(df, sh, sl, symbol, timeframe)
                return sh, sl, sr, lq, fv, ob, sb

            swing_highs, swing_lows, sr_zones, liq_zones, fvg_zones, order_blocks, struct_breaks = await asyncio.to_thread(_cpu_compute)

            counts = {
                "swing_points": await self._save_swings(symbol, timeframe, swing_highs, swing_lows),
                "sr_zones":     await self._save_sr_zones(symbol, timeframe, sr_zones),
                "liquidity_zones": await self._save_liquidity(symbol, timeframe, liq_zones),
                "fvg_zones":    await self._save_fvg(symbol, timeframe, fvg_zones),
                "order_blocks": await self._save_order_blocks(symbol, timeframe, order_blocks),
                "struct_breaks": await self._save_structure_breaks(symbol, timeframe, struct_breaks),
            }

            logger.debug(
                f"Structure analysis {symbol}/{timeframe}: "
                f"swings={counts['swing_points']}, SR={counts['sr_zones']}, "
                f"liq={counts['liquidity_zones']}, fvg={counts['fvg_zones']}, "
                f"OB={counts['order_blocks']}, BOS={counts['struct_breaks']}"
            )
            return counts
        except Exception:
            await self.session.rollback()
            raise

    async def analyze_all(
        self, symbols: list[str], timeframes: list[str]
    ) -> dict[str, dict[str, int]]:
        """Menjalankan analisis untuk kumpulan symbol dan timeframe."""
        results = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}/{tf}"
                try:
                    results[key] = await self.analyze(symbol, tf)
                except Exception as e:
                    logger.error(f"Structure analysis failed for {key}: {e}")
                    try:
                        await self.session.rollback()
                    except Exception:
                        pass
                    results[key] = {"swing_points": 0, "sr_zones": 0,
                                    "liquidity_zones": 0, "fvg_zones": 0,
                                    "order_blocks": 0, "struct_breaks": 0}
        total_swings = sum(r.get("swing_points", 0) for r in results.values())
        total_sr = sum(r.get("sr_zones", 0) for r in results.values())
        total_liq = sum(r.get("liquidity_zones", 0) for r in results.values())
        total_fvg = sum(r.get("fvg_zones", 0) for r in results.values())
        total_ob = sum(r.get("order_blocks", 0) for r in results.values())
        total_bos = sum(r.get("struct_breaks", 0) for r in results.values())
        logger.info(
            f"Structure analysis complete: {len(results)} pairs "
            f"(swings={total_swings}, SR={total_sr}, liq={total_liq}, "
            f"fvg={total_fvg}, OB={total_ob}, BOS={total_bos})"
        )
        return results

    async def _prune_old_data(self, symbol: str, timeframe: str) -> None:
        """Menghapus data lama (retensi FVG ditangani spesifik di _save_fvg)."""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        try:
            await self.session.execute(
                delete(SwingPoint)
                .where(SwingPoint.symbol == symbol)
                .where(SwingPoint.timeframe == timeframe)
                .where(SwingPoint.timestamp < cutoff)
            )
            await self.session.execute(
                delete(LiquidityZone)
                .where(LiquidityZone.symbol == symbol)
                .where(LiquidityZone.timeframe == timeframe)
                .where(LiquidityZone.identified_at < cutoff)
            )
        except Exception as e:
            logger.debug(f"Structure pruning non-fatal error: {e}")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_ohlcv(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Memuat OHLCV dari DB, diurutkan secara kronologis (terlama ke terbaru)."""
        result = await self.session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())  # DESC untuk mendapatkan data terbaru
            .limit(500)
        )
        rows = result.scalars().all()
        if not rows:
            return None

        # Balik urutan agar kembali kronologis (ascending) untuk kalkulasi
        rows = list(reversed(rows))

        df = pd.DataFrame({
            "timestamp": [r.timestamp for r in rows],
            "open":  [r.open  for r in rows],
            "high":  [r.high  for r in rows],
            "low":   [r.low   for r in rows],
            "close": [r.close for r in rows],
        })
        df.set_index("timestamp", inplace=True)
        return df


    # ------------------------------------------------------------------
    # 1. Swing Points (Fractal Method)
    # ------------------------------------------------------------------

    def _find_swings(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Detect swing high/low points using a symmetric fractal window (n-candle comparison).

        Returns:
            Tuple of DataFrames (swing_highs, swing_lows) containing [timestamp, price].
        """
        n = self.swing_window
        highs_idx = []
        lows_idx  = []

        prices_high = np.asarray(df["high"], dtype=float)
        prices_low  = np.asarray(df["low"], dtype=float)
        timestamps  = df.index.tolist()

        for i in range(n, len(df) - n):
            # Task 5.1: Skip inside bars
            prev_high = prices_high[i - 1]
            prev_low = prices_low[i - 1]
            is_inside = bool(prices_high[i] <= prev_high and prices_low[i] >= prev_low)
            
            if is_inside:
                continue

            window_h = list(prices_high[i-n:i]) + list(prices_high[i+1:i+n+1])
            window_l = list(prices_low[i-n:i])  + list(prices_low[i+1:i+n+1])

            if prices_high[i] > max(window_h):
                highs_idx.append({"timestamp": timestamps[i], "price": float(prices_high[i])})
            if prices_low[i] < min(window_l):
                lows_idx.append({"timestamp": timestamps[i], "price": float(prices_low[i])})

        swing_highs = pd.DataFrame(highs_idx) if highs_idx else pd.DataFrame(columns=["timestamp", "price"])
        swing_lows  = pd.DataFrame(lows_idx)  if lows_idx  else pd.DataFrame(columns=["timestamp", "price"])

        logger.debug(f"Found {len(swing_highs)} swing highs, {len(swing_lows)} swing lows")
        return swing_highs, swing_lows

    # ------------------------------------------------------------------
    # 2. S/R Zones (Cluster-based)
    # ------------------------------------------------------------------

    def _find_sr_zones(
        self,
        swing_highs: pd.DataFrame,
        swing_lows: pd.DataFrame,
        df: pd.DataFrame,
    ) -> list[dict]:
        """
        Mengelompokkan swing points berdekatan menjadi S/R zones berdasarkan toleransi harga dan recency.

        Returns:
            List dict zone (price_high, price_low, strength, last_touched).
        """
        all_points = []
        for _, row in swing_highs.iterrows():
            all_points.append((row["price"], row["timestamp"]))
        for _, row in swing_lows.iterrows():
            all_points.append((row["price"], row["timestamp"]))

        if not all_points:
            return []

        # Sort by price
        all_points.sort(key=lambda x: x[0])

        zones: list[dict] = []
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
                if abs(price_j - price_i) / max(1e-8, price_i) <= self.sr_tolerance:
                    cluster.append((price_j, ts_j))
                    used[j] = True
                else:
                    break  # sorted, no more nearby

            if len(cluster) >= self.sr_min_touches:
                cluster_prices = [p for p, _ in cluster]
                cluster_times  = [t for _, t in cluster]
                last_touch_ts = max(cluster_times)
                last_touch_aware = last_touch_ts.replace(tzinfo=timezone.utc) if last_touch_ts.tzinfo is None else last_touch_ts
                recency_hours = (now_utc - last_touch_aware).total_seconds() / 3600
                recency_factor = max(0.3, min(1.0, 1.0 - (recency_hours / (30 * 24))))
                weighted_strength = round(len(cluster) * recency_factor, 2)

                zones.append({
                    "price_high": max(cluster_prices),
                    "price_low":  min(cluster_prices),
                    "strength":   weighted_strength,
                    "touches":    len(cluster),
                    "last_touched": last_touch_ts,
                })

        logger.debug(f"Found {len(zones)} S/R zones")
        return zones

    # ------------------------------------------------------------------
    # 3. Liquidity Zones
    # ------------------------------------------------------------------

    def _find_liquidity_zones(
        self,
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
                np.maximum(
                    (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()
                )
            )
            atr_val = float(np.mean(tr_series[-14:]))

        # Unswept highs
        if not swing_highs.empty:
            for _, row in swing_highs.iterrows():
                ts = row["timestamp"]
                price = float(row["price"])
                buffer = (atr_val * 0.15) if atr_val > 0 else (price * 0.001)
                subsequent_df = df[df.index > ts]
                if subsequent_df.empty or subsequent_df['high'].max() <= price:
                    zones.append(LiquidityZoneData(
                        symbol=symbol,
                        timeframe=timeframe,
                        zone_high=round(price + buffer, 5),
                        zone_low=price,
                        type="above_swing_high",
                        identified_at=now,
                    ))

        # Unswept lows
        if not swing_lows.empty:
            for _, row in swing_lows.iterrows():
                ts = row["timestamp"]
                price = float(row["price"])
                buffer = (atr_val * 0.15) if atr_val > 0 else (price * 0.001)
                subsequent_df = df[df.index > ts]
                if subsequent_df.empty or subsequent_df['low'].min() >= price:
                    zones.append(LiquidityZoneData(
                        symbol=symbol,
                        timeframe=timeframe,
                        zone_high=price,
                        zone_low=round(price - buffer, 5),
                        type="below_swing_low",
                        identified_at=now,
                    ))

        logger.debug(f"Found {len(zones)} liquidity zones")
        return zones[-10:]  # Return up to 10 most recent unswept zones

    # ------------------------------------------------------------------
    # 4. Fair Value Gaps (FVG)
    # ------------------------------------------------------------------

    def _find_fvg(
        self, df: pd.DataFrame, symbol: str, timeframe: str, existing_fvgs: Optional[Sequence[Any]] = None
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
        high_low = df['high'] - df['low']
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
                    # Find if any candle in df fills it
                    check_filled = self._check_fvg_filled(ohlcv, 0, g_high, g_low, direction)
                    if check_filled:
                        filled_at = check_filled
                zones.append(FVGData(
                    symbol=symbol,
                    timeframe=timeframe,
                    gap_high=g_high,
                    gap_low=g_low,
                    direction=direction,
                    formed_at=formed_at,
                    filled_at=filled_at,
                ))

        for i in range(n - 2):
            candle_1 = ohlcv.iloc[i]
            # candle_2 = ohlcv.iloc[i + 1]  # middle candle
            candle_3 = ohlcv.iloc[i + 2]

            ts_formed = candle_3["timestamp"]
            current_atr = atr.iloc[i + 2] if (i + 2) < len(atr) else (atr.iloc[-1] if len(atr) > 0 else 0)

            # Bullish FVG
            if candle_3["low"] > candle_1["high"]:
                gap_low  = float(candle_1["high"])
                gap_high = float(candle_3["low"])
                gap_size = gap_high - gap_low

                # Only persist if gap size >= 30% of current ATR
                if gap_size >= current_atr * 0.3:
                    # Check if gap was already filled by subsequent candles
                    filled_at = self._check_fvg_filled(ohlcv, i + 3, gap_high, gap_low, "bullish")
    
                    zones.append(FVGData(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_high=gap_high,
                        gap_low=gap_low,
                        direction="bullish",
                        formed_at=ts_formed,
                        filled_at=filled_at,
                    ))

            # Bearish FVG
            elif candle_3["high"] < candle_1["low"]:
                gap_high = float(candle_1["low"])
                gap_low  = float(candle_3["high"])
                gap_size = gap_high - gap_low

                if gap_size >= current_atr * 0.3:
                    filled_at = self._check_fvg_filled(ohlcv, i + 3, gap_high, gap_low, "bearish")
    
                    zones.append(FVGData(
                        symbol=symbol,
                        timeframe=timeframe,
                        gap_high=gap_high,
                        gap_low=gap_low,
                        direction="bearish",
                        formed_at=ts_formed,
                        filled_at=filled_at,
                    ))

        logger.debug(f"Found {len(zones)} FVG zones")
        return zones

    @staticmethod
    def _check_fvg_filled(
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
                    return candle["timestamp"]
            else:  # bearish
                # Filled when price trades up into 50% of the gap
                if candle["high"] >= gap_mid:
                    return candle["timestamp"]
        return None

    # ------------------------------------------------------------------
    # 5. Order Blocks (OB) & Structure Breaks
    # ------------------------------------------------------------------

    def _find_order_blocks(
        self, df: pd.DataFrame, symbol: str, timeframe: str, existing_obs: Optional[Sequence[Any]] = None
    ) -> list[OrderBlockData]:
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
        
        # Calculate ATR for threshold (better than avg_body)
        highs = np.asarray(ohlcv['high'], dtype=float)
        lows = np.asarray(ohlcv['low'], dtype=float)
        closes = np.asarray(ohlcv['close'], dtype=float)
        
        # Simple ATR calculation
        trs = []
        for i in range(1, len(closes)):
            tr = max(float(highs[i] - lows[i]), 
                     abs(float(highs[i] - closes[i-1])),
                     abs(float(lows[i] - closes[i-1])))
            trs.append(tr)
        atr = sum(trs[-14:]) / min(14, len(trs)) if trs else 0.0
        
        if atr == 0:
            return bullish_obs + bearish_obs
            
        MAX_OB_PER_SIDE = 3  # Limit to top 3 most recent OBs per direction
        new_bullish: list[OrderBlockData] = []
        new_bearish: list[OrderBlockData] = []
        
        for i in range(2, n - 5):
            candle = ohlcv.iloc[i]
            
            # Look for impulse move in the 5 candles after
            impulse_end = min(i + 5, n - 1)
            
            # Bullish OB: bearish candle followed by impulse bullish move
            if candle['close'] < candle['open']:  # Bearish candle
                body_size = candle['open'] - candle['close']
                impulse_high = ohlcv.iloc[i+1:impulse_end+1]['high'].max()
                impulse_move = impulse_high - candle['high']
                
                # RELAXED threshold per IMP-2
                if impulse_move > max(body_size * 2, atr * 1.5):
                    post_impulse_low = ohlcv.iloc[i+1:min(i+10, n)]['low'].min()
                    if post_impulse_low > candle['low']:  # Price stayed above OB
                        new_bullish.append(OrderBlockData(
                            symbol=symbol, timeframe=timeframe, direction="bullish",
                            price_high=float(candle['high']), price_low=float(candle['low']),
                            formed_at=candle['timestamp']
                        ))
            
            # Bearish OB: bullish candle followed by impulse bearish move
            if candle['close'] > candle['open']:  # Bullish candle
                body_size = candle['close'] - candle['open']
                impulse_low = ohlcv.iloc[i+1:impulse_end+1]['low'].min()
                impulse_move = candle['low'] - impulse_low
                
                # RELAXED threshold per IMP-2
                if impulse_move > max(body_size * 2, atr * 1.5):
                    post_impulse_high = ohlcv.iloc[i+1:min(i+10, n)]['high'].max()
                    if post_impulse_high < candle['high']:  # Price stayed below OB
                        new_bearish.append(OrderBlockData(
                            symbol=symbol, timeframe=timeframe, direction="bearish",
                            price_high=float(candle['high']), price_low=float(candle['low']),
                            formed_at=candle['timestamp']
                        ))
        
        # Mitigation check (penetration into 50% of the OB zone)
        bullish_obs += new_bullish
        bearish_obs += new_bearish
        all_obs = bullish_obs + bearish_obs
        for ob in all_obs:
            ob_ts = pd.Timestamp(ob.formed_at)
            if ob_ts.tzinfo is None:
                ob_ts = ob_ts.tz_localize('UTC')
            
            ts_series = pd.to_datetime(ohlcv['timestamp'], utc=True)
            future_bars = ohlcv[ts_series > ob_ts]
            ob_mid = (ob.price_high + ob.price_low) / 2.0
            
            for _, bar in future_bars.iterrows():
                if ob.direction == "bullish" and bar['low'] <= ob_mid:
                    ob.mitigated_at = bar['timestamp']
                    break
                elif ob.direction == "bearish" and bar['high'] >= ob_mid:
                    ob.mitigated_at = bar['timestamp']
                    break
                    
        # Keep only most recent unmitigated OBs, limit count
        unmitigated_bullish = [ob for ob in sorted(bullish_obs, key=lambda x: x.formed_at, reverse=True) 
                               if ob.mitigated_at is None][:MAX_OB_PER_SIDE]
        unmitigated_bearish = [ob for ob in sorted(bearish_obs, key=lambda x: x.formed_at, reverse=True)
                               if ob.mitigated_at is None][:MAX_OB_PER_SIDE]
        
        # Return all (mitigated for reference + limited unmitigated)
        mitigated = [ob for ob in all_obs if ob.mitigated_at is not None]
        blocks = unmitigated_bullish + unmitigated_bearish + mitigated[-4:]  # Keep some mitigated for context
        
        logger.debug(f'OB detection {symbol}/{timeframe}: {len(unmitigated_bullish)} bull, {len(unmitigated_bearish)} bear unmitigated')
        return blocks

    def _detect_structure_breaks(
        self, df: pd.DataFrame, swing_highs: pd.DataFrame, swing_lows: pd.DataFrame, 
        symbol: str, timeframe: str
    ) -> list[StructureBreakData]:
        breaks: list[StructureBreakData] = []
        swings = []
        for _, row in swing_highs.iterrows():
            swings.append((row['timestamp'], float(row['price']), 'high'))
        for _, row in swing_lows.iterrows():
            swings.append((row['timestamp'], float(row['price']), 'low'))
            
        swings.sort(key=lambda x: x[0])
        current_trend = "ranging"
        last_high = None
        last_low = None
        
        for ts, price, typ in swings:
            if typ == 'high':
                if last_high and price > last_high:
                    subsequent = df[df.index >= ts]
                    breaking_candles = subsequent[subsequent['close'] > last_high]
                    if not breaking_candles.empty:
                        break_ts = breaking_candles.index[0]
                        break_type = "ChoCH" if current_trend == "bearish" else "BOS"
                        breaks.append(StructureBreakData(
                            symbol=symbol, timeframe=timeframe, type=break_type, 
                            direction="bullish", price=last_high, formed_at=break_ts
                        ))
                        current_trend = "bullish"
                elif last_high and price < last_high:
                    current_trend = "bearish"
                last_high = price
            else:
                if last_low and price < last_low:
                    subsequent = df[df.index >= ts]
                    breaking_candles = subsequent[subsequent['close'] < last_low]
                    if not breaking_candles.empty:
                        break_ts = breaking_candles.index[0]
                        break_type = "ChoCH" if current_trend == "bullish" else "BOS"
                        breaks.append(StructureBreakData(
                            symbol=symbol, timeframe=timeframe, type=break_type, 
                            direction="bearish", price=last_low, formed_at=break_ts
                        ))
                        current_trend = "bearish"
                elif last_low and price > last_low:
                    current_trend = "bullish"
                last_low = price
                
        return breaks[-10:]  # Batasi 10 terakhir agar konteks prompt efisien

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save_swings(
        self,
        symbol: str,
        timeframe: str,
        highs: pd.DataFrame,
        lows: pd.DataFrame,
    ) -> int:
        """Mengganti data swing points lama dengan yang baru."""
        await self.session.execute(
            delete(SwingPoint)
            .where(SwingPoint.symbol == symbol)
            .where(SwingPoint.timeframe == timeframe)
        )

        saved = 0
        for _, row in highs.iterrows():
            self.session.add(SwingPoint(
                symbol=symbol, timeframe=timeframe,
                timestamp=row["timestamp"], type="high", price=float(row["price"])
            ))
            saved += 1
        for _, row in lows.iterrows():
            self.session.add(SwingPoint(
                symbol=symbol, timeframe=timeframe,
                timestamp=row["timestamp"], type="low", price=float(row["price"])
            ))
            saved += 1

        await self.session.commit()
        return saved

    async def _save_sr_zones(
        self, symbol: str, timeframe: str, zones: list[dict]
    ) -> int:
        """Mengganti S/R zones lama dengan yang baru."""
        await self.session.execute(
            delete(SRZone)
            .where(SRZone.symbol == symbol)
            .where(SRZone.timeframe == timeframe)
        )

        for zone in zones:
            self.session.add(SRZone(
                symbol=symbol, timeframe=timeframe,
                price_high=float(zone["price_high"]),
                price_low=float(zone["price_low"]),
                strength=float(zone["strength"]),
                last_touched=zone["last_touched"],
            ))

        await self.session.commit()
        return len(zones)

    async def _save_liquidity(self, symbol: str, timeframe: str, zones: list[Any]) -> int:
        """
        Persist newly identified liquidity zones (replaces existing zones per cycle).
        """
        await self.session.execute(
            delete(LiquidityZone)
            .where(LiquidityZone.symbol == symbol)
            .where(LiquidityZone.timeframe == timeframe)
        )
        
        for zone in zones:
            self.session.add(LiquidityZone(
                symbol=symbol,
                timeframe=timeframe,
                zone_high=float(zone.zone_high),
                zone_low=float(zone.zone_low),
                type=str(zone.type),
                identified_at=zone.identified_at,
            ))
        
        if zones:
            await self.session.commit()
        
        return len(zones)

    async def _save_fvg(
        self,
        arg1: Union[str, list[Any]],
        arg2: Optional[Union[str, list[Any]]] = None,
        arg3: Optional[list[Any]] = None,
    ) -> int:
        """
        Upsert Fair Value Gaps.
        Preserves active unfilled FVGs as long as price distance and age remain relevant.
        Supports signatures:
          _save_fvg(symbol, timeframe, zones)
          _save_fvg(zones)
        """
        if isinstance(arg1, str) and isinstance(arg2, str):
            sym = arg1
            tf = arg2
            zones = arg3 or []
        elif isinstance(arg1, list):
            zones = arg1
            sym = arg2 if isinstance(arg2, str) else (zones[0].symbol if zones else None)
            tf = arg3 if isinstance(arg3, str) else (zones[0].timeframe if zones else None)
        else:
            return 0

        if not sym or not tf:
            return 0
            
        MAX_FVG_PER_DIRECTION = 4  # Maximum 4 bullish + 4 bearish = 8 total
        
        bullish_zones = sorted(
            [z for z in zones if z.direction == 'bullish' and z.filled_at is None],
            key=lambda x: x.formed_at, reverse=True
        )[:MAX_FVG_PER_DIRECTION]
        
        bearish_zones = sorted(
            [z for z in zones if z.direction == 'bearish' and z.filled_at is None],
            key=lambda x: x.formed_at, reverse=True
        )[:MAX_FVG_PER_DIRECTION]
        
        filled_zones = [z for z in zones if z.filled_at is not None][-4:]  # Keep last 4 filled for context
        
        target_zones = bullish_zones + bearish_zones + filled_zones

        cutoff_fvg = datetime.now(timezone.utc) - timedelta(days=30)
        await self.session.execute(
            delete(FVGZone)
            .where(FVGZone.symbol == sym)
            .where(FVGZone.timeframe == tf)
            .where(FVGZone.filled_at.is_not(None))
            .where(FVGZone.filled_at < cutoff_fvg)
        )

        last_bar = (await self.session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == sym)
            .where(PriceOHLCV.timeframe == tf)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        current_price = float(last_bar.close) if last_bar else None

        DEFAULT_FVG_DISTANCE = 0.04
        max_dist = FVG_MAX_DISTANCE.get(sym, DEFAULT_FVG_DISTANCE)

        MAX_FVG_AGE_BARS = {
            "H4": 100,   # ~16 hari
            "D1": 60,    # ~3 bulan
            "H1": 200,   # ~8 hari
        }
        
        now_utc = datetime.now(timezone.utc)
        tf_hours = {"H1": 1, "H4": 4, "D1": 24}.get(tf, 4)
        max_age_hours = MAX_FVG_AGE_BARS.get(tf, 100) * tf_hours

        # Load existing unfilled FVGs directly from DB
        existing_records = (await self.session.execute(
            select(FVGZone)
            .where(FVGZone.symbol == sym)
            .where(FVGZone.timeframe == tf)
            .where(FVGZone.filled_at.is_(None))
        )).scalars().all()

        existing_map = {
            (round(float(f.gap_high), 5), round(float(f.gap_low), 5), str(f.direction)): f
            for f in existing_records
        }

        # Process zones
        new_count = 0
        seen_keys = set()
        for zone in target_zones:
            key = (round(float(zone.gap_high), 5), round(float(zone.gap_low), 5), str(zone.direction))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            if key in existing_map:
                # Update fill status if now filled
                db_fvg = existing_map[key]
                if zone.filled_at is not None and db_fvg.filled_at is None:
                    db_fvg.filled_at = zone.filled_at
                del existing_map[key]
            else:
                # New FVG — check if it's relevant before inserting
                if zone.filled_at is None:
                    formed_ts = zone.formed_at.replace(tzinfo=timezone.utc) if zone.formed_at.tzinfo is None else zone.formed_at
                    if (now_utc - formed_ts).total_seconds() / 3600 > max_age_hours:
                        continue  # Skip old unfilled FVGs
                        
                    if current_price:
                        midpoint = (float(zone.gap_high) + float(zone.gap_low)) / 2.0
                        distance_pct = abs(midpoint - current_price) / max(1e-8, current_price)
                        if distance_pct > max_dist:
                            continue  # Too far, skip
                
                self.session.add(FVGZone(
                    symbol=sym,
                    timeframe=tf,
                    gap_high=float(zone.gap_high),
                    gap_low=float(zone.gap_low),
                    direction=str(zone.direction),
                    formed_at=zone.formed_at,
                    filled_at=zone.filled_at,
                ))
                new_count += 1

        # Prune older unfilled FVGs if price has diverged excessively
        if current_price:
            for fvg in existing_map.values():
                midpoint = (float(fvg.gap_high) + float(fvg.gap_low)) / 2.0
                distance_pct = abs(midpoint - current_price) / max(1e-8, current_price)
                if distance_pct > max_dist * 2:  # Distance > 2x limit = irrelevant
                    await self.session.delete(fvg)

        await self.session.commit()
        return new_count

    async def _save_order_blocks(
        self,
        arg1: Union[str, list[Any]],
        arg2: Optional[Union[str, list[Any]]] = None,
        arg3: Optional[list[Any]] = None,
    ) -> int:
        """
        Upsert Order Blocks.
        Preserves active unmitigated OBs and updates mitigated ones.
        Supports signatures:
          _save_order_blocks(symbol, timeframe, blocks)
          _save_order_blocks(blocks)
        """
        if isinstance(arg1, str) and isinstance(arg2, str):
            symbol = arg1
            timeframe = arg2
            blocks = arg3 or []
        elif isinstance(arg1, list):
            blocks = arg1
            symbol = arg2 if isinstance(arg2, str) else (blocks[0].symbol if blocks else None)
            timeframe = arg3 if isinstance(arg3, str) else (blocks[0].timeframe if blocks else None)
        else:
            return 0

        if not symbol or not timeframe:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        await self.session.execute(
            delete(OrderBlock)
            .where(OrderBlock.symbol == symbol)
            .where(OrderBlock.timeframe == timeframe)
            .where(OrderBlock.mitigated_at.is_not(None))
            .where(OrderBlock.mitigated_at < cutoff)
        )
        
        existing_obs = (await self.session.execute(
            select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe)
        )).scalars().all()
        
        existing_map = {
            (round(float(ob.price_high), 5), round(float(ob.price_low), 5), str(ob.direction)): ob 
            for ob in existing_obs
        }
        
        saved = 0
        seen_keys = set()
        for block in blocks:
            key = (round(float(block.price_high), 5), round(float(block.price_low), 5), str(block.direction))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            
            if key in existing_map:
                existing_ob = existing_map[key]
                if block.mitigated_at and not existing_ob.mitigated_at:
                    existing_ob.mitigated_at = block.mitigated_at
            else:
                self.session.add(OrderBlock(
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=str(block.direction),
                    price_high=float(block.price_high),
                    price_low=float(block.price_low),
                    formed_at=block.formed_at,
                    mitigated_at=block.mitigated_at,
                ))
                saved += 1
        
        await self.session.commit()
        return saved

    async def _save_structure_breaks(self, symbol: str, timeframe: str, breaks: list[Any]) -> int:
        await self.session.execute(
            delete(StructureBreak).where(StructureBreak.symbol == symbol).where(StructureBreak.timeframe == timeframe)
        )
        for brk in breaks:
            self.session.add(StructureBreak(
                symbol=symbol,
                timeframe=timeframe,
                type=str(brk.type),
                direction=str(brk.direction),
                price=float(brk.price),
                formed_at=brk.formed_at,
            ))
        if breaks:
            await self.session.commit()
        return len(breaks)

    # ------------------------------------------------------------------
    # Read helpers (used by analysis stage)
    # ------------------------------------------------------------------

    async def get_structure_snapshot(self, symbol: str, timeframe: str) -> dict:
        """
        Snapshot ringkas struktur pasar (Swings, S/R, FVG, dll).
        Digunakan oleh agent untuk tahap analisis per aset.
        """
        # Swing points (last 10 highs and lows)
        highs_q = await self.session.execute(
            select(SwingPoint)
            .where(SwingPoint.symbol == symbol)
            .where(SwingPoint.timeframe == timeframe)
            .where(SwingPoint.type == "high")
            .order_by(SwingPoint.timestamp.desc()).limit(10)
        )
        lows_q = await self.session.execute(
            select(SwingPoint)
            .where(SwingPoint.symbol == symbol)
            .where(SwingPoint.timeframe == timeframe)
            .where(SwingPoint.type == "low")
            .order_by(SwingPoint.timestamp.desc()).limit(10)
        )
        sr_q = await self.session.execute(
            select(SRZone)
            .where(SRZone.symbol == symbol)
            .where(SRZone.timeframe == timeframe)
            .order_by(SRZone.strength.desc()).limit(5)
        )
        liq_q = await self.session.execute(
            select(LiquidityZone)
            .where(LiquidityZone.symbol == symbol)
            .where(LiquidityZone.timeframe == timeframe)
            .order_by(LiquidityZone.identified_at.desc()).limit(10)
        )
        fvg_q = await self.session.execute(
            select(FVGZone)
            .where(FVGZone.symbol == symbol)
            .where(FVGZone.timeframe == timeframe)
            .where(FVGZone.filled_at == None)  # noqa: E711 — unfilled FVGs only
            .order_by(FVGZone.formed_at.desc()).limit(10)
        )
        ob_q = await self.session.execute(
            select(OrderBlock)
            .where(OrderBlock.symbol == symbol)
            .where(OrderBlock.timeframe == timeframe)
            .where(OrderBlock.mitigated_at == None)  # noqa: E711
            .order_by(OrderBlock.formed_at.desc()).limit(5)
        )
        sb_q = await self.session.execute(
            select(StructureBreak)
            .where(StructureBreak.symbol == symbol)
            .where(StructureBreak.timeframe == timeframe)
            .order_by(StructureBreak.formed_at.desc()).limit(5)
        )

        highs = highs_q.scalars().all()
        lows  = lows_q.scalars().all()
        sr    = sr_q.scalars().all()
        liq   = liq_q.scalars().all()
        fvg   = fvg_q.scalars().all()
        ob    = ob_q.scalars().all()
        sb    = sb_q.scalars().all()

        return {
            "swing_highs": [{"price": r.price, "ts": r.timestamp.isoformat()} for r in highs],
            "swing_lows":  [{"price": r.price, "ts": r.timestamp.isoformat()} for r in lows],
            "sr_zones":    [{"high": r.price_high, "low": r.price_low, "strength": r.strength} for r in sr],
            "liquidity_zones": [{"high": r.zone_high, "low": r.zone_low, "type": r.type} for r in liq],
            "fvg_zones":   [{"high": r.gap_high, "low": r.gap_low, "dir": r.direction, "formed": r.formed_at.isoformat()} for r in fvg],
            "order_blocks": [{"high": r.price_high, "low": r.price_low, "dir": r.direction, "formed": r.formed_at.isoformat()} for r in ob],
            "structure_breaks": [{"price": r.price, "type": r.type, "dir": r.direction, "formed": r.formed_at.isoformat()} for r in sb],
        }
