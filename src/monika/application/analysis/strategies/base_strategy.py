from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession


class StrategyTier(str, Enum):
    VALIDATED = "validated"  # Empirically verified, positive DSR/PF, zero ruin risk, allowed to trade live/paper
    EXPERIMENTAL = "experimental"  # In discovery or incubation, paper-shadow only, cannot place live trades
    QUARANTINED = "quarantined"  # Negative edge, high drawdown, structural flaw, or decaying: suppressed from execution


QUARANTINED_STRATEGY_IDS: set[str] = {
    "smc_fvg",
    "btc_donchian_breakout",
    "bollinger_reversion",
    "asian_range_fade",
    "xti_pairs_readiness",
    "alpha_xtiusd_374fa7",
    "alpha_eurusd_8060ed",
    "alpha_xauusd_5044bf",
    "alpha_xauusd_7358c1",
    "alpha_xauusd_a84e8d",
    "alpha_xtiusd_83031c",
}

PROMOTED_EMPIRICAL_STRATEGIES: set[str] = {
    "tokyo_open_sweep",
    "liquidity_sweep",
    "smt_divergence",
    "bb_volume_profile",
    "vwap_mean_reversion",
    "usdjpy_atr_exhaustion",
    "xtiusd_atr_exhaustion",
    "xauusd_atr_exhaustion",
    "btcusd_dynamic_donchian",
    "gbpusd_trend_breakout",
    "xau_trend_engine",
    "tsm_momentum",
}


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

    def is_executable(self, min_rr: float = 1.0) -> bool:
        """Validate physical geometry and completeness of executable trading signal."""
        if not self.valid or self.direction not in ("buy", "sell"):
            return False
        if self.entry_price is None or self.entry_price <= 0:
            return False
        if self.stop_loss is None or self.stop_loss <= 0:
            return False
        if self.take_profit is None or self.take_profit <= 0:
            return False

        if self.direction == "buy":
            if not (self.stop_loss < self.entry_price < self.take_profit):
                return False
            risk = self.entry_price - self.stop_loss
            reward = self.take_profit - self.entry_price
        else:
            if not (self.take_profit < self.entry_price < self.stop_loss):
                return False
            risk = self.stop_loss - self.entry_price
            reward = self.entry_price - self.take_profit

        if risk <= 0 or (reward / risk) < min_rr:
            return False
        return True


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
                if cached:
                    return cached[-limit:]
            elif (symbol, norm_tf) in candle_cache:
                cached = candle_cache[(symbol, norm_tf)]
                if cached:
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
                    "timestamp": r.timestamp.isoformat()
                    if hasattr(r.timestamp, "isoformat")
                    else (str(r.timestamp) if r.timestamp else None),
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

    @classmethod
    def build_bracket(
        cls,
        entry_price: float,
        direction: str,
        atr: float,
        atr_multiplier_sl: float = 1.5,
        risk_reward_ratio: float = 1.8,
    ) -> tuple[float, float]:
        """Compute robust, geometrically sound Stop Loss and Take Profit levels."""
        if entry_price <= 0 or atr <= 0:
            raise ValueError(f"Invalid entry ({entry_price}) or ATR ({atr}) for bracket calculation")

        sl_dist = atr * atr_multiplier_sl
        tp_dist = sl_dist * risk_reward_ratio

        norm_dir = direction.lower()
        if norm_dir == "buy":
            sl = entry_price - sl_dist
            tp = entry_price + tp_dist
        elif norm_dir == "sell":
            sl = entry_price + sl_dist
            tp = entry_price - tp_dist
        else:
            raise ValueError(f"Invalid direction: {direction}")

        return round(sl, 5), round(tp, 5)

    @abstractmethod
    async def evaluate(
        self,
        session: AsyncSession,
        symbol: str,
        settings: dict,
    ) -> EdgeSignal: ...
