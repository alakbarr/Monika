"""
Deterministic Playbook Signal Screener Engine.

Evaluates multi-asset empirical trading playbooks against active price bars,
technical indicators, and session timings in pure Python.
Operates deterministically (<1ms) to eliminate LLM arithmetic hallucinations
and provide grounded quantitative confluence signals to Stage 2 analysis.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Market.PlaybookScreener")

_PRICE_PRECISION: Dict[str, int] = {
    "EURUSD": 5,
    "GBPUSD": 5,
    "AUDUSD": 5,
    "NZDUSD": 5,
    "USDCAD": 5,
    "USDCHF": 5,
    "USDJPY": 3,
    "EURJPY": 3,
    "GBPJPY": 3,
    "AUDJPY": 3,
    "XAUUSD": 2,
    "XAGUSD": 3,
    "XTIUSD": 3,
    "XBRUSD": 3,
    "BTCUSD": 1,
    "ETHUSD": 2,
}


@dataclass
class PlaybookSpec:
    """Formal specification of an empirical trading playbook."""

    name: str
    symbol: str
    regime: str
    timeframe: str
    min_rr: float
    profit_factor: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown_pct: float
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0
    max_hold_bars: int = 24
    description: str = ""
    status: str = "active"
    file_path: Optional[Path] = None


@dataclass
class PlaybookTriggerSignal:
    """Deterministic trade signal emitted by an empirical playbook."""

    playbook_name: str
    symbol: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    sl_price: float
    tp_price: float
    sl_distance: float
    tp_distance: float
    rr_ratio: float
    max_hold_bars: int
    historical_pf: float
    historical_win_rate: float
    historical_sharpe: float
    historical_max_dd: float
    trigger_reasons: List[str]
    macro_alignment: str = "NEUTRAL"  # "ALIGNED", "NEUTRAL", or "OPPOSED"
    confidence: float = 0.75


@dataclass
class PlaybookScreeningReport:
    """Structured report returned by the Playbook Screener."""

    symbol: str
    evaluated_at: datetime
    active_signals: List[PlaybookTriggerSignal] = field(default_factory=list)
    monitoring_playbooks: List[Dict[str, str]] = field(default_factory=list)
    cooldown_playbooks: List[str] = field(default_factory=list)
    total_evaluated: int = 0

    def format_for_prompt(self) -> str:
        """Format screening result as a concise, high-confluence prompt card for LLM."""
        lines = [
            f"-- QUANTITATIVE PLAYBOOK SIGNAL SCREENER ({self.symbol}) --",
            f"Evaluated: {self.total_evaluated} Empirical Playbooks | UTC Time: {self.evaluated_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
        ]

        if self.cooldown_playbooks:
            lines.append(f"[COOLDOWN / CIRCUIT-BREAKER] {', '.join(self.cooldown_playbooks)}")
            lines.append("  (Temporarily suppressed due to 3 consecutive losses; undergoing 48h revalidation)")
            lines.append("")

        if self.active_signals:
            for sig in self.active_signals:
                lines.append(f"[TRIGGERED: {sig.playbook_name.upper()}]")
                lines.append(
                    f"  * Direction: {sig.direction} | Macro Alignment: {sig.macro_alignment} | Confidence: {sig.confidence:.2f}"
                )
                lines.append(
                    f"  * Empirical Edge: PF {sig.historical_pf:.2f} | WinRate {sig.historical_win_rate:.1%} | Sharpe {sig.historical_sharpe:.2f} | Max DD {sig.historical_max_dd:.1f}%"
                )
                lines.append("  * Trigger Conditions Met:")
                for r in sig.trigger_reasons:
                    lines.append(f"    - {r}")
                lines.append("  * Calibrated Order Invariants:")
                lines.append(f"    - Entry: {sig.entry_price}")
                lines.append(f"    - Stop-Loss: {sig.sl_price} (Buffer: {sig.sl_distance:.4f} pts)")
                lines.append(f"    - Take-Profit: {sig.tp_price} (Target: {sig.tp_distance:.4f} pts)")
                lines.append(f"    - Contractual R:R: 1:{sig.rr_ratio:.2f} | Max Hold: {sig.max_hold_bars} H1 bars")
                lines.append(
                    f"  * ACTION DIRECTIVE: If validated by SMC/Orderflow, submit with playbook_id: '{sig.playbook_name}'."
                )
                lines.append("")
        else:
            lines.append(
                f"[INACTIVE] All {self.total_evaluated} empirical playbooks currently inactive (conditions or session window unmet)."
            )
            lines.append("  Directive: Proceed with universal SMC/ICT structure or submit WAIT if no confluence.")
            lines.append("")

        if self.monitoring_playbooks:
            lines.append("-- NEARBY PLAYBOOKS IN MONITORING --")
            for mon in self.monitoring_playbooks[:3]:
                lines.append(f"  * {mon.get('name', 'Unknown')}: {mon.get('status', 'Monitoring')}")
            lines.append("")

        lines.append("-- END PLAYBOOK SCREENER --")
        return "\n".join(lines)


class PlaybookRegistry:
    """Caches and resolves empirical playbook specifications from disk."""

    _cached_specs: Dict[str, List[PlaybookSpec]] = {}
    _playbooks_dir: Optional[Path] = None

    @classmethod
    def get_playbooks_dir(cls) -> Path:
        """Resolve the playbooks directory path."""
        if cls._playbooks_dir is not None and cls._playbooks_dir.exists():
            return cls._playbooks_dir

        base = Path(__file__).resolve().parents[4] / "skills" / "trading" / "playbooks"
        if base.exists():
            cls._playbooks_dir = base
            return base

        fallback = Path("skills/trading/playbooks").resolve()
        if fallback.exists():
            cls._playbooks_dir = fallback
            return fallback

        return base

    @classmethod
    def set_playbooks_dir(cls, custom_dir: Path) -> None:
        """Explicitly override directory for testing."""
        cls._playbooks_dir = custom_dir
        cls._cached_specs.clear()

    @classmethod
    def load_playbooks_for_symbol(cls, symbol: str) -> List[PlaybookSpec]:
        """Load and cache all playbook specifications for a given symbol."""
        sym_clean = symbol.strip().upper()
        if sym_clean in cls._cached_specs:
            return cls._cached_specs[sym_clean]

        pb_dir = cls.get_playbooks_dir()
        if not pb_dir.exists():
            logger.warning(f"Playbooks directory not found at {pb_dir}")
            return []

        specs: List[PlaybookSpec] = []
        prefix = sym_clean.lower() + "_"

        for f in pb_dir.glob("*.md"):
            fname = f.name.lower()
            if not fname.startswith(prefix):
                continue
            try:
                spec = cls._parse_playbook_file(f, sym_clean)
                if spec is not None:
                    specs.append(spec)
            except Exception as e:
                logger.debug(f"Failed parsing playbook {f.name}: {e}")

        # Sort by Profit Factor descending to prioritize highest-edge playbooks
        specs.sort(key=lambda s: s.profit_factor, reverse=True)
        cls._cached_specs[sym_clean] = specs
        return specs

    @classmethod
    def _parse_playbook_file(cls, path: Path, expected_symbol: str) -> Optional[PlaybookSpec]:
        """Parse frontmatter and quantitative directives from a markdown playbook file."""
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None

        parts = text.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_raw = parts[1]
        body = parts[2]

        fm: Dict[str, Any] = {}
        for line in frontmatter_raw.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            fm[k] = v

        name = fm.get("name", path.stem)
        symbol = fm.get("symbol", expected_symbol).upper()
        if symbol != expected_symbol:
            return None

        def _safe_float(val: Any, default: float) -> float:
            try:
                f_val = float(val)
                return f_val if not math.isnan(f_val) and not math.isinf(f_val) else default
            except ValueError, TypeError:
                return default

        def _safe_int(val: Any, default: int) -> int:
            try:
                return int(val)
            except ValueError, TypeError:
                return default

        pf = _safe_float(fm.get("profit_factor"), 1.3)
        wr = _safe_float(fm.get("win_rate"), 0.5)
        sr = _safe_float(fm.get("sharpe_ratio"), 2.0)
        max_dd = _safe_float(fm.get("max_drawdown_pct"), 8.0)
        min_rr = _safe_float(fm.get("min_rr"), 1.5)
        regime = fm.get("regime", "trend")
        timeframe = fm.get("timeframe", "H1")
        description = fm.get("description", "")
        status = fm.get("status", "active")

        # Extract calibrated ATR multipliers from body
        sl_mult = 1.5
        tp_mult = 3.0
        max_hold = 24

        m_sl = re.search(r"Stop-Loss\s*=\s*([\d\.]+)x\s*ATR", body, re.IGNORECASE)
        if m_sl:
            sl_mult = _safe_float(m_sl.group(1), 1.5)
        else:
            m_sl2 = re.search(r"set at ([\d\.]+)x.*?ATR", body, re.IGNORECASE)
            if m_sl2:
                sl_mult = _safe_float(m_sl2.group(1), 1.5)

        m_tp = re.search(r"Take-Profit\s*=\s*([\d\.]+)x\s*ATR", body, re.IGNORECASE)
        if m_tp:
            tp_mult = _safe_float(m_tp.group(1), max(2.5, min_rr * sl_mult))
        else:
            m_tp2 = re.search(r"placed at ([\d\.]+)x.*?ATR", body, re.IGNORECASE)
            if m_tp2:
                tp_mult = _safe_float(m_tp2.group(1), max(2.5, min_rr * sl_mult))

        m_hold = re.search(r"Max Holding\s*=\s*(\d+)\s*bars", body, re.IGNORECASE)
        if m_hold:
            max_hold = _safe_int(m_hold.group(1), 24)
        else:
            m_hold2 = re.search(r"within (\d+) bars", body, re.IGNORECASE)
            if m_hold2:
                max_hold = _safe_int(m_hold2.group(1), 24)

        return PlaybookSpec(
            name=name,
            symbol=symbol,
            regime=regime,
            timeframe=timeframe,
            min_rr=min_rr,
            profit_factor=pf,
            win_rate=wr,
            sharpe_ratio=sr,
            max_drawdown_pct=max_dd,
            sl_atr_mult=sl_mult,
            tp_atr_mult=tp_mult,
            max_hold_bars=max_hold,
            description=description,
            status=status,
            file_path=path,
        )


class PlaybookScreener:
    """
    Deterministic quantitative signal screener.
    Screens active bars against symbol playbooks and computes calibrated orders.
    """

    @classmethod
    def compute_atr(cls, bars: List[Dict[str, Any]], period: int = 14) -> float:
        """Compute Wilder's ATR over a list of OHLCV bars."""
        if len(bars) < period + 1:
            if bars:
                ranges = [float(b.get("high", 0.0)) - float(b.get("low", 0.0)) for b in bars]
                return float(sum(ranges) / max(1, len(ranges)))
            return 1.0

        tr_list: List[float] = []
        for i in range(1, len(bars)):
            h = float(bars[i].get("high", 0.0))
            l = float(bars[i].get("low", 0.0))
            prev_c = float(bars[i - 1].get("close", 0.0))
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)

        if not tr_list:
            return 1.0

        # Initial SMA
        atr = sum(tr_list[:period]) / float(period)
        # Wilder smoothing
        for tr in tr_list[period:]:
            atr = (atr * (period - 1) + tr) / float(period)

        return float(atr) if atr > 0 else 1.0

    @classmethod
    def compute_ema(cls, values: List[float], period: int) -> float:
        """Compute Exponential Moving Average."""
        if not values:
            return 0.0
        if len(values) < period:
            return float(sum(values) / len(values))
        k = 2.0 / (period + 1.0)
        ema = float(sum(values[:period]) / period)
        for v in values[period:]:
            ema = (v * k) + (ema * (1.0 - k))
        return float(ema)

    @classmethod
    def compute_rsi(cls, closes: List[float], period: int = 14) -> float:
        """Compute Relative Strength Index."""
        if len(closes) < period + 1:
            return 50.0
        gains: List[float] = []
        losses: List[float] = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        avg_gain = sum(gains[:period]) / float(period)
        avg_loss = sum(losses[:period]) / float(period)

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / float(period)
            avg_loss = (avg_loss * (period - 1) + losses[i]) / float(period)

        if avg_loss == 0.0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    @classmethod
    def screen(
        cls,
        symbol: str,
        bars: List[Dict[str, Any]],
        indicators: Optional[Dict[str, Any]] = None,
        now_utc: Optional[datetime] = None,
        macro_regime: Optional[str] = None,
        cooldown_playbooks: Optional[Set[str]] = None,
    ) -> PlaybookScreeningReport:
        """
        Screen the latest bars for symbol against all 15 empirical playbooks.
        Fail closed: returns empty report if bars are insufficient or data is corrupt.
        """
        sym_clean = symbol.strip().upper()
        now = now_utc or datetime.now(timezone.utc)
        cooldowns = cooldown_playbooks or set()

        specs = PlaybookRegistry.load_playbooks_for_symbol(sym_clean)
        report = PlaybookScreeningReport(
            symbol=sym_clean,
            evaluated_at=now,
            total_evaluated=len(specs),
        )

        if len(bars) < 10:
            logger.debug(f"[{sym_clean}] Insufficient bars ({len(bars)}) for playbook screening.")
            return report

        # Extract bar arrays
        closes = [float(b.get("close", 0.0)) for b in bars]
        highs = [float(b.get("high", 0.0)) for b in bars]
        lows = [float(b.get("low", 0.0)) for b in bars]
        opens = [float(b.get("open", 0.0)) for b in bars]
        volumes = [float(b.get("tick_volume", b.get("volume", 0.0))) for b in bars]

        current_close = closes[-1]
        current_open = opens[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        current_vol = volumes[-1]

        if current_close <= 0:
            return report

        # Fallback/Indicator values
        ind_dict = indicators or {}
        atr = float(ind_dict.get("atr_14") or ind_dict.get("atr") or cls.compute_atr(bars, 14))
        if atr <= 0:
            atr = cls.compute_atr(bars, 14)

        rsi = float(ind_dict.get("rsi_14") or ind_dict.get("rsi") or cls.compute_rsi(closes, 14))
        ema9 = cls.compute_ema(closes, 9)
        ema21 = cls.compute_ema(closes, 21)
        ema50 = cls.compute_ema(closes, 50)
        avg_vol20 = sum(volumes[-20:]) / max(1.0, len(volumes[-20:])) if len(volumes) >= 5 else 1.0

        # Session & Bar Timing
        hour_utc = now.hour
        # Pre-London / Asian session reference (last 7 bars or 00:00-06:00 window)
        pre_london_bars = bars[-8:-1] if len(bars) >= 8 else bars[:-1]
        pre_london_high = max([float(b.get("high", 0.0)) for b in pre_london_bars]) if pre_london_bars else current_high
        pre_london_low = min([float(b.get("low", 0.0)) for b in pre_london_bars]) if pre_london_bars else current_low
        asian_range = pre_london_high - pre_london_low

        donchian_high20 = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
        donchian_low20 = min(lows[-21:-1]) if len(lows) >= 21 else min(lows)

        prec = _PRICE_PRECISION.get(sym_clean, 4)

        for spec in specs:
            name_lower = spec.name.lower()
            if spec.name in cooldowns or name_lower in cooldowns:
                report.cooldown_playbooks.append(spec.name)
                continue

            signal: Optional[PlaybookTriggerSignal] = None

            # Archetype 1: London Open Volume Expansion Breakout
            if "london_expansion" in name_lower:
                if hour_utc in (7, 8, 9):
                    vol_ok = current_vol >= 1.05 * avg_vol20
                    if current_close > pre_london_high and current_close > current_open and vol_ok:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Hour {hour_utc}:00 UTC aligns with European liquidity expansion window (07:00-09:00 UTC)",
                                f"H1 Close ({current_close:.{prec}f}) broke strictly above pre-London high ({pre_london_high:.{prec}f})",
                                f"Tick volume ({current_vol:.0f}) confirms volume expansion (>= 1.05x 20-MA {avg_vol20:.0f})",
                            ],
                            macro_regime,
                        )
                    elif current_close < pre_london_low and current_close < current_open and vol_ok:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Hour {hour_utc}:00 UTC aligns with European liquidity expansion window (07:00-09:00 UTC)",
                                f"H1 Close ({current_close:.{prec}f}) broke strictly below pre-London low ({pre_london_low:.{prec}f})",
                                f"Tick volume ({current_vol:.0f}) confirms volume expansion (>= 1.05x 20-MA {avg_vol20:.0f})",
                            ],
                            macro_regime,
                        )
                else:
                    report.monitoring_playbooks.append(
                        {
                            "name": spec.name,
                            "status": f"Inactive outside London open window (Current: {hour_utc:02d}:00 UTC)",
                        }
                    )

            # Archetype 2: Asian Range Breakout
            elif "asian_range_breakout" in name_lower:
                if hour_utc in (7, 8):
                    if current_close > pre_london_high and current_close > ema50:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Hour {hour_utc}:00 UTC Asian session breakout",
                                f"H1 Close ({current_close:.{prec}f}) broke above Asian range ({pre_london_high:.{prec}f})",
                                f"Trend alignment: Close > EMA50 ({ema50:.{prec}f})",
                            ],
                            macro_regime,
                        )
                    elif current_close < pre_london_low and current_close < ema50:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Hour {hour_utc}:00 UTC Asian session breakdown",
                                f"H1 Close ({current_close:.{prec}f}) broke below Asian range ({pre_london_low:.{prec}f})",
                                f"Trend alignment: Close < EMA50 ({ema50:.{prec}f})",
                            ],
                            macro_regime,
                        )

            # Archetype 3: Tokyo / Asian Range Fade (Mean Reversion)
            elif "tokyo_range_fade" in name_lower or "asian_range_fade" in name_lower:
                if hour_utc in (1, 2, 3, 4, 5):
                    near_high = current_high >= pre_london_high - (0.2 * atr)
                    near_low = current_low <= pre_london_low + (0.2 * atr)
                    if near_high and current_close < current_open and rsi > 58:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Tokyo Session ({hour_utc:02d}:00 UTC) range fade setup",
                                f"Tested upper Asian boundary ({pre_london_high:.{prec}f}) with bearish rejection candle",
                                f"RSI exhausted ({rsi:.1f} > 58)",
                            ],
                            macro_regime,
                        )
                    elif near_low and current_close > current_open and rsi < 42:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Tokyo Session ({hour_utc:02d}:00 UTC) range fade setup",
                                f"Tested lower Asian boundary ({pre_london_low:.{prec}f}) with bullish rejection candle",
                                f"RSI oversold ({rsi:.1f} < 42)",
                            ],
                            macro_regime,
                        )

            # Archetype 4: New York Reversal / Morning Thrust
            elif "ny_reversal" in name_lower:
                if hour_utc in (13, 14, 15, 16):
                    # False break of prior extreme with immediate reversal bar
                    prior_high = max(highs[-5:-1]) if len(highs) >= 5 else current_high
                    prior_low = min(lows[-5:-1]) if len(lows) >= 5 else current_low
                    if (
                        current_high >= prior_high
                        and current_close < current_open
                        and (current_high - current_close) > (current_close - current_low)
                    ):
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"NY Session ({hour_utc:02d}:00 UTC) liquidity grab & reversal",
                                f"Swept liquidity above {prior_high:.{prec}f} with strong bearish rejection wick",
                            ],
                            macro_regime,
                        )
                    elif (
                        current_low <= prior_low
                        and current_close > current_open
                        and (current_close - current_low) > (current_high - current_close)
                    ):
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"NY Session ({hour_utc:02d}:00 UTC) liquidity grab & reversal",
                                f"Swept liquidity below {prior_low:.{prec}f} with strong bullish rejection wick",
                            ],
                            macro_regime,
                        )

            # Archetype 5: London Fix Reversal
            elif "london_fix_reversal" in name_lower:
                if hour_utc in (15, 16, 17):
                    if rsi > 65 and current_close < current_open:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"London Fix ({hour_utc:02d}:00 UTC) rebalancing exhaustion",
                                f"RSI stretched ({rsi:.1f} > 65) with bearish closing momentum",
                            ],
                            macro_regime,
                        )
                    elif rsi < 35 and current_close > current_open:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"London Fix ({hour_utc:02d}:00 UTC) rebalancing exhaustion",
                                f"RSI oversold ({rsi:.1f} < 35) with bullish closing momentum",
                            ],
                            macro_regime,
                        )

            # Archetype 6: 20-Period Donchian Channel Breakout
            elif "donchian_breakout" in name_lower:
                if current_close > donchian_high20 and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"20-bar Donchian High Breakout ({donchian_high20:.{prec}f})",
                            f"Impulse close ({current_close:.{prec}f}) above 20-period highest high",
                        ],
                        macro_regime,
                    )
                elif current_close < donchian_low20 and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"20-bar Donchian Low Breakdown ({donchian_low20:.{prec}f})",
                            f"Impulse close ({current_close:.{prec}f}) below 20-period lowest low",
                        ],
                        macro_regime,
                    )

            # Archetype 7: EMA Trend Retest & Cross
            elif "ema9_21_cross" in name_lower or "ema_trend_retest" in name_lower:
                if ema9 > ema21 and ema21 > ema50:
                    # Bullish trend alignment: retest near EMA21
                    if current_low <= ema21 + (0.15 * atr) and current_close > ema21:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Structured EMA Trend Alignment: EMA9 ({ema9:.{prec}f}) > EMA21 ({ema21:.{prec}f}) > EMA50 ({ema50:.{prec}f})",
                                f"Price pulled back to EMA21 support zone and held",
                            ],
                            macro_regime,
                        )
                elif ema9 < ema21 and ema21 < ema50:
                    # Bearish trend alignment: retest near EMA21
                    if current_high >= ema21 - (0.15 * atr) and current_close < ema21:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Structured EMA Trend Alignment: EMA9 ({ema9:.{prec}f}) < EMA21 ({ema21:.{prec}f}) < EMA50 ({ema50:.{prec}f})",
                                f"Price rallied to EMA21 resistance zone and rejected",
                            ],
                            macro_regime,
                        )

            # Archetype 8: Bollinger Band Mean Reversion
            elif "bollinger_reversion" in name_lower:
                std20 = math.sqrt(sum((c - ema21) ** 2 for c in closes[-20:]) / 20.0) if len(closes) >= 20 else atr
                upper_bb = ema21 + (2.0 * std20)
                lower_bb = ema21 - (2.0 * std20)
                if current_high >= upper_bb and current_close < upper_bb and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Price pierced 2.0-std Upper Bollinger Band ({upper_bb:.{prec}f})",
                            f"Bearish mean-reversion candle closed back inside bands",
                        ],
                        macro_regime,
                    )
                elif current_low <= lower_bb and current_close > lower_bb and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Price pierced 2.0-std Lower Bollinger Band ({lower_bb:.{prec}f})",
                            f"Bullish mean-reversion candle closed back inside bands",
                        ],
                        macro_regime,
                    )

            # Archetype 9: RSI Extreme Reversal
            elif "rsi_extreme_reversal" in name_lower or "rsi_trend_pullback" in name_lower:
                if rsi >= 70 and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"RSI Overbought Extreme ({rsi:.1f} >= 70)",
                            f"Bearish confirmation close ({current_close:.{prec}f} < {current_open:.{prec}f})",
                        ],
                        macro_regime,
                    )
                elif rsi <= 30 and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"RSI Oversold Extreme ({rsi:.1f} <= 30)",
                            f"Bullish confirmation close ({current_close:.{prec}f} > {current_open:.{prec}f})",
                        ],
                        macro_regime,
                    )

            # Archetype 10: ATR Volatility Impulse
            elif "atr_impulse" in name_lower:
                bar_range = current_high - current_low
                if bar_range >= 1.5 * atr and current_vol >= 1.2 * avg_vol20:
                    if current_close > current_open and current_close > ema50:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"ATR Volatility Expansion bar ({bar_range:.{prec}f} >= 1.5x ATR {atr:.{prec}f})",
                                f"Volume surge ({current_vol:.0f} >= 1.2x avg {avg_vol20:.0f}) with trend alignment > EMA50",
                            ],
                            macro_regime,
                        )
                    elif current_close < current_open and current_close < ema50:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"ATR Volatility Expansion bar ({bar_range:.{prec}f} >= 1.5x ATR {atr:.{prec}f})",
                                f"Volume surge ({current_vol:.0f} >= 1.2x avg {avg_vol20:.0f}) with trend alignment < EMA50",
                            ],
                            macro_regime,
                        )

            # Archetype 11: General Trend / Breakout / Reversion Fallback Matching
            elif spec.regime == "breakout":
                if current_close > donchian_high20 and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [f"Breakout regime match: New 20-bar high ({donchian_high20:.{prec}f})"],
                        macro_regime,
                    )
                elif current_close < donchian_low20 and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [f"Breakout regime match: New 20-bar low ({donchian_low20:.{prec}f})"],
                        macro_regime,
                    )

            if signal is not None:
                report.active_signals.append(signal)

        # Sort active signals: ALIGNED macro first, then highest profit factor
        def _sort_key(s: PlaybookTriggerSignal) -> Tuple[int, float]:
            macro_score = 2 if s.macro_alignment == "ALIGNED" else (1 if s.macro_alignment == "NEUTRAL" else 0)
            return (macro_score, s.historical_pf)

        report.active_signals.sort(key=_sort_key, reverse=True)
        return report

    @classmethod
    def _create_signal(
        cls,
        spec: PlaybookSpec,
        direction: str,
        entry: float,
        atr: float,
        precision: int,
        reasons: List[str],
        macro_regime: Optional[str] = None,
    ) -> PlaybookTriggerSignal:
        """Calculate calibrated SL, TP, and R:R parameters adhering to empirical invariants."""
        sl_dist = max(atr * 0.5, spec.sl_atr_mult * atr)
        tp_dist = max(sl_dist * spec.min_rr, spec.tp_atr_mult * atr)

        if direction == "BUY":
            sl_price = round(entry - sl_dist, precision)
            tp_price = round(entry + tp_dist, precision)
        else:
            sl_price = round(entry + sl_dist, precision)
            tp_price = round(entry - tp_dist, precision)

        real_sl_dist = abs(entry - sl_price)
        real_tp_dist = abs(tp_price - entry)
        rr = round(real_tp_dist / max(1e-6, real_sl_dist), 2)

        # Macro Alignment Evaluation
        macro_align = "NEUTRAL"
        if macro_regime:
            m_clean = macro_regime.lower()
            if direction == "BUY":
                if any(w in m_clean for w in ["bullish", "risk_on", "weak_dollar", "expansion"]):
                    macro_align = "ALIGNED"
                elif any(w in m_clean for w in ["bearish", "risk_off", "strong_dollar", "contraction"]):
                    macro_align = "OPPOSED"
            else:
                if any(w in m_clean for w in ["bearish", "risk_off", "strong_dollar", "contraction"]):
                    macro_align = "ALIGNED"
                elif any(w in m_clean for w in ["bullish", "risk_on", "weak_dollar", "expansion"]):
                    macro_align = "OPPOSED"

        base_conf = 0.70 + min(0.20, (spec.profit_factor - 1.0) * 0.15)
        if macro_align == "ALIGNED":
            base_conf = min(0.95, base_conf + 0.10)
        elif macro_align == "OPPOSED":
            base_conf = max(0.40, base_conf - 0.15)

        return PlaybookTriggerSignal(
            playbook_name=spec.name,
            symbol=spec.symbol,
            direction=direction,
            entry_price=round(entry, precision),
            sl_price=sl_price,
            tp_price=tp_price,
            sl_distance=round(real_sl_dist, precision),
            tp_distance=round(real_tp_dist, precision),
            rr_ratio=rr,
            max_hold_bars=spec.max_hold_bars,
            historical_pf=spec.profit_factor,
            historical_win_rate=spec.win_rate,
            historical_sharpe=spec.sharpe_ratio,
            historical_max_dd=spec.max_drawdown_pct,
            trigger_reasons=reasons,
            macro_alignment=macro_align,
            confidence=round(base_conf, 2),
        )
