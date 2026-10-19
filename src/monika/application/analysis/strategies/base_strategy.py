from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession


class CandleDict(dict):
    """Dictionary supporting both item lookup (c['high']) and attribute access (c.high)."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'CandleDict' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


@dataclass
class EdgeSignal:
    strategy_id: str
    symbol: str
    direction: Optional[str]  # 'buy' | 'sell' | None
    valid: bool
    confidence: float  # 0-1, strategy-native conviction
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    max_hold_minutes: Optional[int] = None
    ttl_minutes: Optional[int] = None  # Alpha Time-to-Live / half-life before signal expires
    factor_family: str = "trend"  # 'trend' | 'mean_reversion' | 'stat_arb' | 'breakout'
    force_session_close: bool = False
    exit_style: str = "intraday_adr"  # 'intraday_adr' or 'trend_trailing'
    rationale: str = ""
    tags: list[str] = field(default_factory=list)  # e.g. "mean_reversion" | "trend"
    meta: dict = field(default_factory=dict)
    paired_leg: Optional["EdgeSignal"] = None  # Hedge leg for stat-arb pairs


class EdgeStrategy(ABC):
    strategy_id: str = ""
    applicable_symbols: set[str] = set()
    compatible_regimes: set[str] = {"ALL"}  # Set of supported market regimes, e.g. {"TREND", "STRONG_TREND"}
    factor_family: str = "trend"  # Factor family for portfolio risk parity
    min_sample_size: int = 30

    def __init__(self, settings: Optional[dict] = None, *args, **kwargs):
        self.settings = settings or {}
        strat_id = getattr(self, "strategy_id", "")
        self.cfg = self.settings.get("trading", {}).get("edge_strategy", {}).get(strat_id, {})

    def is_enabled(self, symbol: str) -> bool:
        if not self.cfg.get("enabled", True):
            return False
        return not self.applicable_symbols or symbol in self.applicable_symbols

    def is_regime_compatible(self, regime: str) -> bool:
        """Evaluates whether this strategy is designed to operate under the given market regime."""
        if not self.compatible_regimes or "ALL" in self.compatible_regimes:
            return True
        norm_regime = str(regime or "").upper().replace(" ", "_")
        return norm_regime in self.compatible_regimes

    async def get_historical_candles(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 100,
        as_of: Optional[Any] = None,
    ) -> list[CandleDict]:
        """Built-in helper for quantitative strategies to retrieve historical OHLCV candles."""
        from sqlalchemy import select

        from monika.infrastructure.database.models import PriceOHLCV

        norm_tf = timeframe.upper()
        cache_key = (symbol, norm_tf, str(as_of) if as_of is not None else None)

        # Check session-level in-memory cache to eliminate N+1 DB query storms
        if hasattr(session, "info") and isinstance(session.info, dict):
            candle_cache = session.info.setdefault("candle_cache", {})
            if cache_key in candle_cache:
                cached = candle_cache[cache_key]
                if len(cached) >= limit:
                    return cached[-limit:]

        stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == norm_tf)
        if as_of is not None:
            stmt = stmt.where(PriceOHLCV.timestamp <= as_of)
        stmt = stmt.order_by(PriceOHLCV.timestamp.desc()).limit(limit)

        rows = (await session.execute(stmt)).scalars().all()
        rows = list(reversed(rows))
        candles = [
            CandleDict(
                {
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": float(r.volume or 0.0),
                }
            )
            for r in rows
        ]
        if hasattr(session, "info") and isinstance(session.info, dict):
            session.info.setdefault("candle_cache", {})[cache_key] = candles
        return candles

    @staticmethod
    def derive_atr_brackets(
        entry_price: float,
        candles: list[CandleDict],
        direction: str,
        atr_period: int = 14,
        atr_multiplier_sl: float = 1.5,
        risk_reward_ratio: float = 1.5,
    ) -> tuple[float, float]:
        """Compute robust ATR-based Stop Loss and Take Profit levels."""
        if not candles or len(candles) < 2 or entry_price <= 0:
            if direction.lower() == "buy":
                return round(entry_price * 0.99, 5), round(entry_price * 1.015, 5)
            else:
                return round(entry_price * 1.01, 5), round(entry_price * 0.985, 5)

        tr_list = []
        for i in range(1, min(len(candles), atr_period + 1)):
            h = float(candles[-i].high)
            l = float(candles[-i].low)
            prev_c = float(candles[-i - 1].close)
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        atr = sum(tr_list) / len(tr_list) if tr_list else (entry_price * 0.005)

        sl_dist = atr * atr_multiplier_sl
        tp_dist = sl_dist * risk_reward_ratio

        if direction.lower() == "buy":
            sl = entry_price - sl_dist
            tp = entry_price + tp_dist
        else:
            sl = entry_price + sl_dist
            tp = entry_price - tp_dist

        return round(sl, 5), round(tp, 5)

    @abstractmethod
    async def evaluate(
        self,
        session: AsyncSession,
        symbol: str,
        settings: dict,
    ) -> EdgeSignal: ...
