# ==============================================================================
# File: application/services/order_flow_service.py
# Monika Order Flow Application Service
# ==============================================================================

"""
Order Flow Application Service.

Orchestrates order flow retrieval and calculations by reading cached snapshots
and historical tick/OHLCV data from the database, dispatching calculations
to pure domain models in monika.domain.indicators.order_flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.indicators.order_flow import OrderFlowEngine, OrderFlowSnapshot
from monika.infrastructure.database.models import PriceOHLCV, TechnicalIndicator

logger = logging.getLogger("TradingAgent.Services.OrderFlow")


class OrderFlowService:
    """Application Service for Order Flow querying and execution."""

    @staticmethod
    async def fetch_latest_order_flow(session: Any, symbol: str) -> OrderFlowSnapshot:
        """Ambil snapshot order flow terbaru dari database atau hitung on-the-fly."""
        row = None
        if session is not None:
            try:
                res = await session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.indicator_name == "ORDER_FLOW_SNAPSHOT")
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )
                row = res.scalar_one_or_none()
            except Exception as exc:
                logger.debug(f"Error fetching cached order flow for {symbol}: {exc}")

        if row and getattr(row, "value_json", None):
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


# Module-level convenience function
fetch_latest_order_flow = OrderFlowService.fetch_latest_order_flow
