# ==============================================================================
# File: application/services/market_structure_service.py
# Monika Market Structure Application Service
# ==============================================================================

"""
Market Structure Application Service.

Orchestrates market structure primitive detection (Swing Points, S/R Zones,
Liquidity Pools, FVGs, Order Blocks, BOS/CHoCH) by reading OHLCV from the
relational database, dispatching calculation to pure domain algorithms in
monika.domain.indicators.structure, and persisting extracted features.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.indicators.structure import (
    FVGData,
    LiquidityZoneData,
    MarketStructureAnalyzer as DomainMarketStructureAnalyzer,
    OrderBlockData,
    StructureBreakData,
    detect_structure_breaks,
    find_fvg,
    find_liquidity_zones,
    find_order_blocks,
    find_sr_zones,
    find_swings,
    get_fvg_max_distance,
)
from monika.infrastructure.database.models import (
    FVGZone,
    LiquidityZone,
    OrderBlock,
    PriceOHLCV,
    SRZone,
    StructureBreak,
    SwingPoint,
)

logger = logging.getLogger("TradingAgent.Services.MarketStructure")


class MarketStructureService(DomainMarketStructureAnalyzer):
    """
    Application Service that detects and persists market structure primitives.

    Usage:
        service = MarketStructureService(session, settings)
        await service.analyze("XAUUSD", "H4")
    """

    def __init__(self, session: Any = None, settings: Optional[dict] = None):
        """
        Args:
            session: Async SQLAlchemy session.
            settings: Dictionary konfigurasi lengkap atau khusus trading.
        """
        super().__init__(session=session, settings=settings)

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
                return {
                    "swing_points": 0,
                    "sr_zones": 0,
                    "liquidity_zones": 0,
                    "fvg_zones": 0,
                    "order_blocks": 0,
                    "struct_breaks": 0,
                }

            if not self.session:
                return {}

            # Fetch existing unfilled FVGs as DTOs (decoupled from session/thread)
            raw_fvgs = (
                (
                    await self.session.execute(
                        select(FVGZone).where(
                            FVGZone.symbol == symbol, FVGZone.timeframe == timeframe, FVGZone.filled_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
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
            raw_obs = (
                (
                    await self.session.execute(
                        select(OrderBlock).where(
                            OrderBlock.symbol == symbol,
                            OrderBlock.timeframe == timeframe,
                            OrderBlock.mitigated_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
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

            def _cpu_compute():
                sh, sl = find_swings(df, self.swing_window)
                sr = find_sr_zones(sh, sl, df, tolerance=self.sr_tolerance, min_touches=self.sr_min_touches)
                lq = find_liquidity_zones(sh, sl, symbol, timeframe, df)
                fv = find_fvg(df, symbol, timeframe, existing_fvgs)
                ob = find_order_blocks(df, symbol, timeframe, existing_obs)
                sb = detect_structure_breaks(df, sh, sl, symbol, timeframe)
                return sh, sl, sr, lq, fv, ob, sb

            (
                swing_highs,
                swing_lows,
                sr_zones,
                liq_zones,
                fvg_zones,
                order_blocks,
                struct_breaks,
            ) = await asyncio.to_thread(_cpu_compute)

            counts = {
                "swing_points": await self._save_swings(symbol, timeframe, swing_highs, swing_lows, commit=False),
                "sr_zones": await self._save_sr_zones(symbol, timeframe, sr_zones, commit=False),
                "liquidity_zones": await self._save_liquidity(symbol, timeframe, liq_zones, commit=False),
                "fvg_zones": await self._save_fvg(symbol, timeframe, fvg_zones, commit=False),
                "order_blocks": await self._save_order_blocks(symbol, timeframe, order_blocks, commit=False),
                "struct_breaks": await self._save_structure_breaks(symbol, timeframe, struct_breaks, commit=False),
            }
            if self.session:
                await self.session.commit()

            logger.debug(
                f"Structure analysis {symbol}/{timeframe}: "
                f"swings={counts['swing_points']}, SR={counts['sr_zones']}, "
                f"liq={counts['liquidity_zones']}, fvg={counts['fvg_zones']}, "
                f"OB={counts['order_blocks']}, BOS={counts['struct_breaks']}"
            )
            return counts
        except Exception:
            if self.session:
                await self.session.rollback()
            raise

    async def analyze_all(self, symbols: list[str], timeframes: list[str]) -> dict[str, dict[str, int]]:
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
                        if self.session:
                            await self.session.rollback()
                    except Exception:
                        pass
                    results[key] = {
                        "swing_points": 0,
                        "sr_zones": 0,
                        "liquidity_zones": 0,
                        "fvg_zones": 0,
                        "order_blocks": 0,
                        "struct_breaks": 0,
                    }
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
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        try:
            if not self.session:
                return

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
        if not self.session:
            return None

        result = await self.session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(500)
        )
        rows = result.scalars().all()
        if not rows:
            return None

        rows = list(reversed(rows))

        def _get_ts(r: Any) -> Any:
            c = getattr(r, "canonical_timestamp", None)
            return c if isinstance(c, datetime) else getattr(r, "timestamp", None)

        df = pd.DataFrame(
            {
                "timestamp": [_get_ts(r) for r in rows],
                "open": [r.open for r in rows],
                "high": [r.high for r in rows],
                "low": [r.low for r in rows],
                "close": [r.close for r in rows],
            }
        )
        df.set_index("timestamp", inplace=True)
        df = df.loc[~df.index.duplicated(keep="last")]
        return df

    # ------------------------------------------------------------------
    # Method delegates for testing and caller compatibility
    # ------------------------------------------------------------------

    def _find_swings(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        return find_swings(df, self.swing_window)

    def _find_sr_zones(self, swing_highs: pd.DataFrame, swing_lows: pd.DataFrame, df: pd.DataFrame) -> list[dict]:
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
        symbol: str = "",
        timeframe: str = "",
        existing_fvgs: Optional[Sequence[Any]] = None,
    ) -> list[FVGData]:
        return find_fvg(df, symbol, timeframe, existing_fvgs)

    def _find_order_blocks(
        self,
        df: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "",
        existing_obs: Optional[Sequence[Any]] = None,
    ) -> list[OrderBlockData]:
        return find_order_blocks(df, symbol, timeframe, existing_obs)

    def _detect_structure_breaks(
        self,
        df: pd.DataFrame,
        swing_highs: pd.DataFrame,
        swing_lows: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "",
    ) -> list[StructureBreakData]:
        return detect_structure_breaks(df, swing_highs, swing_lows, symbol, timeframe)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save_swings(
        self,
        symbol: str,
        timeframe: str,
        highs: pd.DataFrame,
        lows: pd.DataFrame,
        commit: bool = True,
    ) -> int:
        """Mengganti data swing points lama dengan yang baru."""
        if not self.session:
            return 0

        await self.session.execute(
            delete(SwingPoint).where(SwingPoint.symbol == symbol).where(SwingPoint.timeframe == timeframe)
        )

        saved = 0
        for _, row in highs.iterrows():
            ts_val = row["confirmed_at"] if "confirmed_at" in row.index else None
            ts_confirmed = (
                ts_val
                if ts_val is not None and str(ts_val).strip() not in ("", "nan", "NaT", "None")
                else row["timestamp"]
            )
            self.session.add(
                SwingPoint(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=pd.Timestamp(str(ts_confirmed)).to_pydatetime(),
                    type="high",
                    price=float(np.asarray(row["price"]).item()),
                )
            )
            saved += 1
        for _, row in lows.iterrows():
            ts_val = row["confirmed_at"] if "confirmed_at" in row.index else None
            ts_confirmed = (
                ts_val
                if ts_val is not None and str(ts_val).strip() not in ("", "nan", "NaT", "None")
                else row["timestamp"]
            )
            self.session.add(
                SwingPoint(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=pd.Timestamp(str(ts_confirmed)).to_pydatetime(),
                    type="low",
                    price=float(np.asarray(row["price"]).item()),
                )
            )
            saved += 1

        if commit:
            await self.session.commit()
        return saved

    async def _save_sr_zones(self, symbol: str, timeframe: str, zones: list[dict], commit: bool = True) -> int:
        """Mengganti S/R zones lama dengan yang baru."""
        if not self.session:
            return 0

        await self.session.execute(delete(SRZone).where(SRZone.symbol == symbol).where(SRZone.timeframe == timeframe))

        for zone in zones:
            self.session.add(
                SRZone(
                    symbol=symbol,
                    timeframe=timeframe,
                    price_high=float(zone["price_high"]),
                    price_low=float(zone["price_low"]),
                    strength=float(zone["strength"]),
                    last_touched=zone["last_touched"],
                )
            )

        if commit:
            await self.session.commit()
        return len(zones)

    async def _save_liquidity(self, symbol: str, timeframe: str, zones: list[Any], commit: bool = True) -> int:
        """Persist newly identified liquidity zones."""
        if not self.session:
            return 0

        await self.session.execute(
            delete(LiquidityZone).where(LiquidityZone.symbol == symbol).where(LiquidityZone.timeframe == timeframe)
        )

        for zone in zones:
            self.session.add(
                LiquidityZone(
                    symbol=symbol,
                    timeframe=timeframe,
                    zone_high=float(zone.zone_high),
                    zone_low=float(zone.zone_low),
                    type=str(zone.type),
                    identified_at=zone.identified_at,
                )
            )

        if commit and zones:
            await self.session.commit()

        return len(zones)

    async def _save_fvg(
        self,
        arg1: Union[str, list[Any]],
        arg2: Optional[Union[str, list[Any]]] = None,
        arg3: Optional[list[Any]] = None,
        commit: bool = True,
    ) -> int:
        """Upsert Fair Value Gaps."""
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

        if not sym or not tf or not self.session:
            return 0

        MAX_FVG_PER_DIRECTION = 4

        bullish_zones = sorted(
            [z for z in zones if z.direction == "bullish" and z.filled_at is None],
            key=lambda x: x.formed_at,
            reverse=True,
        )[:MAX_FVG_PER_DIRECTION]

        bearish_zones = sorted(
            [z for z in zones if z.direction == "bearish" and z.filled_at is None],
            key=lambda x: x.formed_at,
            reverse=True,
        )[:MAX_FVG_PER_DIRECTION]

        filled_zones = [z for z in zones if z.filled_at is not None][-4:]
        target_zones = bullish_zones + bearish_zones + filled_zones

        cutoff_fvg = datetime.now(timezone.utc) - timedelta(days=14)

        await self.session.execute(
            delete(FVGZone)
            .where(FVGZone.symbol == sym)
            .where(FVGZone.timeframe == tf)
            .where(FVGZone.filled_at.is_not(None))
            .where(FVGZone.filled_at < cutoff_fvg)
        )

        last_bar = (
            await self.session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == sym)
                .where(PriceOHLCV.timeframe == tf)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        current_price = float(last_bar.close) if last_bar else None

        max_dist = get_fvg_max_distance(sym)

        MAX_FVG_AGE_BARS = {
            "H4": 100,
            "D1": 60,
            "H1": 200,
        }

        now_utc = datetime.now(timezone.utc)
        tf_hours = {"H1": 1, "H4": 4, "D1": 24}.get(tf, 4)
        max_age_hours = MAX_FVG_AGE_BARS.get(tf, 100) * tf_hours

        existing_records = (
            (
                await self.session.execute(
                    select(FVGZone)
                    .where(FVGZone.symbol == sym)
                    .where(FVGZone.timeframe == tf)
                    .where((FVGZone.filled_at.is_(None)) | (FVGZone.formed_at >= cutoff_fvg))
                )
            )
            .scalars()
            .all()
        )

        existing_map = {
            (round(float(f.gap_high), 5), round(float(f.gap_low), 5), str(f.direction)): f for f in existing_records
        }

        new_count = 0
        seen_keys = set()
        for zone in target_zones:
            key = (round(float(zone.gap_high), 5), round(float(zone.gap_low), 5), str(zone.direction))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            if key in existing_map:
                db_fvg = existing_map[key]
                if zone.filled_at is not None and db_fvg.filled_at is None:
                    db_fvg.filled_at = zone.filled_at
                del existing_map[key]
            else:
                if zone.filled_at is None:
                    formed_ts = (
                        zone.formed_at.replace(tzinfo=timezone.utc) if zone.formed_at.tzinfo is None else zone.formed_at
                    )
                    if (now_utc - formed_ts).total_seconds() / 3600 > max_age_hours:
                        continue

                    if current_price:
                        midpoint = (float(zone.gap_high) + float(zone.gap_low)) / 2.0
                        distance_pct = abs(midpoint - current_price) / max(1e-8, current_price)
                        if distance_pct > max_dist:
                            continue

                self.session.add(
                    FVGZone(
                        symbol=sym,
                        timeframe=tf,
                        gap_high=float(zone.gap_high),
                        gap_low=float(zone.gap_low),
                        direction=str(zone.direction),
                        formed_at=zone.formed_at,
                        filled_at=zone.filled_at,
                    )
                )
                new_count += 1

        if current_price:
            for fvg in existing_map.values():
                midpoint = (float(fvg.gap_high) + float(fvg.gap_low)) / 2.0
                distance_pct = abs(midpoint - current_price) / max(1e-8, current_price)
                if distance_pct > max_dist * 2:
                    await self.session.delete(fvg)

        if commit:
            await self.session.commit()
        return new_count

    async def _save_order_blocks(
        self,
        arg1: Union[str, list[Any]],
        arg2: Optional[Union[str, list[Any]]] = None,
        arg3: Optional[list[Any]] = None,
        commit: bool = True,
    ) -> int:
        """Upsert Order Blocks."""
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

        if not symbol or not timeframe or not self.session:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        await self.session.execute(
            delete(OrderBlock)
            .where(OrderBlock.symbol == symbol)
            .where(OrderBlock.timeframe == timeframe)
            .where(OrderBlock.mitigated_at.is_not(None))
            .where(OrderBlock.mitigated_at < cutoff)
        )

        existing_obs = (
            (
                await self.session.execute(
                    select(OrderBlock).where(OrderBlock.symbol == symbol, OrderBlock.timeframe == timeframe)
                )
            )
            .scalars()
            .all()
        )

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
                self.session.add(
                    OrderBlock(
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=str(block.direction),
                        price_high=float(block.price_high),
                        price_low=float(block.price_low),
                        formed_at=block.formed_at,
                        mitigated_at=block.mitigated_at,
                    )
                )
                saved += 1

        if commit:
            await self.session.commit()
        return saved

    async def _save_structure_breaks(self, symbol: str, timeframe: str, breaks: list[Any], commit: bool = True) -> int:
        if not self.session:
            return 0

        await self.session.execute(
            delete(StructureBreak).where(StructureBreak.symbol == symbol).where(StructureBreak.timeframe == timeframe)
        )
        for brk in breaks:
            self.session.add(
                StructureBreak(
                    symbol=symbol,
                    timeframe=timeframe,
                    type=str(brk.type),
                    direction=str(brk.direction),
                    price=float(brk.price),
                    formed_at=brk.formed_at,
                )
            )
        if commit and breaks:
            await self.session.commit()
        return len(breaks)

    async def get_structure_snapshot(self, symbol: str, timeframe: str) -> dict:
        """Snapshot ringkas struktur pasar (Swings, S/R, FVG, dll)."""
        if not self.session:
            return {}

        highs_q = await self.session.execute(
            select(SwingPoint)
            .where(SwingPoint.symbol == symbol)
            .where(SwingPoint.timeframe == timeframe)
            .where(SwingPoint.type == "high")
            .order_by(SwingPoint.timestamp.desc())
            .limit(10)
        )
        lows_q = await self.session.execute(
            select(SwingPoint)
            .where(SwingPoint.symbol == symbol)
            .where(SwingPoint.timeframe == timeframe)
            .where(SwingPoint.type == "low")
            .order_by(SwingPoint.timestamp.desc())
            .limit(10)
        )
        sr_q = await self.session.execute(
            select(SRZone)
            .where(SRZone.symbol == symbol)
            .where(SRZone.timeframe == timeframe)
            .order_by(SRZone.strength.desc())
            .limit(5)
        )
        liq_q = await self.session.execute(
            select(LiquidityZone)
            .where(LiquidityZone.symbol == symbol)
            .where(LiquidityZone.timeframe == timeframe)
            .order_by(LiquidityZone.identified_at.desc())
            .limit(10)
        )
        fvg_q = await self.session.execute(
            select(FVGZone)
            .where(FVGZone.symbol == symbol)
            .where(FVGZone.timeframe == timeframe)
            .where(FVGZone.filled_at.is_(None))
            .order_by(FVGZone.formed_at.desc())
            .limit(10)
        )
        ob_q = await self.session.execute(
            select(OrderBlock)
            .where(OrderBlock.symbol == symbol)
            .where(OrderBlock.timeframe == timeframe)
            .where(OrderBlock.mitigated_at.is_(None))
            .order_by(OrderBlock.formed_at.desc())
            .limit(5)
        )
        sb_q = await self.session.execute(
            select(StructureBreak)
            .where(StructureBreak.symbol == symbol)
            .where(StructureBreak.timeframe == timeframe)
            .order_by(StructureBreak.formed_at.desc())
            .limit(5)
        )

        highs = highs_q.scalars().all()
        lows = lows_q.scalars().all()
        sr = sr_q.scalars().all()
        liq = liq_q.scalars().all()
        fvg = fvg_q.scalars().all()
        ob = ob_q.scalars().all()
        sb = sb_q.scalars().all()

        return {
            "swing_highs": [{"price": r.price, "ts": r.timestamp.isoformat()} for r in highs],
            "swing_lows": [{"price": r.price, "ts": r.timestamp.isoformat()} for r in lows],
            "sr_zones": [{"high": r.price_high, "low": r.price_low, "strength": r.strength} for r in sr],
            "liquidity_zones": [{"high": r.zone_high, "low": r.zone_low, "type": r.type} for r in liq],
            "fvg_zones": [
                {"high": r.gap_high, "low": r.gap_low, "dir": r.direction, "formed": r.formed_at.isoformat()}
                for r in fvg
            ],
            "order_blocks": [
                {"high": r.price_high, "low": r.price_low, "dir": r.direction, "formed": r.formed_at.isoformat()}
                for r in ob
            ],
            "structure_breaks": [
                {"price": r.price, "type": r.type, "dir": r.direction, "formed": r.formed_at.isoformat()} for r in sb
            ],
        }


# Canonical & backward-compatible aliases
MarketStructureAnalyzer = MarketStructureService
MarketStructureCalculator = MarketStructureService
