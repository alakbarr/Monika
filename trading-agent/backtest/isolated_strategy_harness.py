"""
IsolatedStrategyBacktestHarness: Institutional Isolated Strategy Backtesting & Walk-Forward Engine.

Provides strictly isolated, zero-lookahead historical bar-by-bar evaluation for any EdgeStrategy subclass.
Features:
1. Zero Lookahead Enforcement: Slices data temporally as of current bar timestamp.
2. Multi-Timeframe Alignment: Accurately feeds H1, M15, H4, and D1 candles using session.info["candle_cache"].
3. Simulation-to-Live Parity: Computes stops/targets matching EdgeStrategyRunner (ATR/ADR intraday levels when unspecified).
4. Realistic Friction Profile: Asset-specific spreads, volatility slippage, and commissions.
5. Institutional Statistical Gating: Integrates Walk-Forward Efficiency (WFE), Deflated Sharpe Ratio (DSR),
   Probabilistic Sharpe Ratio (PSR), and full AlphaValidation (2.0x cost stress, directional bias, split-half consistency).
"""

import math
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Type, Union

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal, CandleDict
from backtest.outcome_evaluator import ASSET_FRICTION_PROFILE
from backtest.statistical_tests import (
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
    compute_sample_moments,
)
from backtest.alpha_validation import validate_alpha, AlphaValidation
from database.models import PriceOHLCV, BacktestTrade

logger = logging.getLogger("TradingAgent.IsolatedStrategyHarness")


@dataclass
class StrategyTradeRecord:
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    stop_loss: float
    take_profit: float
    pnl_pct: float
    exit_reason: str
    bars_held: int
    confidence: float
    strategy_id: str
    r_multiple: float = 0.0


@dataclass
class HarnessMetrics:
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    total_pnl_pct: float
    trade_returns: List[float] = field(default_factory=list)
    trades: List[StrategyTradeRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_pnl_pct": self.total_pnl_pct,
        }


