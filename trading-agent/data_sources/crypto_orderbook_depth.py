# ==============================================================================
# File: data_sources/crypto_orderbook_depth.py
# Monika Institutional Level-2 Crypto Orderbook Depth & Liquidity Engine
# ==============================================================================

"""
Level-2 Orderbook Depth & Microstructure Liquidity Ladder for Crypto Assets.

Fetches real-time L2 orderbooks from public exchange REST endpoints (Binance & OKX)
without requiring API keys. Computes:
1. Tightest Bid-Ask spread in basis points (bps)
2. Normalized Depth Imbalance Score [-1.0, 1.0] across top 20 levels
3. Market impact slippage simulation for $10k, $50k, and $100k taker orders
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.CryptoOrderbookDepth")

DEFAULT_TIMEOUT = 5.0
DEFAULT_USER_AGENT = "Monika-Quant-Agent/1.0 (Institutional Microstructure Engine)"


@dataclass(frozen=True, slots=True)
class OrderbookSnapshot:
    symbol: str
    exchange: str
    timestamp: str
    best_bid: float
    best_ask: float
    mid_price: float
    spread_bps: float
    imbalance_score: float  # [-1.0 = heavy ask pressure, +1.0 = heavy bid support]
    bid_liquidity_usd: float
    ask_liquidity_usd: float
    slippage_estimates: Dict[str, Dict[str, float]]  # e.g. {"10k": {"buy_slip_bps": 1.2, "sell_slip_bps": 1.1}}
    bids: List[Tuple[float, float]] = field(default_factory=list)  # (price, quantity)
    asks: List[Tuple[float, float]] = field(default_factory=list)


class CryptoOrderbookDepth:
    """Institutional Level-2 orderbook analyzer for BTC and ETH."""

    SYMBOL_MAP_BINANCE = {
        "BTCUSD": "BTCUSDT",
        "BTCUSDT": "BTCUSDT",
        "ETHUSD": "ETHUSDT",
        "ETHUSDT": "ETHUSDT",
    }

    SYMBOL_MAP_OKX = {
        "BTCUSD": "BTC-USDT",
        "BTCUSDT": "BTC-USDT",
        "ETHUSD": "ETH-USDT",
        "ETHUSDT": "ETH-USDT",
    }

    @classmethod
    def _fetch_url_json(cls, url: str) -> Optional[dict]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"Orderbook fetch failed for {url}: {e}")
        return None

    @classmethod
    def _simulate_market_order_impact(
        cls, book_side: List[Tuple[float, float]], target_usd: float, is_buy: bool
    ) -> float:
        """Simulates walking the orderbook to fill target_usd and calculates slippage in bps."""
        if not book_side or target_usd <= 0:
            return 0.0

        remaining_usd = target_usd
        total_qty = 0.0
        spent_usd = 0.0
        best_price = book_side[0][0]

        for price, qty in book_side:
            level_usd = price * qty
            if remaining_usd <= level_usd:
                fill_qty = remaining_usd / price
                spent_usd += remaining_usd
                total_qty += fill_qty
                remaining_usd = 0.0
                break
            else:
                spent_usd += level_usd
                total_qty += qty
                remaining_usd -= level_usd

        if remaining_usd > 0:
            # Depth exhausted: assign severe penalty
            return 50.0

        avg_fill_price = spent_usd / total_qty
        if is_buy:
            slip_bps = ((avg_fill_price - best_price) / best_price) * 10000.0
        else:
            slip_bps = ((best_price - avg_fill_price) / best_price) * 10000.0

        return round(max(float(slip_bps), 0.0), 2)

    @classmethod
    def fetch_snapshot_sync(cls, symbol: str = "BTCUSD", limit: int = 20) -> Optional[OrderbookSnapshot]:
        norm_sym = symbol.upper().replace("/", "")
        binance_sym = cls.SYMBOL_MAP_BINANCE.get(norm_sym, "BTCUSDT")

        # 1. Try Binance Depth
        binance_url = f"https://api.binance.com/api/v3/depth?symbol={binance_sym}&limit={limit}"
        data = cls._fetch_url_json(binance_url)

        exchange = "Binance"
        bids_raw: list = []
        asks_raw: list = []

        if data and "bids" in data and "asks" in data:
            bids_raw = data["bids"]
            asks_raw = data["asks"]
        else:
            # 2. Fallback to OKX Books
            okx_sym = cls.SYMBOL_MAP_OKX.get(norm_sym, "BTC-USDT")
            okx_url = f"https://www.okx.com/api/v5/market/books?instId={okx_sym}&sz={limit}"
            okx_data = cls._fetch_url_json(okx_url)
            if okx_data and okx_data.get("data"):
                exchange = "OKX"
                bids_raw = okx_data["data"][0].get("bids", [])
                asks_raw = okx_data["data"][0].get("asks", [])

        if not bids_raw or not asks_raw:
            return None

        bids = [(float(p[0]), float(p[1])) for p in bids_raw]
        asks = [(float(p[0]), float(p[1])) for p in asks_raw]

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid_price = (best_bid + best_ask) / 2.0
        spread_bps = round(((best_ask - best_bid) / mid_price) * 10000.0, 3)

        bid_liquidity_usd = sum(p * q for p, q in bids)
        ask_liquidity_usd = sum(p * q for p, q in asks)
        total_liq = bid_liquidity_usd + ask_liquidity_usd

        imbalance_score = round((bid_liquidity_usd - ask_liquidity_usd) / max(total_liq, 1.0), 3)

        # Slippage ladder simulation
        slippage_estimates = {}
        for tier_name, tier_usd in [("10k", 10000.0), ("50k", 50000.0), ("100k", 100000.0)]:
            buy_slip = cls._simulate_market_order_impact(asks, tier_usd, is_buy=True)
            sell_slip = cls._simulate_market_order_impact(bids, tier_usd, is_buy=False)
            slippage_estimates[tier_name] = {"buy_slip_bps": buy_slip, "sell_slip_bps": sell_slip}

        return OrderbookSnapshot(
            symbol=norm_sym,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc).isoformat(),
            best_bid=best_bid,
            best_ask=best_ask,
            mid_price=mid_price,
            spread_bps=spread_bps,
            imbalance_score=imbalance_score,
            bid_liquidity_usd=round(bid_liquidity_usd, 2),
            ask_liquidity_usd=round(ask_liquidity_usd, 2),
            slippage_estimates=slippage_estimates,
            bids=bids,
            asks=asks,
        )

    @classmethod
    async def fetch_snapshot(cls, symbol: str = "BTCUSD", limit: int = 20) -> Optional[OrderbookSnapshot]:
        return await asyncio.to_thread(cls.fetch_snapshot_sync, symbol, limit)
