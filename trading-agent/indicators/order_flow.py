# ==============================================================================
# File: indicators/order_flow.py
# ==============================================================================

"""
Dual-Mode Order Flow & Liquidity Engine.
- Primary: Real Level 2 Market Depth (DOM) via mt5.market_book_add / mt5.market_book_get
  (Order Book Imbalance OBI, Top-of-Book Depth).
- Seamless Fallback: Lee-Ready Tick Rule CVD (Cumulative Volume Delta) &
  Institutional Absorption Divergence detection when DOM is unsupported by the broker.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("TradingAgent.OrderFlow")


@dataclass
class OrderFlowSnapshot:
    """Snapshot data representing order flow and liquidity metrics for a symbol."""
    symbol: str
    mode: str  # "REAL_DOM_L2" | "SYNTHETIC_TICK_RULE"
    order_book_imbalance: float  # [-1.0, 1.0]. Positive = Bid Dominant, Negative = Ask Dominant
    cvd_session_delta: float     # Cumulative session volume delta
    cvd_divergence: str         # "BEARISH_ABSORPTION" | "BULLISH_ABSORPTION" | "NONE"
    top_of_book_depth: Dict[str, Any] = field(default_factory=dict)
    vpin: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "mode": self.mode,
            "order_book_imbalance": round(self.order_book_imbalance, 4),
            "cvd_session_delta": round(self.cvd_session_delta, 2),
            "cvd_divergence": self.cvd_divergence,
            "top_of_book_depth": self.top_of_book_depth,
            "vpin": round(self.vpin, 4) if self.vpin is not None else None,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
        }


class OrderFlowEngine:
    """
    Mesin Order Flow & Likuiditas Dual-Mode.
    Mendeteksi ketersediaan DOM L2 MT5, atau beralih mulus ke Lee-Ready CVD.
    """

    def __init__(self, mt5_client=None, settings: Optional[dict] = None):
        self.mt5_client = mt5_client
        self.settings = settings or {}
        self._dom_supported_symbols: Dict[str, bool] = {}

    async def _check_and_subscribe_dom(self, symbol: str) -> bool:
        """Cek apakah broker mendukung DOM Level 2 untuk simbol ini."""
        if symbol in self._dom_supported_symbols:
            return self._dom_supported_symbols[symbol]
        if self.mt5_client is None:
            self._dom_supported_symbols[symbol] = False
            return False
        try:
            supported = await self.mt5_client.market_book_add(symbol)
            self._dom_supported_symbols[symbol] = bool(supported)
            return self._dom_supported_symbols[symbol]
        except Exception as e:
            logger.debug(f"DOM check error for {symbol}: {e}")
            self._dom_supported_symbols[symbol] = False
            return False

    async def _compute_dom_l2_snapshot(self, symbol: str) -> OrderFlowSnapshot:
        """Hitung Order Book Imbalance (OBI) dan kedalaman likuiditas dari DOM L2 riil."""
        if not self.mt5_client:
            return OrderFlowSnapshot(
                symbol=symbol,
                mode="REAL_DOM_L2",
                order_book_imbalance=0.0,
                cvd_session_delta=0.0,
                cvd_divergence="NONE",
                top_of_book_depth={"bid_depth": 0.0, "ask_depth": 0.0, "spread": 0.0},
            )

        try:
            books = await self.mt5_client.market_book_get(symbol)
            if books:
                def _val(item: Any, key: str, default: Any = 0.0) -> Any:
                    if isinstance(item, dict):
                        return item.get(key, default)
                    return getattr(item, key, default)

                # MT5 BookInfo: type (1=SELL, 2=BUY), price, volume
                bids = [b for b in books if _val(b, "type", 0) in (2,)]
                asks = [b for b in books if _val(b, "type", 0) in (1,)]

                bid_vol = sum(float(_val(b, "volume", _val(b, "volume_dbl", 0.0)) or 0.0) for b in bids)
                ask_vol = sum(float(_val(b, "volume", _val(b, "volume_dbl", 0.0)) or 0.0) for b in asks)
                tot = bid_vol + ask_vol
                obi = (bid_vol - ask_vol) / tot if tot > 0 else 0.0

                top_bid = max([float(_val(b, "price", 0.0)) for b in bids], default=0.0)
                top_ask = min([float(_val(b, "price", 0.0)) for b in asks], default=0.0)
                spread = round(top_ask - top_bid, 5) if top_ask > top_bid else 0.0

                return OrderFlowSnapshot(
                    symbol=symbol,
                    mode="REAL_DOM_L2",
                    order_book_imbalance=obi,
                    cvd_session_delta=round(bid_vol - ask_vol, 2),
                    cvd_divergence="NONE",
                    top_of_book_depth={"bid_depth": bid_vol, "ask_depth": ask_vol, "spread": spread},
                )
        except Exception as e:
            logger.debug(f"DOM computation error for {symbol}: {e}")

        return OrderFlowSnapshot(
            symbol=symbol,
            mode="REAL_DOM_L2",
            order_book_imbalance=0.0,
            cvd_session_delta=0.0,
            cvd_divergence="NONE",
            top_of_book_depth={"bid_depth": 0.0, "ask_depth": 0.0, "spread": 0.0},
        )

    async def _compute_tick_rule_cvd_snapshot(
        self, session: Optional[AsyncSession] = None, symbol: str = "", lookback: int = 200, df: Any = None, timeframe: str = "H1"
    ) -> OrderFlowSnapshot:
        """
        Kalkulasi Cumulative Volume Delta (CVD) berbasis Lee-Ready Tick Rule & deteksi absorpsi.
        Mendukung komputasi langsung dari DataFrame in-memory jika tersedia, atau query database PriceOHLCV.
        """
        prices: List[float] = []
        volumes: List[float] = []

        if df is not None and len(df) >= 2 and "close" in df:
            try:
                sub_df = df.tail(lookback)
                prices = [float(x) for x in sub_df["close"].values]
                if "volume" in sub_df:
                    volumes = [float(v or 1.0) for v in sub_df["volume"].values]
                else:
                    volumes = [1.0] * len(prices)
            except Exception as df_err:
                logger.debug(f"Error parsing in-memory df for CVD: {df_err}")

        if len(prices) < 2 and session is not None:
            try:
                from database.models import PriceOHLCV
                stmt = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == timeframe)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(lookback)
                )
                res = await session.execute(stmt)
                rows = res.scalars().all()
                if rows and len(rows) >= 2:
                    bars = list(reversed(rows))
                    prices = [float(b.close) for b in bars if hasattr(b, "close") and isinstance(getattr(b, "close", None), (int, float))]
                    volumes = [float(b.volume or 1.0) for b in bars if hasattr(b, "volume")]
            except Exception as db_err:
                logger.debug(f"Error loading OHLCV for CVD: {db_err}")

        if len(prices) < 2:
            return OrderFlowSnapshot(
                symbol=symbol,
                mode="SYNTHETIC_TICK_RULE",
                order_book_imbalance=0.0,
                cvd_session_delta=0.0,
                cvd_divergence="NONE",
                top_of_book_depth={"bid_depth": 0.0, "ask_depth": 0.0, "spread": 0.0},
                vpin=None,
            )

        cvd = 0.0
        cvd_series: List[float] = []
        prev_dir = 1

        for i in range(len(prices)):
            p = prices[i]
            vol = volumes[i] if i < len(volumes) else 1.0

            if i == 0:
                direction = 1
            else:
                prev_p = prices[i - 1]
                if p > prev_p:
                    direction = 1
                elif p < prev_p:
                    direction = -1
                else:
                    direction = prev_dir

            prev_dir = direction
            delta = direction * vol
            cvd += delta
            cvd_series.append(cvd)

        # Evaluasi divergensi (penyerapan institusi)
        half = len(prices) // 2
        p_first = float(np.mean(prices[:half]))
        p_second = float(np.mean(prices[half:]))
        cvd_first = float(np.mean(cvd_series[:half]))
        cvd_second = float(np.mean(cvd_series[half:]))

        divergence = "NONE"
        if p_second > p_first and cvd_second < cvd_first:
            divergence = "BEARISH_ABSORPTION"
        elif p_second < p_first and cvd_second > cvd_first:
            divergence = "BULLISH_ABSORPTION"

        tot_vol = sum(volumes) if volumes else 1.0
        synthetic_obi = (cvd / tot_vol) if tot_vol > 0 else 0.0
        synthetic_obi = max(-1.0, min(1.0, synthetic_obi))

        # Calculate VPIN if asset is BTCUSD or XAUUSD
        vpin_val: Optional[float] = None
        if any(sym_tag in symbol.upper() for sym_tag in ("BTC", "XAU")) and len(prices) >= 20:
            try:
                import pandas as pd
                from indicators.microstructure import compute_vpin
                t_df = pd.DataFrame({"price": prices, "volume": volumes})
                bucket_vol = float(np.sum(volumes) / 50.0) if np.sum(volumes) > 0 else 1.0
                vpin_val = round(compute_vpin(t_df, bucket_volume=bucket_vol), 4)
            except Exception as vpin_err:
                logger.debug(f"VPIN computation failed for {symbol}: {vpin_err}")

        return OrderFlowSnapshot(
            symbol=symbol,
            mode="SYNTHETIC_TICK_RULE",
            order_book_imbalance=synthetic_obi,
            cvd_session_delta=round(cvd, 2),
            cvd_divergence=divergence,
            top_of_book_depth={"bid_depth": max(0.0, cvd), "ask_depth": max(0.0, -cvd), "spread": 0.0},
            vpin=vpin_val,
        )

    async def analyze_order_flow(
        self, session: Optional[AsyncSession] = None, symbol: str = "", lookback: int = 200, df: Any = None, timeframe: str = "H1"
    ) -> OrderFlowSnapshot:
        """Entry point utama: coba DOM L2 jika broker mendukung, atau beralih ke Lee-Ready CVD."""
        is_dom_avail = await self._check_and_subscribe_dom(symbol)
        if is_dom_avail:
            return await self._compute_dom_l2_snapshot(symbol)
        return await self._compute_tick_rule_cvd_snapshot(session, symbol, lookback, df=df, timeframe=timeframe)


async def fetch_latest_order_flow(session: AsyncSession, symbol: str) -> OrderFlowSnapshot:
    """Ambil snapshot order flow terbaru dari database atau hitung on-the-fly."""
    from database.models import TechnicalIndicator
    row = (await session.execute(
        select(TechnicalIndicator)
        .where(TechnicalIndicator.symbol == symbol)
        .where(TechnicalIndicator.indicator_name == "ORDER_FLOW_SNAPSHOT")
        .order_by(TechnicalIndicator.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()

    if row and row.value_json:
        try:
            data = json.loads(row.value_json)
            return OrderFlowSnapshot(
                symbol=symbol,
                mode=data.get("mode", "SYNTHETIC_TICK_RULE"),
                order_book_imbalance=float(data.get("order_book_imbalance", 0.0)),
                cvd_session_delta=float(data.get("cvd_session_delta", 0.0)),
                cvd_divergence=data.get("cvd_divergence", "NONE"),
                top_of_book_depth=data.get("top_of_book_depth", {}),
                vpin=float(data["vpin"]) if data.get("vpin") is not None else None,
            )
        except Exception:
            pass

    engine = OrderFlowEngine()
    return await engine.analyze_order_flow(session, symbol)