def resample_candles(h1_candles: List[CandleDict], factor: int) -> List[CandleDict]:
    """Resamples H1 candles into higher timeframe (e.g. factor=4 for H4, factor=24 for D1)."""
    if not h1_candles:
        return []
    
    first_time = h1_candles[0].get("time")
    if isinstance(first_time, datetime) and factor in (4, 24):
        chunks = []
        current_chunk = []
        current_key = None
        for c in h1_candles:
            t = c.get("time")
            if not isinstance(t, datetime):
                current_chunk.append(c)
                continue
            key = (t.year, t.month, t.day) if factor == 24 else (t.year, t.month, t.day, t.hour // 4)
            if current_key is None:
                current_key = key
                current_chunk.append(c)
            elif key == current_key:
                current_chunk.append(c)
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [c]
                current_key = key
        if current_chunk:
            chunks.append(current_chunk)
    else:
        chunks = [h1_candles[i : i + factor] for i in range(0, len(h1_candles), factor)]

    res = []
    for chunk in chunks:
        if not chunk:
            continue
        c_open = chunk[0].open
        c_high = max(c.high for c in chunk)
        c_low = min(c.low for c in chunk)
        c_close = chunk[-1].close
        c_vol = sum(getattr(c, "volume", 0.0) or 0.0 for c in chunk)
        res.append(CandleDict({
            "timestamp": chunk[-1].timestamp,
            "time": chunk[-1].get("time"),
            "open": float(c_open),
            "high": float(c_high),
            "low": float(c_low),
            "close": float(c_close),
            "volume": float(c_vol),
        }))
    return res


class MockIndicatorRow:
    def __init__(self, value_json: str, timestamp: Optional[datetime] = None):
        self.value_json = value_json
        self.timestamp = timestamp or datetime.now(timezone.utc)


class MockStructureBreakRow:
    def __init__(self, direction: str, formed_at: Optional[datetime] = None):
        self.direction = direction
        self.formed_at = formed_at or datetime.now(timezone.utc)


class ZeroLookaheadSliceSession:
    """
    Proxy AsyncSession providing strictly zero-lookahead temporal slices across multiple timeframes.
    Supports session.info['candle_cache'] and smart dispatching of direct session.execute(stmt) queries:
    1. Synchronized multi-timeframe candles (H1, M15, H4, D1).
    2. Scalar float series if PriceOHLCV.close or volume is queried directly.
    3. Simulates TechnicalIndicator rows (EMA, ATR) and StructureBreak rows from historical candle cache.
    """

    def __init__(
        self,
        candle_cache: Dict[tuple[str, str], List[CandleDict]],
        as_of_time: datetime,
        symbol: str = "EURUSD",
    ):
        self.candle_cache = candle_cache
        self.as_of_time = as_of_time
        self.symbol = symbol.upper()
        self.info = {"candle_cache": dict(candle_cache)}

    async def execute(self, stmt, *args, **kwargs):
        import json as _json
        import re as _re

        class _SliceScalarResult:
            def __init__(self, data):
                self._data = data

            def scalars(self):
                return self

            def all(self):
                return list(reversed(self._data))

            def scalar_one_or_none(self):
                return self._data[-1] if self._data else None

            def first(self):
                return self._data[-1] if self._data else None

        stmt_str = str(stmt).upper()
        h1_candles = self.candle_cache.get((self.symbol, "H1"), [])
        last_close = float(h1_candles[-1].close) if h1_candles else 1.0

        # 1. TechnicalIndicator query dispatch
        if "TECHNICALINDICATOR" in stmt_str or "INDICATOR" in stmt_str:
            if "ATR" in stmt_str:
                atr_val = last_close * 0.005
                if len(h1_candles) >= 15:
                    trs = [
                        max(
                            h1_candles[j].high - h1_candles[j].low,
                            abs(h1_candles[j].high - h1_candles[j - 1].close),
                            abs(h1_candles[j].low - h1_candles[j - 1].close),
                        )
                        for j in range(1, len(h1_candles))
                    ]
                    atr_val = float(np.mean(trs[-14:])) if trs else atr_val
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"atr": round(atr_val, 5), "value": round(atr_val, 5)}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

            elif "EMA" in stmt_str:
                m = _re.search(r"EMA_(\d+)", stmt_str)
                period = int(m.group(1)) if m else 20
                if len(h1_candles) >= period:
                    closes = [float(c.close) for c in h1_candles]
                    alpha = 2.0 / (period + 1.0)
                    ema = closes[0]
                    for c in closes[1:]:
                        ema = alpha * c + (1.0 - alpha) * ema
                    ema_val = round(ema, 5)
                else:
                    ema_val = round(last_close, 5)
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"value": ema_val}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

            elif "SMA" in stmt_str:
                m = _re.search(r"SMA_(\d+)", stmt_str)
                period = int(m.group(1)) if m else 20
                if len(h1_candles) >= period:
                    sma_val = round(float(np.mean([float(c.close) for c in h1_candles[-period:]])), 5)
                else:
                    sma_val = round(last_close, 5)
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"value": sma_val, "sma": sma_val}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

            elif "RSI" in stmt_str:
                m = _re.search(r"RSI_(\d+)", stmt_str)
                period = int(m.group(1)) if m else 14
                if len(h1_candles) >= period + 1:
                    closes = [float(c.close) for c in h1_candles]
                    diffs = [closes[k] - closes[k - 1] for k in range(1, len(closes))]
                    recent_diffs = diffs[-period:]
                    gains = [d for d in recent_diffs if d > 0]
                    losses = [-d for d in recent_diffs if d < 0]
                    avg_gain = sum(gains) / period if gains else 0.0
                    avg_loss = sum(losses) / period if losses else 0.0
                    if avg_loss == 0.0:
                        rsi_val = 100.0 if avg_gain > 0 else 50.0
                    else:
                        rs = avg_gain / avg_loss
                        rsi_val = round(100.0 - (100.0 / (1.0 + rs)), 2)
                else:
                    rsi_val = 50.0
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"value": rsi_val, "rsi": rsi_val}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

            elif "BOLLINGER" in stmt_str or "BB" in stmt_str:
                period = 20
                if len(h1_candles) >= period:
                    closes = [float(c.close) for c in h1_candles[-period:]]
                    mean_val = float(np.mean(closes))
                    std_val = float(np.std(closes, ddof=1)) if len(closes) > 1 else 0.0
                    upper = round(mean_val + 2.0 * std_val, 5)
                    lower = round(mean_val - 2.0 * std_val, 5)
                    mid = round(mean_val, 5)
                else:
                    mid = round(last_close, 5)
                    upper = round(last_close * 1.01, 5)
                    lower = round(last_close * 0.99, 5)
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"value": mid, "middle": mid, "upper": upper, "lower": lower}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

            elif "ADX" in stmt_str:
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"value": 25.0, "adx": 25.0}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

            else:
                mock_row = MockIndicatorRow(
                    value_json=_json.dumps({"value": last_close}),
                    timestamp=self.as_of_time,
                )
                return _SliceScalarResult([mock_row])

        # 2. StructureBreak query dispatch
        if "STRUCTUREBREAK" in stmt_str or "STRUCTURE_BREAK" in stmt_str:
            if len(h1_candles) >= 5:
                direction = "bullish" if h1_candles[-1].close >= h1_candles[-5].close else "bearish"
                mock_break = MockStructureBreakRow(direction=direction, formed_at=self.as_of_time)
                return _SliceScalarResult([mock_break])
            return _SliceScalarResult([])

        # 3. Determine timeframe from stmt
        tf = "H1"
        for candidate_tf in ("M15", "H4", "D1", "H1"):
            if f"'{candidate_tf}'" in stmt_str or f'"{candidate_tf}"' in stmt_str:
                tf = candidate_tf
                break

        candles = self.candle_cache.get((self.symbol, tf))
        if not candles:
            if tf == "H4":
                candles = resample_candles(h1_candles, 4)
            elif tf == "D1":
                candles = resample_candles(h1_candles, 24)
            elif tf == "M15":
                candles = h1_candles
            else:
                candles = h1_candles

        # If scalar column like .close was queried (e.g. tsm_momentum):
        if "PRICEOHLCV.CLOSE" in stmt_str or (".CLOSE" in stmt_str and ".HIGH" not in stmt_str and ".OPEN" not in stmt_str):
            float_closes = [float(c.close) for c in candles]
            return _SliceScalarResult(float_closes)
        elif "PRICEOHLCV.VOLUME" in stmt_str and ".CLOSE" not in stmt_str:
            float_vols = [float(getattr(c, "volume", 0.0) or 0.0) for c in candles]
            return _SliceScalarResult(float_vols)

        return _SliceScalarResult(candles)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class IsolatedStrategyBacktestHarness:
    """
    Isolated Backtesting & Walk-Forward Optimization Harness for EdgeStrategy instances.
    Enforces deterministic clock freezing, multi-timeframe alignment, and conservative execution.
    """

    def __init__(
        self,
        strategy: Optional[Union[Type[EdgeStrategy], EdgeStrategy]] = None,
        symbol: str = "EURUSD",
        settings: Optional[Dict[str, Any]] = None,
        strategy_cls: Optional[Union[Type[EdgeStrategy], EdgeStrategy]] = None,
        strategy_params: Optional[Dict[str, Any]] = None,
        custom_friction_profile: Optional[Dict[str, Dict[str, float]]] = None,
        fail_fast_on_error: bool = False,
    ):
        target_strat = strategy if strategy is not None else strategy_cls
        if target_strat is None:
            raise ValueError("Either strategy or strategy_cls must be provided.")
        self.settings = dict(settings or {})
        self.strategy_params = dict(strategy_params or {})
        self.symbol = symbol.upper()
        self.strategy_cls = target_strat if isinstance(target_strat, type) else target_strat.__class__
        self.strategy_instance = target_strat if not isinstance(target_strat, type) else None
        self.fail_fast_on_error = fail_fast_on_error

        # Build friction profile
        friction_dict = dict(ASSET_FRICTION_PROFILE)
        if custom_friction_profile:
            friction_dict.update(custom_friction_profile)
        self.friction = friction_dict.get(self.symbol, {"spread_pips": 1.5, "slippage_pips": 0.5})

        # Pip size determination
        if any(c in self.symbol for c in ("JPY", "XAU", "XTI", "XBR")):
            self.pip_size = 0.01
        elif any(c in self.symbol for c in ("BTC", "ETH", "SOL")):
            self.pip_size = 1.0
        else:
            self.pip_size = 0.0001

        self.spread_cost = self.friction.get("spread_pips", 1.5) * self.pip_size
        self.slippage_cost = self.friction.get("slippage_pips", 0.5) * self.pip_size

    def _get_strategy_instance(self) -> EdgeStrategy:
        if self.strategy_instance is not None:
            inst = self.strategy_instance
        else:
            try:
                inst = self.strategy_cls(self.settings)
            except TypeError:
                try:
                    inst = self.strategy_cls(**self.settings)
                except TypeError:
                    inst = self.strategy_cls()

        if self.strategy_params and hasattr(inst, "cfg"):
            inst.cfg = dict(getattr(inst, "cfg", {}))
            inst.cfg.update(self.strategy_params)
        return inst

    async def fetch_historical_candles(
        self,
        session: AsyncSession,
        timeframe: str = "H1",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1500,
    ) -> List[CandleDict]:
        """Fetch historical candles in strictly chronological order."""
        stmt = select(PriceOHLCV).where(
            PriceOHLCV.symbol == self.symbol,
            PriceOHLCV.timeframe == timeframe.upper(),
        )
        if start_date:
            stmt = stmt.where(PriceOHLCV.timestamp >= start_date)
        if end_date:
            stmt = stmt.where(PriceOHLCV.timestamp <= end_date)
        stmt = stmt.order_by(PriceOHLCV.timestamp.desc()).limit(limit)

        rows = (await session.execute(stmt)).scalars().all()
        if len(rows) > 1 and hasattr(rows[0], "timestamp") and hasattr(rows[-1], "timestamp"):
            if rows[0].timestamp and rows[-1].timestamp and rows[0].timestamp > rows[-1].timestamp:
                chronological_rows = list(reversed(rows))
            else:
                chronological_rows = list(rows)
        else:
            chronological_rows = list(rows)

        candles = [
            CandleDict({
                "timestamp": r.timestamp.isoformat() if hasattr(r, "timestamp") and hasattr(r.timestamp, "isoformat") else str(getattr(r, "timestamp", "")),
                "time": getattr(r, "timestamp", None),
                "open": float(getattr(r, "open", 0.0)),
                "high": float(getattr(r, "high", 0.0)),
                "low": float(getattr(r, "low", 0.0)),
                "close": float(getattr(r, "close", 0.0)),
                "volume": float(getattr(r, "volume", 0.0) or 0.0),
            })
            for r in chronological_rows
        ]
        return candles

    def _calculate_atr(self, candles: List[CandleDict], period: int = 14) -> float:
        """Compute Wilder's ATR over a candle slice."""
        if len(candles) < period + 1:
            return float(candles[-1].close) * 0.005 if candles else 0.001
        tr_list = []
        for j in range(1, len(candles)):
            c = candles[j]
            prev_c = candles[j - 1]
            tr = max(
                c.high - c.low,
                abs(c.high - prev_c.close),
                abs(c.low - prev_c.close),
            )
            tr_list.append(tr)
        return float(np.mean(tr_list[-period:])) if tr_list else float(candles[-1].close) * 0.005

    def _resolve_sl_tp(
        self,
        sig: EdgeSignal,
        entry_price: float,
        atr: float,
        strat_instance: Optional[EdgeStrategy] = None,
    ) -> tuple[float, float]:
        """Resolves Stop Loss and Take Profit levels respecting dynamic strategy params."""
        if sig.stop_loss is not None and sig.take_profit is not None:
            return float(sig.stop_loss), float(sig.take_profit)

        sl_mult = None
        tp_mult = None
        if isinstance(sig.meta, dict):
            sl_mult = sig.meta.get("sl_atr_multiplier")
            tp_mult = sig.meta.get("tp_sl_multiplier")
        if sl_mult is None and self.strategy_params:
            sl_mult = self.strategy_params.get("sl_atr_multiplier")
        if tp_mult is None and self.strategy_params:
            tp_mult = self.strategy_params.get("tp_sl_multiplier")
        if sl_mult is None and strat_instance and hasattr(strat_instance, "cfg"):
            sl_mult = strat_instance.cfg.get("sl_atr_multiplier")
        if tp_mult is None and strat_instance and hasattr(strat_instance, "cfg"):
            tp_mult = strat_instance.cfg.get("tp_sl_multiplier")

        exit_style = getattr(sig, "exit_style", "intraday_adr")
        if exit_style == "trend_trailing":
            default_sl = 1.5
            default_tp_ratio = 2.333
        else:
            default_sl = 1.2
            default_tp_ratio = 2.0

        sl_atr = float(sl_mult) if sl_mult is not None else default_sl
        tp_ratio = float(tp_mult) if tp_mult is not None else default_tp_ratio

        sl_dist = atr * sl_atr
        tp_dist = sl_dist * tp_ratio

        if sig.direction == "buy":
            sl = entry_price - sl_dist
            tp = entry_price + tp_dist
        else:
            sl = entry_price + sl_dist
            tp = entry_price - tp_dist

        return sl, tp

    def _calculate_trade_pnl(
        self,
        direction: str,
        entry_price: float,
        exit_price: float,
        sl: float,
    ) -> tuple[float, float, float]:
        """
        Calculates risk-normalized return (R-multiple) and standardized equity return.
        1R = initial distance to stop loss.
        Standard return normalized to 1.0% equity risk per trade.
        Returns: (equity_return, pnl_pct, r_multiple)
        """
        price_diff = (exit_price - entry_price) if direction == "buy" else (entry_price - exit_price)
        risk_dist = abs(entry_price - sl)
        if risk_dist > 1e-7:
            r_multiple = price_diff / risk_dist
        else:
            r_multiple = (price_diff / entry_price) * 100.0 if entry_price > 0 else 0.0

        equity_return = r_multiple * 0.01
        pnl_pct = r_multiple * 1.0
        return round(equity_return, 5), round(pnl_pct, 3), round(r_multiple, 3)

    async def run_simulation(
        self,
        session: AsyncSession,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        lookback_candles: int = 1000,
        min_candles: int = 60,
        burn_in_bars: int = 20,
        max_hold_bars: int = 24,
    ) -> HarnessMetrics:
        """
        Executes zero-lookahead historical bar-by-bar simulation for this strategy.
        Enforces frozen simulated clock per bar stepping to eliminate lookahead bias.
        """
        from utils.clock import frozen_time

        primary_candles = await self.fetch_historical_candles(
            session=session,
            timeframe="H1",
            start_date=start_date,
            end_date=end_date,
            limit=lookback_candles,
        )

        if len(primary_candles) < min_candles:
            logger.info(
                f"[IsolatedHarness] Insufficient H1 candles for {self.symbol} "
                f"({len(primary_candles)} < {min_candles}). Returning empty metrics."
            )
            return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        m15_candles = await self.fetch_historical_candles(
            session=session, timeframe="M15", start_date=start_date, end_date=end_date, limit=lookback_candles * 4
        )
        h4_candles = await self.fetch_historical_candles(
            session=session, timeframe="H4", start_date=start_date, end_date=end_date, limit=max(100, lookback_candles // 4)
        )
        if not h4_candles:
            h4_candles = resample_candles(primary_candles, 4)

        d1_candles = resample_candles(primary_candles, 24)

        strat_instance = self._get_strategy_instance()
        trade_records: List[StrategyTradeRecord] = []
        trade_returns: List[float] = []

        i = burn_in_bars
        while i < len(primary_candles) - 5:
            current_bar = primary_candles[i]
            cur_time = current_bar.get("time") or datetime.now(timezone.utc)

            h1_slice = primary_candles[: i + 1]
            m15_slice = [c for c in m15_candles if (c.get("time") or cur_time) <= cur_time]
            h4_slice = [c for c in h4_candles if (c.get("time") or cur_time) <= cur_time]
            d1_slice = [c for c in d1_candles if (c.get("time") or cur_time) <= cur_time]

            slice_cache: Dict[tuple[str, str], List[CandleDict]] = {
                (self.symbol, "H1"): h1_slice,
                (self.symbol, "M15"): m15_slice if m15_slice else h1_slice,
                (self.symbol, "H4"): h4_slice if h4_slice else h1_slice,
                (self.symbol, "D1"): d1_slice if d1_slice else h1_slice,
            }

            slice_session = ZeroLookaheadSliceSession(slice_cache, as_of_time=cur_time, symbol=self.symbol)

            sig: Optional[EdgeSignal] = None
            try:
                # Freeze clock deterministically at historical bar time
                with frozen_time(cur_time):
                    sig = await asyncio.wait_for(
                        strat_instance.evaluate(
                            session=slice_session,  # type: ignore[arg-type]
                            symbol=self.symbol,
                            settings=self.settings,
                        ),
                        timeout=5.0,
                    )
            except Exception as e:
                logger.debug(f"[IsolatedHarness] Evaluation exception at bar {i} for {self.symbol}: {e}")
                if self.fail_fast_on_error:
                    return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                i += 1
                continue

            if sig is not None and not isinstance(sig, EdgeSignal):
                if self.fail_fast_on_error:
                    return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                i += 1
                continue

            if sig is not None and ("error" in getattr(sig, "tags", []) or "evaluation_error" in getattr(sig, "tags", [])):
                if self.fail_fast_on_error:
                    return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                i += 1
                continue

            if not sig or not sig.valid or sig.direction not in ("buy", "sell"):
                i += 1
                continue

            # Directional execution price with realistic broker friction
            base_price = float(current_bar.close)
            if sig.direction == "buy":
                entry_price = base_price + (self.spread_cost / 2.0) + self.slippage_cost
            else:
                entry_price = base_price - (self.spread_cost / 2.0) - self.slippage_cost

            atr = self._calculate_atr(h1_slice, period=14)

            # Resolve Stop Loss and Take Profit
            if sig.stop_loss is not None and sig.take_profit is not None:
                sl = float(sig.stop_loss)
                tp = float(sig.take_profit)
            else:
                if self.fail_fast_on_error:
                    logger.debug(
                        f"[IsolatedHarness] Signal without SL/TP rejected under fail_fast for {self.symbol}"
                    )
                    return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                sl, tp = self._resolve_sl_tp(sig, entry_price, atr, strat_instance)

            # Forward bar-by-bar outcome simulation with conservative intra-bar sequencing and gap modeling
            exit_price = entry_price
            exit_reason = "time_exit"
            exit_time = cur_time
            bars_held = 0

            max_eval_bar = min(i + max_hold_bars + 1, len(primary_candles))
            for f_idx in range(i + 1, max_eval_bar):
                f_bar = primary_candles[f_idx]
                f_open = float(f_bar.open)
                f_high = float(f_bar.high)
                f_low = float(f_bar.low)
                bars_held += 1
                exit_time = f_bar.get("time") or (cur_time + timedelta(hours=bars_held))

                if sig.direction == "buy":
                    # Gap open past stop loss
                    if f_open <= sl:
                        exit_price = f_open - self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    # Intra-bar collision: conservative worst-case
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
                    # Gap open past stop loss
                    if f_open >= sl:
                        exit_price = f_open + self.slippage_cost
                        exit_reason = "stop_loss"
                        break
                    # Intra-bar collision: conservative worst-case
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
                last_held_bar = primary_candles[max_eval_bar - 1]
                exit_price = float(last_held_bar.close)
                exit_reason = "time_exit"

            ret_equity, ret_pct, r_mult = self._calculate_trade_pnl(
                direction=sig.direction,
                entry_price=entry_price,
                exit_price=exit_price,
                sl=sl,
            )
            trade_returns.append(ret_equity)
            trade_records.append(
                StrategyTradeRecord(
                    symbol=self.symbol,
                    direction=sig.direction,
                    entry_time=cur_time,
                    entry_price=round(entry_price, 5),
                    exit_time=exit_time,
                    exit_price=round(exit_price, 5),
                    stop_loss=round(sl, 5),
                    take_profit=round(tp, 5),
                    pnl_pct=ret_pct,
                    exit_reason=exit_reason,
                    bars_held=bars_held,
                    confidence=float(sig.confidence or 0.7),
                    strategy_id=getattr(strat_instance, "strategy_id", "unknown"),
                    r_multiple=r_mult,
                )
            )

            i += max(1, bars_held)

        return self._compute_metrics(trade_returns, trade_records)

    run_single_window = run_simulation

    def _compute_metrics(
        self, returns: List[float], records: List[StrategyTradeRecord]
    ) -> HarnessMetrics:
        """Calculates comprehensive institutional performance metrics."""
        if not returns:
            return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        total_trades = len(returns)
        wins = [r for r in returns if r > 0.0]
        losses = [r for r in returns if r < 0.0]

        win_rate_pct = round((len(wins) / total_trades) * 100.0, 1)

        sum_wins = sum(wins)
        sum_losses = abs(sum(losses))
        profit_factor = round(sum_wins / sum_losses, 2) if sum_losses > 1e-9 else (10.0 if sum_wins > 0 else 0.0)

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1)) if len(returns) > 1 else 1e-6
        ann_factor = math.sqrt(252.0 * 24.0 / max(1.0, np.mean([r.bars_held for r in records]))) if records else math.sqrt(252.0)
        sharpe_ratio = round(float((mean_ret / (std_ret + 1e-9)) * ann_factor), 2)

        downside_std = float(np.std([r for r in returns if r < 0.0], ddof=1)) if len(losses) > 1 else 1e-6
        sortino_ratio = round(float((mean_ret / (downside_std + 1e-9)) * ann_factor), 2)

        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in returns:
            equity *= (1.0 + r)
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        total_pnl_pct = round((equity - 1.0) * 100.0, 2)

        return HarnessMetrics(
            total_trades=total_trades,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown_pct=round(max_dd, 2),
            total_pnl_pct=total_pnl_pct,
            trade_returns=returns,
            trades=records,
        )

    async def run_walk_forward(
        self,
        session: AsyncSession,
        n_folds: int = 4,
        is_ratio: float = 0.65,
        total_candles: int = 1500,
        min_candles: int = 120,
        trial_counter: int = 1,
        param_specs: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes rolling-window Walk-Forward Optimization (WFO).
        Applies Deflated Sharpe Ratio (DSR) and AlphaValidation across stitched OOS trades.
        Ensures zero-lookahead, full dataset coverage, and optional fold-level plateau optimization.
        """
        all_candles = await self.fetch_historical_candles(
            session=session, timeframe="H1", limit=total_candles
        )

        if len(all_candles) < min_candles:
            return {
                "passed": False,
                "overall_wfe": 0.0,
                "aggregate_is_sharpe": 0.0,
                "aggregate_oos_sharpe": 0.0,
                "dsr": 0.0,
                "total_oos_trades": 0,
                "reason": f"Insufficient candles ({len(all_candles)} < {min_candles})",
            }

        N = len(all_candles)
        total_oos = int(N * (1.0 - is_ratio))
        oos_size = max(10, total_oos // n_folds)
        is_size = int(N * is_ratio)

        is_sharpes: List[float] = []
        oos_sharpes: List[float] = []
        is_pnls: List[float] = []
        oos_pnls: List[float] = []
        all_oos_trades: List[StrategyTradeRecord] = []

        for fold_idx in range(n_folds):
            oos_start = N - (n_folds - fold_idx) * oos_size
            oos_end = oos_start + oos_size
            is_start = max(0, oos_start - is_size)
            is_end = oos_start

            is_candles = all_candles[is_start:is_end]
            oos_candles = all_candles[oos_start:oos_end]

            if len(is_candles) < 20 or len(oos_candles) < 5:
                continue

            # In-Sample Plateau Optimization per fold if param_specs supplied (Anti-Leakage)
            if param_specs and len(is_candles) >= 30:
                try:
                    from analysis.calculators.quant_plateau_optimizer import QuantPlateauOptimizer
                    async def _eval_fold_plateau(params: Dict[str, Any]) -> Dict[str, Any]:
                        self.strategy_params = params
                        m = await self._run_simulation_on_candles(is_candles)
                        return {
                            "sharpe": m.sharpe_ratio,
                            "trades": m.total_trades,
                            "trade_returns": [t.pnl_pct / 100.0 for t in m.trades],
                            "pnl_pct": m.total_pnl_pct,
                        }
                    fold_opt = QuantPlateauOptimizer(
                        param_space=param_specs,
                        n_trials=8,
                        n_neighbors_per_candidate=2,
                        min_trade_count=3,
                    )
                    fold_opt_res = await fold_opt.optimize(_eval_fold_plateau)
                    if fold_opt_res and fold_opt_res.best_parameters:
                        self.strategy_params = fold_opt_res.best_parameters
                except Exception as fold_err:
                    logger.debug(f"[IsolatedHarness] Fold {fold_idx} plateau opt note: {fold_err}")

            is_metrics = await self._run_simulation_on_candles(is_candles)
            oos_metrics = await self._run_simulation_on_candles(oos_candles)

            is_sharpes.append(is_metrics.sharpe_ratio)
            oos_sharpes.append(oos_metrics.sharpe_ratio)
            is_pnls.append(is_metrics.total_pnl_pct)
            oos_pnls.append(oos_metrics.total_pnl_pct)
            all_oos_trades.extend(oos_metrics.trades)

        avg_is_sharpe = float(np.mean(is_sharpes)) if is_sharpes else 0.0
        avg_oos_sharpe = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0

        # Institutional Annualized WFE (Robert Pardo): OOS Sharpe / IS Sharpe
        if avg_is_sharpe > 0.1:
            wfe = round(max(0.0, avg_oos_sharpe) / avg_is_sharpe, 2)
        else:
            wfe = 0.0

        # Deflated Sharpe Ratio (DSR) using actual observed OOS trades with consistent trade-level scale
        oos_returns = [t.pnl_pct / 100.0 for t in all_oos_trades]
        _, _, oos_skew, oos_kurt = compute_sample_moments(oos_returns) if len(oos_returns) >= 3 else (0.0, 0.0, 0.0, 0.0)

        if len(oos_returns) >= 3 and np.std(oos_returns, ddof=1) > 1e-9:
            trade_sr = float(np.mean(oos_returns) / np.std(oos_returns, ddof=1))
            dsr_score = deflated_sharpe_ratio(
                observed_sr=trade_sr,
                n_trials=max(1, trial_counter),
                n_obs=len(all_oos_trades),
                skew=oos_skew,
                excess_kurt=oos_kurt,
                sr_std=max(0.1, 1.0 / math.sqrt(len(all_oos_trades))),
            )
        else:
            dsr_score = 0.5 if avg_oos_sharpe > 0 else 0.0

        alpha_val = validate_alpha(trades=all_oos_trades, cost_multiplier=2.0)

        passed = bool(
            wfe >= 0.60
            and avg_oos_sharpe >= 0.50
            and len(all_oos_trades) >= 5
            and (dsr_score >= 0.55 if len(all_oos_trades) >= 15 else True)
            and alpha_val.passed
        )

        return {
            "passed": passed,
            "overall_wfe": wfe,
            "aggregate_is_sharpe": round(avg_is_sharpe, 2),
            "aggregate_oos_sharpe": round(avg_oos_sharpe, 2),
            "dsr": round(dsr_score, 2),
            "total_oos_trades": len(all_oos_trades),
            "alpha_validation": alpha_val,
            "all_oos_trades": all_oos_trades,
            "is_sharpes": is_sharpes,
            "oos_sharpes": oos_sharpes,
        }

    async def _run_simulation_on_candles(self, candles: List[CandleDict]) -> HarnessMetrics:
        """Helper to simulate on a pre-sliced list of candles with full clock freezing and resampled HTF."""
        from utils.clock import frozen_time

        if len(candles) < 25:
            return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        strat_instance = self._get_strategy_instance()
        trade_records: List[StrategyTradeRecord] = []
        trade_returns: List[float] = []

        h4_candles = resample_candles(candles, 4)
        d1_candles = resample_candles(candles, 24)

        i = 15
        while i < len(candles) - 2:
            current_bar = candles[i]
            cur_time = current_bar.get("time") or datetime.now(timezone.utc)
            h1_slice = candles[: i + 1]
            h4_slice = [c for c in h4_candles if (c.get("time") or cur_time) <= cur_time]
            d1_slice = [c for c in d1_candles if (c.get("time") or cur_time) <= cur_time]

            slice_cache: Dict[tuple[str, str], List[CandleDict]] = {
                (self.symbol, "H1"): h1_slice,
                (self.symbol, "M15"): h1_slice,
                (self.symbol, "H4"): h4_slice if h4_slice else h1_slice,
                (self.symbol, "D1"): d1_slice if d1_slice else h1_slice,
            }
            slice_session = ZeroLookaheadSliceSession(slice_cache, as_of_time=cur_time, symbol=self.symbol)

            try:
                with frozen_time(cur_time):
                    sig = await asyncio.wait_for(
                        strat_instance.evaluate(
                            session=slice_session,  # type: ignore[arg-type]
                            symbol=self.symbol,
                            settings=self.settings,
                        ),
                        timeout=5.0,
                    )
            except Exception:
                i += 1
                continue

            if not sig or not sig.valid or sig.direction not in ("buy", "sell"):
                i += 1
                continue

            base_price = float(current_bar.close)
            entry_price = base_price + (self.spread_cost / 2.0) + self.slippage_cost if sig.direction == "buy" else base_price - (self.spread_cost / 2.0) - self.slippage_cost
            atr = self._calculate_atr(h1_slice, period=14)

            if sig.stop_loss is not None and sig.take_profit is not None:
                sl = float(sig.stop_loss)
                tp = float(sig.take_profit)
            else:
                if self.fail_fast_on_error:
                    return HarnessMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                sl, tp = self._resolve_sl_tp(sig, entry_price, atr, strat_instance)

            exit_price = entry_price
            exit_reason = "time_exit"
            exit_time = cur_time
            bars_held = 0

            max_eval_bar = min(i + 15, len(candles))
            for f_idx in range(i + 1, max_eval_bar):
                f_bar = candles[f_idx]
                f_open = float(f_bar.open)
                f_high = float(f_bar.high)
                f_low = float(f_bar.low)
                bars_held += 1
                exit_time = f_bar.get("time") or cur_time

                if sig.direction == "buy":
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
                last_bar = candles[max_eval_bar - 1]
                exit_price = float(last_bar.close)

            ret_equity, ret_pct, r_mult = self._calculate_trade_pnl(
                direction=sig.direction,
                entry_price=entry_price,
                exit_price=exit_price,
                sl=sl,
            )
            trade_returns.append(ret_equity)
            trade_records.append(
                StrategyTradeRecord(
                    symbol=self.symbol,
                    direction=sig.direction,
                    entry_time=cur_time,
                    entry_price=entry_price,
                    exit_time=exit_time,
                    exit_price=exit_price,
                    stop_loss=sl,
                    take_profit=tp,
                    pnl_pct=ret_pct,
                    exit_reason=exit_reason,
                    bars_held=bars_held,
                    confidence=float(sig.confidence or 0.7),
                    strategy_id=getattr(strat_instance, "strategy_id", "unknown"),
                    r_multiple=r_mult,
                )
            )
            i += max(1, bars_held)

        return self._compute_metrics(trade_returns, trade_records)

    def generate_markdown_report(self, res: Dict[str, Any]) -> str:
        """Generates an institutional markdown report for harness results."""
        wfe = res.get("overall_wfe", 0.0)
        is_sr = res.get("aggregate_is_sharpe", 0.0)
        oos_sr = res.get("aggregate_oos_sharpe", 0.0)
        dsr = res.get("dsr", 0.0)
        trades = res.get("all_oos_trades", [])
        alpha_val = res.get("alpha_validation")
        strat_name = self.strategy_cls.__name__ if hasattr(self.strategy_cls, "__name__") else str(self.strategy_cls)
        strat_id = getattr(self.strategy_cls, "strategy_id", "unknown")

        wins = sum(1 for t in trades if getattr(t, "pnl_pct", 0.0) > 0)
        win_rate = (wins / len(trades) * 100.0) if trades else 0.0

        lines = [
            f"# Isolated Alpha Evaluation: {strat_name} ({self.symbol})",
            f"**Strategy ID**: `{strat_id}` | **Symbol**: `{self.symbol}`",
            "",
            "## Summary Performance",
            f"- **Walk-Forward Efficiency (WFE)**: `{wfe:.2f}` ({'PASS (>= 0.60)' if wfe >= 0.60 else 'FAIL (< 0.60)'})",
            f"- **Aggregate In-Sample Sharpe**: `{is_sr:.2f}`",
            f"- **Aggregate Out-of-Sample Sharpe**: `{oos_sr:.2f}` ({'PASS (>= 0.50)' if oos_sr >= 0.50 else 'FAIL (< 0.50)'})",
            f"- **Deflated Sharpe Ratio (DSR)**: `{dsr:.2f}` ({'PASS (>= 0.60)' if dsr >= 0.60 else 'FAIL (< 0.60)'})",
            f"- **Total OOS Trades**: `{len(trades)}` (Win Rate: `{win_rate:.1f}%`)",
            f"- **Alpha Validation**: `{'PASS' if alpha_val and getattr(alpha_val, 'passed', False) else 'FAIL'}`",
        ]
        if alpha_val and hasattr(alpha_val, "details"):
            lines.append(f"  - Validation Details: {alpha_val.details}")
        return "\n".join(lines)

