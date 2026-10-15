"""
Deterministic Playbook Signal Screener Engine.

Evaluates multi-asset empirical trading playbooks against active price bars,
technical indicators, and session timings in pure Python.
Operates deterministically (<1ms) to eliminate LLM arithmetic hallucinations
and provide grounded quantitative confluence signals to Stage 2 analysis.
"""

from __future__ import annotations

import json
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
    def load_reserve_playbooks(cls, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load quantitative reserve playbooks from reserve_catalog.json."""
        pb_dir = cls.get_playbooks_dir()
        catalog_path = pb_dir / "reserve_catalog.json"
        if not catalog_path.exists():
            return []
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            if symbol:
                sym_clean = symbol.strip().upper()
                res = data.get(sym_clean, [])
                return res if isinstance(res, list) else []
            all_reserves: List[Dict[str, Any]] = []
            for plist in data.values():
                if isinstance(plist, list):
                    all_reserves.extend(plist)
            return all_reserves
        except Exception as e:
            logger.debug(f"Failed loading reserve catalog: {e}")
            return []

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
        raw_regime = str(fm.get("regime", "trending")).lower().strip()
        if raw_regime in ("trend", "trending"):
            regime = "trending"
        elif raw_regime in ("range", "ranging", "mean_reverting", "mean_reversion"):
            regime = "mean_reverting"
        elif raw_regime in ("breakout", "momentum"):
            regime = "breakout"
        elif raw_regime in ("volatile", "volatility"):
            regime = "volatile"
        else:
            regime = raw_regime
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
    def compute_stoch(
        cls,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        k_period: int = 14,
        d_period: int = 3,
    ) -> Tuple[float, float]:
        """Compute Fast/Slow Stochastic Oscillator (%K, %D)."""
        if len(closes) < k_period + d_period:
            return 50.0, 50.0

        k_values: List[float] = []
        for i in range(len(closes) - d_period, len(closes)):
            window_high = max(highs[max(0, i - k_period + 1) : i + 1])
            window_low = min(lows[max(0, i - k_period + 1) : i + 1])
            denom = window_high - window_low
            k = ((closes[i] - window_low) / max(1e-8, denom)) * 100.0
            k_values.append(k)

        curr_k = k_values[-1]
        curr_d = sum(k_values) / float(len(k_values))
        return float(curr_k), float(curr_d)

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
        ema20 = cls.compute_ema(closes, 20)
        ema21 = cls.compute_ema(closes, 21)
        ema34 = cls.compute_ema(closes, 34)
        ema40 = cls.compute_ema(closes, 40)
        ema50 = cls.compute_ema(closes, 50)
        ema200 = cls.compute_ema(closes, 200)
        avg_vol20 = sum(volumes[-20:]) / max(1.0, len(volumes[-20:])) if len(volumes) >= 5 else 1.0

        # Session & Bar Timing
        hour_utc = now.hour
        pre_london_bars = bars[-8:-1] if len(bars) >= 8 else bars[:-1]
        pre_london_high = max([float(b.get("high", 0.0)) for b in pre_london_bars]) if pre_london_bars else current_high
        pre_london_low = min([float(b.get("low", 0.0)) for b in pre_london_bars]) if pre_london_bars else current_low
        asian_range = pre_london_high - pre_london_low

        # Dynamic Donchian channel helper
        def _get_donchian(p_bars: int) -> Tuple[float, float]:
            p = max(2, min(p_bars, len(highs) - 1))
            h_win = highs[-p - 1 : -1] if len(highs) >= p + 1 else highs[:-1]
            l_win = lows[-p - 1 : -1] if len(lows) >= p + 1 else lows[:-1]
            dh = max(h_win) if h_win else current_high
            dl = min(l_win) if l_win else current_low
            return dh, dl

        donchian_high20, donchian_low20 = _get_donchian(20)

        # 20-period standard deviation for Bollinger Band evaluations
        sma20 = sum(closes[-20:]) / max(1.0, len(closes[-20:])) if len(closes) >= 20 else current_close
        std20 = math.sqrt(sum((c - sma20) ** 2 for c in closes[-20:]) / 20.0) if len(closes) >= 20 else max(atr, 1e-4)

        # Fast Stochastic (14, 3)
        stoch14_k, stoch14_d = cls.compute_stoch(closes, highs, lows, 14, 3)

        # Wick and Body characteristics for Rejection / Pinbar detection
        upper_wick = current_high - max(current_open, current_close)
        lower_wick = min(current_open, current_close) - current_low
        candle_body = abs(current_close - current_open)
        swing_high12 = max(highs[-13:-1]) if len(highs) >= 13 else current_high
        swing_low12 = min(lows[-13:-1]) if len(lows) >= 13 else current_low

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

            # Archetype 3: Tokyo / Asian Range Fade & Drift (Mean Reversion)
            elif (
                "tokyo_range_fade" in name_lower
                or "asian_range_fade" in name_lower
                or "tokyo_w" in name_lower
                or "asian_lunch_drift" in name_lower
            ):
                if hour_utc in (1, 2, 3, 4, 5, 6):
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
                                f"Tokyo/Asian Session ({hour_utc:02d}:00 UTC) range fade setup",
                                f"Tested upper boundary ({pre_london_high:.{prec}f}) with bearish rejection candle",
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
                                f"Tokyo/Asian Session ({hour_utc:02d}:00 UTC) range fade setup",
                                f"Tested lower boundary ({pre_london_low:.{prec}f}) with bullish rejection candle",
                                f"RSI oversold ({rsi:.1f} < 42)",
                            ],
                            macro_regime,
                        )

            # Archetype 4: New York Reversal / Morning Thrust
            elif "ny_reversal" in name_lower:
                if hour_utc in (13, 14, 15, 16):
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

            # Archetype 6: Donchian Channel Breakouts (Dynamic N-Period)
            elif "donchian" in name_lower or "dch_" in name_lower:
                m_dch = re.search(r"(?:dch|donchian)_(\d+)", name_lower)
                dch_period = int(m_dch.group(1)) if m_dch else 20
                dch_h, dch_l = _get_donchian(dch_period)
                if current_close > dch_h and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"{dch_period}-bar Donchian High Breakout ({dch_h:.{prec}f})",
                            f"Impulse close ({current_close:.{prec}f}) above {dch_period}-period highest high",
                        ],
                        macro_regime,
                    )
                elif current_close < dch_l and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"{dch_period}-bar Donchian Low Breakdown ({dch_l:.{prec}f})",
                            f"Impulse close ({current_close:.{prec}f}) below {dch_period}-period lowest low",
                        ],
                        macro_regime,
                    )

            # Archetype 7: EMA Bounces & Trend Retests (Dynamic Period P: 9, 20, 21, 34, 40, 50, 200)
            elif "ema" in name_lower and (
                "bounce" in name_lower
                or "retest" in name_lower
                or "touch" in name_lower
                or "cross" in name_lower
                or "ribbon" in name_lower
                or "pullback" in name_lower
            ):
                m_ema = re.search(r"ema(\d+)", name_lower)
                ema_p_num = int(m_ema.group(1)) if m_ema else 21
                if ema_p_num == 9:
                    ema_target = ema9
                elif ema_p_num == 20:
                    ema_target = ema20
                elif ema_p_num == 21:
                    ema_target = ema21
                elif ema_p_num == 34:
                    ema_target = ema34
                elif ema_p_num == 40:
                    ema_target = ema40
                elif ema_p_num == 50:
                    ema_target = ema50
                elif ema_p_num == 200:
                    ema_target = ema200
                else:
                    ema_target = cls.compute_ema(closes, ema_p_num)

                bullish_context = (ema9 > ema21) or (current_close > ema50)
                bearish_context = (ema9 < ema21) or (current_close < ema50)

                if bullish_context and current_low <= ema_target + (0.25 * atr) and current_close >= ema_target:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"EMA{ema_p_num} ({ema_target:.{prec}f}) dynamic trend support bounce",
                            f"Price held EMA{ema_p_num} buffer and closed bullish ({current_close:.{prec}f})",
                        ],
                        macro_regime,
                    )
                elif bearish_context and current_high >= ema_target - (0.25 * atr) and current_close <= ema_target:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"EMA{ema_p_num} ({ema_target:.{prec}f}) dynamic trend resistance rejection",
                            f"Price rejected EMA{ema_p_num} buffer and closed bearish ({current_close:.{prec}f})",
                        ],
                        macro_regime,
                    )

            # Archetype 8: Bollinger Band & Standard Deviation Fades (bb_15, bb_20, bb_25, dev10, dev13, etc.)
            elif "bollinger" in name_lower or "bb" in name_lower or "dev" in name_lower:
                m_bb = re.search(r"(?:bb_?|dev)(\d+)", name_lower)
                if m_bb:
                    raw_dev = int(m_bb.group(1))
                    bb_mult = raw_dev / 10.0 if raw_dev >= 10 else float(raw_dev)
                else:
                    bb_mult = 2.0

                upper_bb = ema21 + (bb_mult * std20)
                lower_bb = ema21 - (bb_mult * std20)

                if current_high >= upper_bb and current_close < upper_bb and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Price pierced {bb_mult:.1f}-std Upper Band ({upper_bb:.{prec}f})",
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
                            f"Price pierced {bb_mult:.1f}-std Lower Band ({lower_bb:.{prec}f})",
                            f"Bullish mean-reversion candle closed back inside bands",
                        ],
                        macro_regime,
                    )

            # Archetype 9: Stochastic Oscillator Crosses & Pullbacks (stoch8, stoch10, stoch14, stoch21)
            elif "stoch" in name_lower:
                m_st = re.search(r"stoch(\d+)", name_lower)
                k_per = int(m_st.group(1)) if m_st else 14
                k_val, d_val = (
                    (stoch14_k, stoch14_d) if k_per == 14 else cls.compute_stoch(closes, highs, lows, k_per, 3)
                )

                if k_val < 35 and k_val > d_val and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Stochastic({k_per}) oversold bullish cross (%K={k_val:.1f} > %D={d_val:.1f})",
                            f"Bullish close confirming upward momentum",
                        ],
                        macro_regime,
                    )
                elif k_val > 65 and k_val < d_val and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Stochastic({k_per}) overbought bearish cross (%K={k_val:.1f} < %D={d_val:.1f})",
                            f"Bearish close confirming downward momentum",
                        ],
                        macro_regime,
                    )
                elif "trend" in name_lower or "confluence" in name_lower:
                    if current_close > ema50 and k_val > d_val and k_val < 65 and current_close > current_open:
                        signal = cls._create_signal(
                            spec,
                            "BUY",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Stochastic({k_per}) trend-pullback cross aligned > EMA50",
                                f"K={k_val:.1f} crossed above D={d_val:.1f}",
                            ],
                            macro_regime,
                        )
                    elif current_close < ema50 and k_val < d_val and k_val > 35 and current_close < current_open:
                        signal = cls._create_signal(
                            spec,
                            "SELL",
                            current_close,
                            atr,
                            prec,
                            [
                                f"Stochastic({k_per}) trend-pullback cross aligned < EMA50",
                                f"K={k_val:.1f} crossed below D={d_val:.1f}",
                            ],
                            macro_regime,
                        )

            # Archetype 10: Pinbar / Rejection Swings / Star Reversals / Sweep-Reenters
            elif (
                "pinbar" in name_lower
                or "rejection_swing" in name_lower
                or "star_reversal" in name_lower
                or "sweep_reenter" in name_lower
            ):
                if (
                    current_high >= swing_high12 - (0.15 * atr)
                    and upper_wick >= 1.6 * max(candle_body, 0.08 * atr)
                    and current_close < current_open
                ):
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Liquidity grab & rejection wick ({upper_wick:.{prec}f} >= 1.6x body) at swing high ({swing_high12:.{prec}f})",
                            f"Bearish confirmation close below open",
                        ],
                        macro_regime,
                    )
                elif (
                    current_low <= swing_low12 + (0.15 * atr)
                    and lower_wick >= 1.6 * max(candle_body, 0.08 * atr)
                    and current_close > current_open
                ):
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Liquidity grab & rejection wick ({lower_wick:.{prec}f} >= 1.6x body) at swing low ({swing_low12:.{prec}f})",
                            f"Bullish confirmation close above open",
                        ],
                        macro_regime,
                    )

            # Archetype 11: Consecutive Candle Exhaustion / Fade / Multi-Bar Reversals
            elif (
                "consec" in name_lower
                or "consecutive" in name_lower
                or "two_bar" in name_lower
                or "three_bar" in name_lower
            ):
                m_con = re.search(r"(\d+)bar", name_lower)
                consec_target = int(m_con.group(1)) if m_con else 3
                prior_bars = bars[-consec_target - 1 : -1] if len(bars) >= consec_target + 1 else []
                all_prior_bull = len(prior_bars) >= consec_target and all(
                    float(b.get("close", 0.0)) > float(b.get("open", 0.0)) for b in prior_bars
                )
                all_prior_bear = len(prior_bars) >= consec_target and all(
                    float(b.get("close", 0.0)) < float(b.get("open", 0.0)) for b in prior_bars
                )

                if all_prior_bull and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"{consec_target}-bar bullish streak exhaustion",
                            f"Reversal candle confirmed ({current_close:.{prec}f} < {current_open:.{prec}f})",
                        ],
                        macro_regime,
                    )
                elif all_prior_bear and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"{consec_target}-bar bearish streak exhaustion",
                            f"Reversal candle confirmed ({current_close:.{prec}f} > {current_open:.{prec}f})",
                        ],
                        macro_regime,
                    )

            # Archetype 12: Fair Value Gap (FVG) Retests & Mitigation
            elif "fvg" in name_lower:
                has_bull_fvg = len(bars) >= 4 and float(bars[-2].get("low", 0.0)) > float(bars[-4].get("high", 0.0))
                has_bear_fvg = len(bars) >= 4 and float(bars[-2].get("high", 0.0)) < float(bars[-4].get("low", 0.0))
                if has_bull_fvg and current_low <= float(bars[-2].get("low", 0.0)) and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Bullish Fair Value Gap (FVG) retest & mitigation bounce",
                            f"H1 close ({current_close:.{prec}f}) confirmed institutional demand",
                        ],
                        macro_regime,
                    )
                elif has_bear_fvg and current_high >= float(bars[-2].get("high", 0.0)) and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Bearish Fair Value Gap (FVG) retest & mitigation rejection",
                            f"H1 close ({current_close:.{prec}f}) confirmed institutional supply",
                        ],
                        macro_regime,
                    )

            # Archetype 13: Average Daily Range (ADR) Extreme Fade & Exhaustion
            elif "adr" in name_lower:
                day_high = max(highs[-14:]) if len(highs) >= 14 else current_high
                day_low = min(lows[-14:]) if len(lows) >= 14 else current_low
                day_span = day_high - day_low
                is_adr_exhausted = day_span >= 0.85 * (atr * 4.0)

                if (
                    is_adr_exhausted
                    and current_high >= day_high - (0.1 * atr)
                    and rsi >= 65
                    and current_close < current_open
                ):
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Intraday Range Exhaustion ({day_span:.{prec}f} >= 85% expected ADR)",
                            f"RSI overbought ({rsi:.1f}) with bearish reversal close",
                        ],
                        macro_regime,
                    )
                elif (
                    is_adr_exhausted
                    and current_low <= day_low + (0.1 * atr)
                    and rsi <= 35
                    and current_close > current_open
                ):
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Intraday Range Exhaustion ({day_span:.{prec}f} >= 85% expected ADR)",
                            f"RSI oversold ({rsi:.1f}) with bullish reversal close",
                        ],
                        macro_regime,
                    )

            # Archetype 14: Supertrend Trend Bounce
            elif "supertrend" in name_lower:
                if current_close > ema50 and current_low <= ema50 + (0.25 * atr) and current_close > current_open:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Supertrend dynamic trendline support held above EMA50 ({ema50:.{prec}f})",
                            f"Bullish continuation impulse close",
                        ],
                        macro_regime,
                    )
                elif current_close < ema50 and current_high >= ema50 - (0.25 * atr) and current_close < current_open:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Supertrend dynamic trendline resistance held below EMA50 ({ema50:.{prec}f})",
                            f"Bearish continuation impulse close",
                        ],
                        macro_regime,
                    )

            # Archetype 15: RSI Extreme Reversal
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

            # Archetype 16: ATR Volatility Impulse
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

            # Archetype 17: General Trend / Breakout / Reversion Fallback Matching
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
            elif spec.regime == "trending":
                if current_close > ema50 and current_close > current_open and ema21 > ema50:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [f"Trend regime alignment: Close ({current_close:.{prec}f}) > EMA50 and EMA21 > EMA50"],
                        macro_regime,
                    )
                elif current_close < ema50 and current_close < current_open and ema21 < ema50:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [f"Trend regime alignment: Close ({current_close:.{prec}f}) < EMA50 and EMA21 < EMA50"],
                        macro_regime,
                    )
            elif spec.regime == "mean_reverting":
                if current_low <= donchian_low20 + (0.35 * atr) and current_close > current_open and rsi <= 42:
                    signal = cls._create_signal(
                        spec,
                        "BUY",
                        current_close,
                        atr,
                        prec,
                        [f"Mean-reverting support bounce: Low near 20-bar low, RSI oversold ({rsi:.1f} <= 42)"],
                        macro_regime,
                    )
                elif current_high >= donchian_high20 - (0.35 * atr) and current_close < current_open and rsi >= 58:
                    signal = cls._create_signal(
                        spec,
                        "SELL",
                        current_close,
                        atr,
                        prec,
                        [
                            f"Mean-reverting resistance rejection: High near 20-bar high, RSI overbought ({rsi:.1f} >= 58)"
                        ],
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
