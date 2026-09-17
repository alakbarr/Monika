# ==============================================================================
# File: execution/service/risk_evaluator.py
# ==============================================================================

import asyncio
import json
import logging
import math
import uuid
import time
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from unittest.mock import MagicMock

from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

import database.db as _db_mod
from database.safe_ops import safe_commit
from database.models import (
    AssetAnalysis, Position, OrderLog, ActivityLog, RiskState, SystemConfig,
    Order, OrderStatus, OrderEvent, PaperTradeRecord
)
from execution.mt5_client import MT5Client
from execution.broker_adapter import BrokerAdapter, MT5LiveAdapter
from risk.position_sizing import PositionSizer, SizingResult
from risk.risk_gate import RiskGate
from utils.infra.notifier import AgentNotifier

def get_session(*args, **kwargs):
    es = sys.modules.get("execution.execution_service")
    if es and hasattr(es, "get_session"):
        return es.get_session(*args, **kwargs)
    return _db_mod.get_session(*args, **kwargs)

def transactional_advisory_lock(*args, **kwargs):
    es = sys.modules.get("execution.execution_service")
    if es and hasattr(es, "transactional_advisory_lock"):
        return es.transactional_advisory_lock(*args, **kwargs)
    return _db_mod.transactional_advisory_lock(*args, **kwargs)


from execution.service.base import _ExecutionServiceMixinBase

logger = logging.getLogger("TradingAgent.ExecutionService.RiskEvaluator")

class RiskEvaluatorMixin(_ExecutionServiceMixinBase):
    """Mixin untuk evaluasi risiko, perhitungan equity/margin, dan kuota open positions."""

    async def _count_open_positions(self, session, symbol: Optional[str] = None) -> int:
        """Count currently open positions in database."""
        from sqlalchemy import select, func
        from database.models import Position
        try:
            stmt = select(func.count(Position.id)).where(Position.status == 'open')
            if symbol:
                stmt = stmt.where(Position.symbol == symbol)
            result = await session.execute(stmt)
            count = result.scalar_one_or_none() if hasattr(result, "scalar_one_or_none") else getattr(result, "scalar", lambda: 0)()
            if asyncio.iscoroutine(count):
                count = await count
            return int(count or 0)
        except Exception as e:
            logger.debug(f"Count open positions error (non-fatal): {e}")
            return 0


    async def _get_dynamic_risk_percent(self, session: AsyncSession, symbol: str, base_risk_pct: float) -> float:
        """
        Sesuaikan persentase risiko secara dinamis berdasarkan performa terakhir simbol.
        Menggunakan kriteria half-Kelly sebagai batas atas.
        """
        try:
            risk_cfg = self.settings.get("trading", {}).get("risk", {})
            if not risk_cfg.get("dynamic_risk_scaling", False):
                return base_risk_pct
                
            from utils.analytics.paper_tracker import PaperTracker
            tracker = PaperTracker(self.settings)
            stats = await tracker.get_statistics(session)
            
            by_symbol = stats.get("by_symbol", {})
            min_pct = risk_cfg.get("dynamic_risk_min_pct", 0.5)
            max_pct = risk_cfg.get("dynamic_risk_max_pct", 2.0)
            min_trades = risk_cfg.get("dynamic_risk_lookback_trades", 10)
            
            sym_stats = by_symbol.get(symbol, {})
            trades = sym_stats.get("trades", 0)
            
            if trades < min_trades:
                return base_risk_pct
                
            win_rate = sym_stats.get("win_rate", 50) / 100
            rr_ratio = risk_cfg.get("min_rr_ratio", 1.3)
            kelly = win_rate - (1 - win_rate) / rr_ratio
            
            if kelly <= 0:
                return min_pct
                
            half_kelly_pct = kelly * 50
            scaled = max(min_pct, min(max_pct, half_kelly_pct))
            
            if abs(scaled - base_risk_pct) > 0.2:
                logger.info(
                    f"Dynamic risk scaling for {symbol}: "
                    f"{base_risk_pct}% → {scaled:.2f}% "
                    f"(WR={win_rate:.0%}, Kelly={kelly:.2f}, trades={trades})"
                )
                
            return round(scaled, 2)
        except Exception as e:
            logger.debug(f"Dynamic risk scaling failed (non-fatal), using default: {e}")
            return base_risk_pct


    async def _get_current_price(self, symbol: str, direction: str = "buy") -> tuple[float, bool, float]:
        """
        Get current ask (for buy) or bid (for sell) from MT5.
        Returns (price, is_stale, age_seconds).
        is_stale=True means the price came from DB fallback and may be outdated.
        """
        try:
            if hasattr(self, 'broker_adapter') and self.broker_adapter is not None:
                tick = await self.broker_adapter.get_tick(symbol)
            else:
                tick = await self.mt5.get_current_price(symbol)
            if tick:
                dir_clean = (direction or "").lower().strip()
                price = tick['ask'] if dir_clean == 'buy' else tick['bid']
                
                fetched_at = tick.get('fetched_at')
                if fetched_at is not None:
                    age_seconds = abs(time.time() - fetched_at)
                    if age_seconds > 120:
                        return price, True, age_seconds
                    return price, False, 0.0
                
                now = clock.now()
                tick_time = tick.get('time')
                if tick_time:
                    if tick_time.tzinfo is None:
                        tick_time = tick_time.replace(tzinfo=timezone.utc)
                    age_seconds = (now - tick_time).total_seconds()
                    if 0 < age_seconds > 120:
                        return price, True, age_seconds
                        
                return price, False, 0.0
        except Exception as e:
            logger.warning(f"Cannot get live price for {symbol}: {e}")
        
        # Fallback: use last known close from DB
        async with get_session() as session:
            from database.models import PriceOHLCV
            bar = (await session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            if bar:
                now = datetime.now(timezone.utc)
                bar_ts = bar.timestamp
                if bar_ts.tzinfo is None:
                    bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                age_seconds = (now - bar_ts).total_seconds()
                return bar.close, True, age_seconds
                
        return 0.0, True, float('inf')


    async def _get_equity(self) -> Optional[float]:
        """Get current account equity from broker adapter or MT5."""
        try:
            if hasattr(self, 'broker_adapter') and self.broker_adapter is not None:
                info = await self.broker_adapter.get_account_info()
            else:
                info = await self.mt5.get_account_info()
            if info:
                return info.get('equity')
        except Exception as e:
            logger.warning(f"Cannot get account equity: {e}")
        return None

