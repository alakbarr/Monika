# ==============================================================================
# File: risk/risk_gate.py
# ==============================================================================

"""
Risk Gate — Layer validasi pra-eksekusi. Sistem yang memutuskan, bukan AI.

Aturan Utama:
  Semua order yang diajukan akan divalidasi terhadap seluruh aturan berikut:
    1. Drawdown harian tidak melampaui batas
    2. Posisi terbuka (concurrent) tidak melebihi batas
    3. Batas posisi per simbol (hanya 1 posisi terbuka per simbol)
    4. Ukuran posisi (lot) dalam rentang yang valid
    5. Bebas dari jadwal rilis berita high-impact (dalam jeda waktu)
    6. Paparan korelasi antar aset (correlation heat) aman
    7. Trading tidak sedang dipause secara manual

Jika ADA SATU SAJA yang gagal → order ditolak dan dicatat di orders_log.
"""

import asyncio
from decimal import Decimal
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import (
    Position, RiskState, EconomicCalendar, OrderLog, TradeOutcome, PaperTradeRecord, AssetAnalysis, SystemConfig
)
from risk.position_sizing import SizingResult

logger = logging.getLogger("TradingAgent.RiskGate")



# Simpler: track per base-currency exposure
from utils.market.currency_utils import SYMBOL_CURRENCIES, get_symbol_currencies


# ---------------------------------------------------------------------------
# Verdict dataclass
# ---------------------------------------------------------------------------

@dataclass
class RiskVerdict:
    """Hasil pengecekan dari Risk Gate."""
    approved: bool
    symbol: str
    proposed_lots: float
    checks_passed: list[str]
    checks_failed: list[str]
    rejection_reasons: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=clock.now)

    def summary(self) -> str:
        status = "APPROVED" if self.approved else f"REJECTED"
        reasons = f" — {'; '.join(self.rejection_reasons)}" if self.rejection_reasons else ""
        return f"RiskGate [{status}] {self.symbol} {self.proposed_lots}lots{reasons}"


def get_trading_day_start(settings: dict, now: Optional[datetime] = None) -> datetime:
    """
    Menghitung waktu mulai hari perdagangan berdasarkan broker daily rollover.
    Default: 21:00 UTC (17:00 New York / NY Close), aware terhadap Daylight Saving Time.
    """
    if now is None:
        from utils.clock import now as get_clock_now
        now = get_clock_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
        
    risk_cfg = (settings or {}).get("trading", {}).get("risk", {})
    rollover_hour_cfg = risk_cfg.get("daily_rollover_utc_hour")
    
    # 1. Jika konfigurasi eksplisit jam 0 (midnight UTC)
    if rollover_hour_cfg is not None and int(rollover_hour_cfg) == 0:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 2. Broker Timezone Dynamic Calculation (Default: America/New_York at 17:00 Close)
    broker_tz_name = risk_cfg.get("broker_timezone", "America/New_York")
    broker_rollover_hour = int(risk_cfg.get("broker_rollover_hour", 17))
    
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(broker_tz_name)
        now_tz = now.astimezone(tz)
        if now_tz.hour >= broker_rollover_hour:
            tz_start = now_tz.replace(hour=broker_rollover_hour, minute=0, second=0, microsecond=0)
        else:
            from datetime import timedelta
            tz_start = (now_tz - timedelta(days=1)).replace(hour=broker_rollover_hour, minute=0, second=0, microsecond=0)
        return tz_start.astimezone(timezone.utc)
    except Exception:
        rollover_hour = int(rollover_hour_cfg if rollover_hour_cfg is not None else 21)
        if now.hour >= rollover_hour:
            return now.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)
        else:
            from datetime import timedelta
            yesterday = now - timedelta(days=1)
            return yesterday.replace(hour=rollover_hour, minute=0, second=0, microsecond=0)


def get_daily_risk_cutoff(now: datetime, risk_cfg: dict) -> datetime:
    """Helper alias untuk get_trading_day_start dengan parameter (now, risk_cfg)."""
    return get_trading_day_start({"trading": {"risk": risk_cfg}}, now)


# ---------------------------------------------------------------------------
# Risk Gate
# ---------------------------------------------------------------------------

class RiskGate:
    """Memvalidasi order terhadap semua aturan risiko yang ada."""

    def __init__(self, settings: dict, mt5_client=None, flash_crash_detector=None):
        """
        Args:
        settings:   Full settings dict (uses trading.risk section).
        mt5_client: Optional live MT5Client for real-time account info.
        flash_crash_detector: Optional FlashCrashDetector instance.
        """
        risk_cfg = settings.get("trading", {}).get("risk", {})
        self.settings = settings
        self.max_daily_drawdown_pct: float = risk_cfg.get("max_daily_drawdown_percent", 3.0)
        self.max_concurrent:          int   = risk_cfg.get("max_concurrent_positions", 5)
        self.correlation_limit:       int   = risk_cfg.get("correlation_limit", 3)
        self.news_window_minutes:     int   = risk_cfg.get("news_window_minutes", 15)
        self._mt5 = mt5_client
        self.flash_crash_detector = flash_crash_detector
        from risk.correlation_matrix import DynamicCorrelationMatrix
        self.dynamic_correlation_matrix = DynamicCorrelationMatrix(
            rolling_days=int(risk_cfg.get("correlation_rolling_days", 30)),
            correlation_threshold=float(risk_cfg.get("correlation_threshold", 0.65)),
        )
        self.correlation_matrix = self.dynamic_correlation_matrix

    def update_parameters(self, new_risk_cfg: dict) -> None:
        """Hot-reload risk parameters dynamically without restarting."""
        if not new_risk_cfg or not isinstance(new_risk_cfg, dict):
            return
        cfg = (
            new_risk_cfg.get("trading", {}).get("risk", {})
            if "trading" in new_risk_cfg
            else new_risk_cfg.get("risk", new_risk_cfg)
        )
        if "max_daily_drawdown_percent" in cfg:
            self.max_daily_drawdown_pct = float(cfg["max_daily_drawdown_percent"])
        if "max_concurrent_positions" in cfg:
            self.max_concurrent = int(cfg["max_concurrent_positions"])
        if "correlation_limit" in cfg:
            self.correlation_limit = int(cfg["correlation_limit"])
        if "news_window_minutes" in cfg:
            self.news_window_minutes = int(cfg["news_window_minutes"])
        if "correlation_threshold" in cfg and hasattr(self, "dynamic_correlation_matrix"):
            self.dynamic_correlation_matrix.correlation_threshold = float(cfg["correlation_threshold"])

        if "trading" in self.settings and "risk" in self.settings["trading"]:
            self.settings["trading"]["risk"].update(cfg)
        logger.info(
            f"[RiskGate] Risk parameters hot-reloaded: "
            f"max_daily_drawdown={self.max_daily_drawdown_pct}%, "
            f"max_concurrent={self.max_concurrent}, "
            f"news_window={self.news_window_minutes}m"
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        session: AsyncSession,
        symbol: str,
        direction: str,
        sizing: SizingResult,
        account_equity: Optional[float] = None,
        analysis: Optional['AssetAnalysis'] = None,
        as_of: Optional[datetime] = None,
        simulated_positions: Optional[list] = None,
        simulated_equity: Optional[float] = None,
        simulated_daily_pnl: Optional[float] = None,
        is_backtest: bool = False,
        pair_group_id: Optional[str] = None,
        is_paper: Optional[bool] = None,
    ) -> RiskVerdict:
        """
        Memvalidasi semua aturan risiko pra-eksekusi.

        Args:
            session: Sesi DB.
            symbol: Simbol aset.
            direction: Arah trade ('buy' atau 'sell').
            sizing: Hasil position sizing.
            account_equity: Ekuitas akun live dari broker atau simulasi backtest.
            analysis: Analisis aset terkait jika ada.
            as_of: Timestamp simulasi waktu jika mode backtest/point-in-time.
            simulated_positions: List posisi terbuka virtual saat simulasi backtest.
            simulated_equity: Ekuitas simulasi saat mode backtest.
            simulated_daily_pnl: PnL harian simulasi saat mode backtest.
            is_backtest: Flag apakah dieksekusi di bawah lingkungan backtest.
            pair_group_id: ID group multi-leg atau tranche jika order bagian dari sepasang leg.
            is_paper: Explicitly specify if trade is paper vs live (defaults to config check).
            
        Returns:
        RiskVerdict (diizinkan atau ditolak beserta alasannya).
        """
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        rejections:    list[str] = []

        effective_pair_group = pair_group_id or getattr(analysis, 'pair_group_id', None)
        fallback_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        equity = simulated_equity if (is_backtest and simulated_equity is not None) else (account_equity or fallback_equity)

        try:
            from utils.plugins.manager import get_plugin_manager, PluginHook
            await get_plugin_manager().emit(
                PluginHook.PRE_RISK_GATE,
                symbol=symbol,
                direction=direction,
                sizing=sizing,
                equity=equity,
                analysis=analysis,
            )
        except Exception as e:
            logger.debug(f"Plugin PRE_RISK_GATE error: {e}")

        async def run_check(name: str, coro):
            """Execute a single check and record pass/fail."""
            try:
                ok, reason = await coro
                if ok:
                    checks_passed.append(name)
                else:
                    checks_failed.append(name)
                    rejections.append(f"[{name}] {reason}")
            except Exception as e:
                checks_failed.append(name)
                rejections.append(f"[{name}] Check error: {e}")
                logger.error(f"RiskGate check '{name}' raised exception: {e}")

        checks = [
            ("daily_trade_count", self._check_daily_trade_count(session, is_backtest=is_backtest, is_paper=is_paper)),
            ("trading_not_paused", self._check_not_paused(session, is_backtest=is_backtest)),
            ("edge_status_not_paused", self._check_edge_status_not_paused(session, is_backtest=is_backtest)),
            ("vix_threshold", self._check_vix_threshold(session, as_of=as_of, is_backtest=is_backtest)),
            ("flash_crash_cooldown", self._check_flash_crash_cooldown(symbol)),
            ("sizing_valid", self._check_sizing_valid(sizing)),
            ("lot_size", self._check_lot_size(sizing)),
            ("daily_drawdown", self._check_daily_drawdown(session, equity, simulated_daily_pnl=simulated_daily_pnl, is_backtest=is_backtest)),
            ("weekly_drawdown", self._check_weekly_drawdown(session, equity, is_backtest=is_backtest)),
            ("max_concurrent_positions", self._check_max_positions(session, simulated_positions=simulated_positions)),
            ("no_duplicate_symbol", self._check_no_duplicate(session, symbol, simulated_positions=simulated_positions, pair_group_id=effective_pair_group)),
            ("portfolio_heat", self._check_total_portfolio_heat(session, sizing, equity, simulated_positions=simulated_positions)),
            ("weekend_proximity", self.assess_weekend_gap_risk(session, symbol, as_of=as_of)),
            ("rollover_window", self._check_rollover_window(symbol, as_of=as_of)),
            ("post_sl_cooldown", self._check_post_loss_cooldown(session, symbol, as_of=as_of, is_backtest=is_backtest)),
            ("news_window", self._check_news_window(session, symbol, as_of=as_of, is_backtest=is_backtest)),
            ("correlation_exposure", self._check_correlation(session, symbol, direction, simulated_positions=simulated_positions, as_of=as_of)),
            ("consecutive_losses", self._check_consecutive_losses(session, symbol, is_backtest=is_backtest)),
            ("data_freshness", self._check_data_freshness(session, symbol, as_of=as_of, is_backtest=is_backtest)),
            ("timesfm_expectancy", self._check_timesfm_expectancy(session, symbol, direction, sizing, is_backtest=is_backtest)),
            ("schmitt_regime", self._check_schmitt_regime(session, symbol, simulated_positions=simulated_positions, is_backtest=is_backtest)),
            ("vpin_toxicity", self._check_vpin_toxicity(session, symbol, as_of=as_of, is_backtest=is_backtest)),
        ]
        
        if analysis is not None:
            checks.append(("analysis_quality_scores", self._check_analysis_quality_scores(analysis)))
            
        for name, coro in checks:
            await run_check(name, coro)

        approved = len(checks_failed) == 0

        verdict = RiskVerdict(
            approved=approved,
            symbol=symbol,
            proposed_lots=sizing.recommended_lots,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            rejection_reasons=rejections,
        )

        # Log to orders_log only in live/paper execution (skip in backtest simulation to avoid polluting DB)
        if not is_backtest:
            await self._log_verdict(session, symbol, direction, sizing, verdict)
            try:
                from database.event_store import TradingEventStore
                await TradingEventStore.emit(
                    session=session,
                    event_type="risk.verdict",
                    payload={
                        "symbol": symbol,
                        "direction": direction,
                        "approved": approved,
                        "proposed_lots": sizing.recommended_lots,
                        "checks_passed": checks_passed,
                        "checks_failed": checks_failed,
                        "rejection_reasons": rejections,
                    },
                    correlation_id=f"risk_{symbol}_{clock.now().strftime('%Y%m%d%H%M%S')}",
                    actor="risk_gate",
                )
            except Exception as e:
                logger.debug(f"Event store emit risk.verdict failed: {e}")

        log_fn = logger.info if approved else logger.warning
        log_fn(verdict.summary())
        return verdict

    # Backward compatibility alias
    check = evaluate

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    async def _check_data_freshness(self, session: AsyncSession, symbol: str, as_of: Optional[datetime] = None, is_backtest: bool = False) -> tuple[bool, str]:
        """Tolak order jika data pasar (OHLCV/Indikator) basi atau tidak segar (hard gate)."""
        if is_backtest:
            return True, "backtest_freshness_ok"
        try:
            from utils.validation.data_validator import validate_data_freshness
            tfs = self.settings.get("trading", {}).get("timeframes", ["M15", "H1", "H4", "D1"]) if isinstance(self.settings, dict) else ["M15", "H1", "H4", "D1"]
            freshness = await validate_data_freshness(session, [symbol], tfs)
            if not freshness.get('ready', True):
                errors = "; ".join(freshness.get('errors', []))
                return False, f"Stale market data: {errors}"
            return True, "data_freshness_ok"
        except Exception as e:
            logger.warning(f"Data freshness check error for {symbol}: {e}")
            return False, f"Data freshness check failed: {e}"

    async def _check_timesfm_expectancy(
        self, session: AsyncSession, symbol: str, direction: str, sizing: SizingResult, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """Validasi ekspektansi probabilistik menggunakan kuantil TimesFM 3.0."""
        tfm_cfg = self.settings.get("timesfm", {})
        if not tfm_cfg.get("enabled", True) or not tfm_cfg.get("expectancy_gate", {}).get("enabled", True):
            return True, "TimesFM expectancy gate disabled"

        try:
            from indicators.timesfm_engine import TimesFMEngine
            engine = TimesFMEngine(self.settings)
            fc = await engine.get_latest_forecast(session, symbol, timeframe="H1", max_age_hours=8.0)
            if not fc or "quantiles" not in fc:
                return True, "No fresh TimesFM forecast available — gate bypassed"

            q = fc["quantiles"]
            entry = sizing.entry_price
            tp = sizing.take_profit
            sl = sizing.stop_loss

            if not tp or not sl or entry <= 0:
                return True, "Missing TP/SL levels for expectancy calculation"

            # Check reachability in 24h horizon
            if direction.lower() == "buy":
                if "q90" in q and q["q90"]:
                    q90 = float(q["q90"][-1])
                    if tp > (q90 * 1.02):
                        return False, f"Proposed TP ({tp}) exceeds TimesFM Q90 ceiling ({q90:.2f}) by >2%. Mathematical expectancy negative."
                if "q30" in q and q["q30"] and "q10" in q and q["q10"]:
                    q30 = float(q["q30"][-1])
                    q10 = float(q["q10"][-1])
                    if sl > q30 and (entry - sl) < (entry - q10) * 0.2:
                        return False, f"Proposed SL ({sl}) is inside high-probability noise cone (> Q30 {q30:.2f})."
            elif direction.lower() == "sell":
                if "q10" in q and q["q10"]:
                    q10 = float(q["q10"][-1])
                    if tp < (q10 * 0.98):
                        return False, f"Proposed TP ({tp}) falls below TimesFM Q10 floor ({q10:.2f}) by >2%. Mathematical expectancy negative."
                if "q70" in q and q["q70"] and "q90" in q and q["q90"]:
                    q70 = float(q["q70"][-1])
                    q90 = float(q["q90"][-1])
                    if sl < q70 and (sl - entry) < (q90 - entry) * 0.2:
                        return False, f"Proposed SL ({sl}) is inside high-probability noise cone (< Q70 {q70:.2f})."

            return True, "TimesFM expectancy passed (target within Q10-Q90 cone)"
        except Exception as e:
            logger.debug(f"TimesFM expectancy check non-fatal error: {e}")
            return True, f"TimesFM check exception bypassed: {e}"

    async def _check_flash_crash_cooldown(self, symbol: str) -> tuple[bool, str]:
        """Pastikan simbol tidak sedang dalam status karantina Flash Crash circuit breaker."""
        if self.flash_crash_detector and self.flash_crash_detector.is_symbol_blocked(symbol):
            return False, f"Symbol {symbol} is in cooldown after Flash Crash circuit breaker trigger."
        return True, "flash_crash_not_active"

    async def _check_analysis_quality_scores(self, analysis: 'AssetAnalysis') -> tuple[bool, str]:
        """Validate that analysis has required quality scores before execution."""
        if analysis is None:
            return (False, 'No analysis object provided')
        
        if getattr(analysis, 'decision_source', None) == 'edge_registry':
            if analysis.confidence is None or analysis.confidence < 0.3:
                return False, f"edge_registry signal confidence too low ({analysis.confidence})"
            return True, "edge_registry_scoring_bypass"

        if analysis.confluence_score is None:
            return (False, 
                f'confluence_score is None for {analysis.symbol}. '
                f'Model did not fill required scorecard. Blocking execution.')
        
        if analysis.priced_in_score is None:
            return (False,
                f'priced_in_score is None for {analysis.symbol}. '
                f'Priced-in assessment not completed. Blocking execution.')
        
        if analysis.priced_in_score >= 9:
            return (False,
                f'priced_in_score={analysis.priced_in_score} >= 9 for {analysis.symbol}. '
                f'Event fully priced in — high sell-the-news reversal risk.')
        
        min_confluence = self.settings.get('trading', {}).get('auto_execute_min_confluence', 7)
        if analysis.confluence_score < min_confluence:
            return (False,
                f'confluence_score={analysis.confluence_score} < {min_confluence} '
                f'(auto_execute_min_confluence threshold).')
        
        return (True, f'quality_scores_ok(confluence={analysis.confluence_score}, priced_in={analysis.priced_in_score})')

    async def _check_consecutive_losses(self, session: AsyncSession, symbol: str, is_backtest: bool = False) -> tuple[bool, str]:
        """Check apakah symbol ini sedang dalam losing streak yang berbahaya."""
        if is_backtest:
            return (True, "consecutive_losses_backtest_ok")
            
        auto_execute = self.settings.get('trading', {}).get('auto_execute', False)
        paper_cfg = self.settings.get('trading', {}).get('paper_trading', {})
        streak_policy = paper_cfg.get('streak_loss_policy', 'warn_and_scale')
        risk_cfg = self.settings.get('trading', {}).get('risk', {})
        max_consecutive = risk_cfg.get('max_consecutive_losses_per_symbol', 3)
        
        # Check recent losses
        from database.models import PaperTradeRecord
        from sqlalchemy import select
        recent = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == symbol)
            .where(PaperTradeRecord.status == 'closed')
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(max_consecutive + 1)
        )).scalars().all()
        
        consecutive_losses = 0
        for trade in recent:
            if (trade.pnl_pct is not None and trade.pnl_pct < 0) or trade.exit_reason == 'sl_hit':
                consecutive_losses += 1
            else:
                break

        # Jika mode paper trading (auto_execute=False atau dry-run)
        if not auto_execute:
            if streak_policy == 'disabled':
                return (True, f"consecutive_losses_paper_disabled(streak={consecutive_losses})")
            elif streak_policy == 'warn_and_scale':
                scale_factor = paper_cfg.get('streak_risk_scale_factor', 0.5)
                if consecutive_losses >= max_consecutive:
                    return (True, f"consecutive_losses_paper_warn_and_scale(streak={consecutive_losses}, scale={scale_factor})")
                return (True, f"consecutive_losses_paper_ok({consecutive_losses}/{max_consecutive})")

        # Mode strict / Live Trading:
        from utils.analytics.paper_tracker import PaperTracker
        suspended = await PaperTracker(self.settings).get_suspended_symbols(session)
        if symbol in suspended:
            return (False, f'{symbol} is suspended due to consecutive losses')
        
        if consecutive_losses >= max_consecutive:
            return (False, 
                f'{symbol}: {consecutive_losses} consecutive SL hits detected. '
                f'Auto-suspend should have triggered. Blocking as safety measure.'
            )
        
        return (True, f'consecutive_losses={consecutive_losses}/{max_consecutive}')

    async def _check_not_paused(self, session: AsyncSession, is_backtest: bool = False) -> tuple[bool, str]:
        """Periksa bahwa trading belum di-pause manual."""
        if is_backtest:
            return (True, "ok")
        from database.models import SystemConfig
        # Check persistent SystemConfig manual pause & emergency kill switch (persists across midnight rollover)
        pause_configs = (await session.execute(
            select(SystemConfig).where(SystemConfig.key.in_(['manual_trading_paused', 'system_paused', 'kill_switch', 'system_kill_switch']))
        )).scalars().all()
        for cfg in pause_configs:
            if cfg and cfg.value and cfg.value.split(':', 1)[0].strip().lower() == 'true':
                reason = cfg.value.split(':', 1)[1] if ':' in cfg.value else f'kill switch active ({cfg.key})'
                return False, f"Trading is blocked by {cfg.key}: {reason}"

        today_start = get_trading_day_start(self.settings)
        state = (await session.execute(
            select(RiskState)
            .where(RiskState.date >= today_start)
            .order_by(RiskState.date.desc())
            .limit(1)
        )).scalar_one_or_none()

        if state and state.trading_paused:
            return False, f"Trading is manually paused: {state.reason or 'no reason given'}"
        return True, "ok"

    async def _check_daily_trade_count(
        self,
        session: AsyncSession,
        is_backtest: bool = False,
        is_paper: Optional[bool] = None,
    ) -> tuple[bool, str]:
        """Hard limit: max N trades per day regardless of other conditions"""
        if is_backtest:
            return (True, "daily_trades_backtest_ok")
        today_start = get_trading_day_start(self.settings)
        from datetime import timedelta
        today_end = today_start + timedelta(days=1)
        # Count from positions opened today (separating live vs paper positions)
        # to ensure paper simulation trades do not exhaust live quota limits.
        from database.models import Position, PaperTradeRecord
        
        # Hitung posisi live yang dibuka hari ini
        live_today = (await session.execute(
            select(func.count(Position.id))
            .where(Position.opened_at >= today_start)
            .where(Position.opened_at < today_end)
            .where(Position.is_paper == False)  # noqa: E712
        )).scalar_one_or_none() or 0
        
        # Hitung paper trades yang dibuka hari ini (sebagai proxy jika belum ada live trades)
        paper_today = (await session.execute(
            select(func.count(PaperTradeRecord.id))
            .where(PaperTradeRecord.opened_at >= today_start)
            .where(PaperTradeRecord.opened_at < today_end)
            .where(PaperTradeRecord.is_pending_fill == False)  # noqa: E712
        )).scalar_one_or_none() or 0
        
        # Pisahkan live vs paper (DB-14)
        if is_paper is None:
            is_paper = bool(self.settings.get("paper_trading", {}).get("enabled", False))
            
        today_trades = paper_today if is_paper else live_today
        trade_label = "paper" if is_paper else "live"
        
        max_daily_trades = self.settings.get('trading', {}).get('risk', {}).get('max_daily_trades', 3)
        logger.debug(
            f'Daily trade count ({trade_label}): live_positions_today={live_today}, '
            f'paper_trades_today={paper_today}, effective_count={today_trades}/{max_daily_trades}'
        )
        
        if today_trades >= max_daily_trades:
            return (False, f'Daily {trade_label} trade limit reached: {today_trades}/{max_daily_trades} trades opened today.')
        return (True, f'daily_{trade_label}_trades={today_trades}/{max_daily_trades}')

    async def _check_sizing_valid(self, sizing: SizingResult) -> tuple[bool, str]:
        """Validasi bahwa position sizing sebelumnya (engine) telah sukses."""
        if not sizing.is_valid:
            return False, f"Invalid sizing: {'; '.join(sizing.rejection_reasons)}"
        if sizing.recommended_lots <= 0:
            return False, "Recommended lots is zero or negative"
        return True, "ok"

    async def _check_lot_size(self, sizing: SizingResult) -> tuple[bool, str]:
        """Validasi bahwa ukuran lot berada dalam batas aman."""
        if sizing.recommended_lots <= 0:
            return False, "Lot size is zero or negative"
        
        # Check against max_lot from instrument spec
        # (Position sizing already handles this, but double-check here)
        # We use a hard limit of 100 lots as absolute maximum for any instrument
        ABSOLUTE_MAX_LOTS = 100.0
        if sizing.recommended_lots > ABSOLUTE_MAX_LOTS:
            return False, f"Lot size {sizing.recommended_lots} exceeds absolute maximum {ABSOLUTE_MAX_LOTS}"
        
        # Check minimum lot
        ABSOLUTE_MIN_LOTS = 0.001
        if sizing.recommended_lots < ABSOLUTE_MIN_LOTS:
            return False, f"Lot size {sizing.recommended_lots} is below minimum tradeable {ABSOLUTE_MIN_LOTS}"
        
        return True, f"lot_size={sizing.recommended_lots} (valid)"

    async def _check_weekly_drawdown(self, session: AsyncSession, equity: Optional[float] = None, is_backtest: bool = False) -> tuple[bool, str]:
        if is_backtest:
            return True, "weekly_drawdown_backtest_ok"
        from database.models import PaperTradeRecord, TradeOutcome
        from datetime import timedelta
        now = clock.now()
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Paper trades closed this week
        paper_trades = (await session.execute(select(PaperTradeRecord).where(
            PaperTradeRecord.closed_at >= week_start,
            PaperTradeRecord.closed_at <= now,
            PaperTradeRecord.status == 'closed'
        ))).scalars().all()
        paper_weekly_pnl = sum(t.pnl_pct or 0 for t in paper_trades)
        
        # Live trades closed this week
        live_outcomes = (await session.execute(select(TradeOutcome).where(
            TradeOutcome.closed_at >= week_start,
            TradeOutcome.closed_at <= now
        ))).scalars().all()
        live_weekly_pnl = 0.0
        eff_equity = equity if (equity is not None and equity > 0) else float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        if live_outcomes and eff_equity > 0:
            total_live_profit = sum(o.pnl_usd or 0.0 for o in live_outcomes)
            live_weekly_pnl = (total_live_profit / eff_equity) * 100.0

        # Conservative: take the worst PnL between live and paper
        weekly_pnl = min(paper_weekly_pnl, live_weekly_pnl) if live_outcomes else paper_weekly_pnl
        max_weekly = self.settings.get('trading', {}).get('risk', {}).get('max_weekly_drawdown_percent', 6.0)
        if weekly_pnl <= -max_weekly:
            return False, f"Weekly loss {weekly_pnl:.2f}% >= limit {max_weekly}%"
        return True, f"weekly_pnl={weekly_pnl:.2f}%/{-max_weekly}%"

    async def _check_daily_drawdown(
        self, session: AsyncSession, equity: Optional[float] = None, simulated_daily_pnl: Optional[float] = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """Periksa apakah drawdown hari ini (realized + unrealized loss) belum melampaui batas."""
        if is_backtest:
            if simulated_daily_pnl is not None and equity and equity > 0:
                drawdown_pct = (abs(simulated_daily_pnl) / equity * 100) if simulated_daily_pnl < 0 else 0.0
                if simulated_daily_pnl < 0 and drawdown_pct >= self.max_daily_drawdown_pct:
                    return False, f"Simulated daily drawdown {drawdown_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%"
                return True, f"simulated_drawdown={drawdown_pct:.2f}%"
            return True, "backtest_mode_dd_ok"

        today_start = get_trading_day_start(self.settings)
        state = (await session.execute(
            select(RiskState)
            .where(RiskState.date >= today_start)
            .order_by(RiskState.date.desc())
            .limit(1)
        )).scalar_one_or_none()

        realized_pnl = 0.0
        if state is None:
            # First trade of the day: initialize baseline state record from account equity
            try:
                state = RiskState(
                    date=clock.now(),
                    daily_pnl=0.0,
                    current_drawdown=0.0,
                    trading_paused=False,
                )
                session.add(state)
                await session.flush()
            except Exception as init_err:
                logger.debug(f"Failed to initialize baseline RiskState: {init_err}")
        else:
            realized_pnl = state.daily_pnl

        # Calculate unrealized PnL from MT5
        unrealized_pnl = 0.0
        is_dry = getattr(self, 'dry_run', getattr(self, '_dry_run', False))
        if self._mt5 and not is_dry:
            try:
                positions = await self._mt5.get_open_positions()
                unrealized_pnl = sum(p.get('profit', 0.0) for p in positions)
            except Exception as e:
                logger.debug(f"Failed to fetch MT5 positions for unrealized PnL: {e}")
        elif is_dry:
            try:
                from database.models import PaperTradeRecord, PriceOHLCV
                open_papers = (await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.status == 'open')
                )).scalars().all()
                unrealized_pnl = 0.0
                for paper in open_papers:
                    last_bar = (await session.execute(
                        select(PriceOHLCV.close)
                        .where(PriceOHLCV.symbol == paper.symbol)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if last_bar and paper.entry_price and paper.stop_loss:
                        sl_dist = abs(paper.entry_price - paper.stop_loss)
                        if sl_dist > 0:
                            diff = (last_bar - paper.entry_price) if paper.direction == 'buy' else (paper.entry_price - last_bar)
                            risk_pct = paper.risk_pct or 0.75
                            trade_pnl_pct = risk_pct * (diff / sl_dist)
                            unrealized_pnl += (equity or 10000.0) * (trade_pnl_pct / 100.0)
            except Exception as e:
                logger.debug(f"Failed to calc paper unrealized PnL: {e}")

        # We track Daily Drawdown as the net daily PnL (realized + unrealized).
        # A true daily loss limit is based on the starting equity of the day.
        eff_equity = equity if (equity is not None and equity > 0) else float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        total_daily_pnl = (state.daily_pnl if state else realized_pnl) + unrealized_pnl
        drawdown_pct = (abs(total_daily_pnl) / eff_equity * 100) if (eff_equity > 0 and total_daily_pnl < 0) else 0.0
        
        # We also enforce that unrealized loss on its own cannot exceed the limit.
        if unrealized_pnl < 0:
            unrealized_dd_pct = (abs(unrealized_pnl) / eff_equity * 100) if eff_equity > 0 else 0.0
            if unrealized_dd_pct >= self.max_daily_drawdown_pct:
                return False, (
                    f"Unrealized drawdown {unrealized_dd_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%. "
                    f"Unrealized: ${unrealized_pnl:.2f}"
                )

        # Also check if daily PnL is already at max loss
        if total_daily_pnl < 0:
            if drawdown_pct >= self.max_daily_drawdown_pct:
                return False, (
                    f"Daily PnL loss {drawdown_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%. "
                    f"Total Daily PnL: ${total_daily_pnl:.2f}"
                )

        return True, f"drawdown={drawdown_pct:.2f}% (limit={self.max_daily_drawdown_pct}%)"

    async def _check_max_positions(self, session: AsyncSession, simulated_positions: Optional[list] = None) -> tuple[bool, str]:
        """Pastikan batas maksimal posisi terbuka (concurrent) belum terlewati."""
        if simulated_positions is not None:
            count = len(simulated_positions)
            if count >= self.max_concurrent:
                return False, f"Max concurrent positions reached (simulated): {count}/{self.max_concurrent}"
            return True, f"open_positions={count}/{self.max_concurrent}"

        count = (await session.execute(
            select(func.count(Position.id)).where(Position.status == "open")
        )).scalar_one_or_none() or 0

        if count >= self.max_concurrent:
            return False, (
                f"Max concurrent positions reached: {count}/{self.max_concurrent}"
            )
        return True, f"open_positions={count}/{self.max_concurrent}"

    async def _check_no_duplicate(
        self,
        session: AsyncSession,
        symbol: str,
        simulated_positions: Optional[list] = None,
        pair_group_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Pastikan hanya ada SATU posisi terbuka untuk simbol ini (kecuali multi-leg/tranche dengan pair_group_id)."""
        if simulated_positions is not None:
            for pos in simulated_positions:
                pos_sym = getattr(pos, 'symbol', None) or (pos.get('symbol') if isinstance(pos, dict) else None)
                pos_group = getattr(pos, 'pair_group_id', None) or (pos.get('pair_group_id') if isinstance(pos, dict) else None)
                if pos_sym == symbol:
                    if pair_group_id and pos_group == pair_group_id:
                        continue
                    return False, f"Already have an open simulated position for {symbol}"
            return True, "no duplicate (simulated)"

        if pair_group_id:
            # DB-15: Posisi dengan pair_group_id diizinkan multi-leg/tranche dalam group yang sama
            conflict = (await session.execute(
                select(Position.id)
                .where(Position.symbol == symbol)
                .where(Position.status == "open")
                .where((Position.pair_group_id != pair_group_id) | (Position.pair_group_id.is_(None)))
                .limit(1)
            )).scalar_one_or_none()
            if conflict is not None:
                return False, f"Already have an open position for {symbol} outside pair group {pair_group_id} (id={conflict})"

            group_count = (await session.execute(
                select(func.count(Position.id))
                .where(Position.symbol == symbol)
                .where(Position.status == "open")
                .where(Position.pair_group_id == pair_group_id)
            )).scalar_one_or_none() or 0
            if group_count >= 2:
                return False, f"Pair group {pair_group_id} already has max legs ({group_count}) for {symbol}"
            return True, "no duplicate (pair group leg allowed)"

        existing = (await session.execute(
            select(Position.id)
            .where(Position.symbol == symbol)
            .where(Position.status == "open")
            .limit(1)
        )).scalar_one_or_none()

        if existing is not None:
            return False, f"Already have an open position for {symbol} (id={existing})"
        return True, "no duplicate"

    async def _check_vix_threshold(self, session: AsyncSession, as_of: Optional[datetime] = None, is_backtest: bool = False) -> tuple[bool, str]:
        """Block new positions when VIX exceeds the configured pause threshold."""
        if is_backtest:
            return True, "vix_threshold_backtest_ok"
        from database.models import VIXData
        from sqlalchemy import select
        
        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        vix_thresholds = risk_cfg.get("vix_thresholds", {})
        pause_threshold = float(vix_thresholds.get("pause", 30))
        defensive_threshold = float(vix_thresholds.get("defensive", 25.0))
        
        now = as_of or clock.now()
        vix_row = (await session.execute(
            select(VIXData)
            .where(VIXData.date <= now)
            .order_by(VIXData.date.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        vix_close = defensive_threshold  # Fail-safe default (defensive volatility)
        if vix_row is None:
            vix_age_days = 0
            vix_str_info = f"defaulting to {defensive_threshold} (Defensive Fail-Safe)"
        else:
            vix_close = vix_row.close
            now_dt = now if (hasattr(now, 'tzinfo') and now.tzinfo) else now.replace(tzinfo=timezone.utc)
            row_dt = vix_row.date if (hasattr(vix_row.date, 'tzinfo') and vix_row.date.tzinfo) else vix_row.date.replace(tzinfo=timezone.utc)
            vix_age_days = (now_dt - row_dt).total_seconds() / 86400
            vix_str_info = f"{vix_age_days:.1f} days old"
        
        if vix_row is not None and vix_age_days > 3.0:
            # Check if it's weekend or Monday before US close (vix_age_days up to 4.5 is normal for Friday close)
            is_weekend_or_monday = now.weekday() in (5, 6, 0)
            if is_weekend_or_monday and vix_age_days <= 4.5:
                vix_str_info += " (weekend/Monday expected delay)"
            else:
                # Fail-safe: if VIX is too stale, assume defensive risk
                vix_close = defensive_threshold
                vix_str_info += f" (stale -> defaulting to {defensive_threshold})"
        
        if vix_close >= pause_threshold:
            return False, (
                f"VIX={vix_close:.1f} >= pause threshold {pause_threshold}. "
                f"Extreme market fear detected. All new positions blocked. "
                f"Trading resumes automatically when VIX drops below {pause_threshold}."
            )
        
        return True, f"VIX={vix_close:.1f} ({vix_str_info} - below threshold {pause_threshold})"

    async def assess_weekend_gap_risk(
        self, session: AsyncSession, symbol: str, as_of: Optional[datetime] = None
    ) -> tuple[bool, str]:
        """Blokir entri saat akhir pekan untuk aset non-24/7 (menghindari risiko gap)."""
        weekend_cfg = self.settings.get("trading", {}).get("weekend_management", {})
        exempted = weekend_cfg.get("exempted_symbols", ["BTCUSD", "ETHUSD"])
        gap_hours = weekend_cfg.get("gap_protection_hours", 2)

        if symbol in exempted:
            return True, f"{symbol} is exempted (24/7)"
        
        now = as_of or clock.now()
        weekday = now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        hour = now.hour
        
        # Block during actual weekend (market closed)
        if weekday == 5:
            return False, f"Forex/commodity markets closed all day Saturday. No new positions until Sunday 21:00 UTC."
        if weekday == 6 and hour < 21:
            return False, f"Forex/commodity markets closed (Sunday before 21:00 UTC). Sydney opens at ~21:00 UTC."
        
        # Block Friday within gap_protection_hours of close (21:00 UTC = high weekend gap risk)
        threshold_hour = 21 - gap_hours
        if weekday == 4 and hour >= threshold_hour:
            return False, (
                f"Blocked: {hour}:00 UTC Friday is within {gap_hours}h of weekend close (21:00 UTC). "
                f"High weekend gap risk. Wait until Sunday 21:00 UTC for new positions."
            )
        
        return True, "ok - not near weekend"

    # Alias for naming consistency with internal _check_* validators
    _check_weekend_gap_risk = assess_weekend_gap_risk

    async def _check_rollover_window(self, symbol: str, as_of: Optional[datetime] = None) -> tuple[bool, str]:
        """Blokir entri saat jeda rollover harian (spread membesar). BTCUSD & ETHUSD kebal."""
        if symbol in ("BTCUSD", "ETHUSD"):
            return True, f"{symbol} exempt from rollover check"
        
        now = as_of or clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        try:
            import zoneinfo
            ny_tz = zoneinfo.ZoneInfo("America/New_York")
            now_ny = now.astimezone(ny_tz)
            today_close = now_ny.replace(hour=17, minute=0, second=0, microsecond=0)
            diff_seconds = (now_ny - today_close).total_seconds()
            
            # Daily rollover window: 5 menit sebelum (-300s) hingga 30 menit sesudah (+1800s) 17:00 NY Close
            is_rollover = -300 <= diff_seconds <= 1800
            
            if is_rollover:
                window_start = today_close - timedelta(minutes=5)
                window_end = today_close + timedelta(minutes=30)
                start_utc = window_start.astimezone(timezone.utc).strftime('%H:%M')
                end_utc = window_end.astimezone(timezone.utc).strftime('%H:%M UTC')
                return False, (
                    f"Daily rollover window ({start_utc}-{end_utc}). Spreads are currently elevated. "
                    f"Current time: {now.strftime('%H:%M UTC')}. "
                    f"Retry after {end_utc}."
                )
        except Exception:
            hour = now.hour
            minute = now.minute
            is_rollover = (hour == 20 and minute >= 55) or (hour == 21 and minute <= 30)
            if is_rollover:
                return False, (
                    f"Daily rollover window (20:55-21:30 UTC). Spreads are currently elevated. "
                    f"Current time: {now.strftime('%H:%M UTC')}. "
                    f"Retry after 21:30 UTC."
                )
        
        return True, "Outside rollover window"

    async def _check_news_window(self, session: AsyncSession, symbol: str, as_of: Optional[datetime] = None, is_backtest: bool = False) -> tuple[bool, str]:
        if is_backtest:
            return True, "news_window_backtest_ok"
        currencies = get_symbol_currencies(symbol)
        now = as_of or clock.now()
        window = timedelta(minutes=self.news_window_minutes)

        # 1. Check calendar data freshness via SystemConfig metadata first
        latest_calendar_fetch: Optional[datetime] = None
        try:
            latest_fetch_cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == "last_calendar_fetch_at")
            )).scalar_one_or_none()
            if latest_fetch_cfg and latest_fetch_cfg.value:
                dt = datetime.fromisoformat(latest_fetch_cfg.value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                latest_calendar_fetch = dt
        except Exception as e:
            logger.debug(f"Could not read last_calendar_fetch_at from SystemConfig: {e}")

        # Fallback to MAX(EconomicCalendar.fetched_at)
        if latest_calendar_fetch is None:
            max_fetched = (await session.execute(
                select(func.max(EconomicCalendar.fetched_at))
            )).scalar_one_or_none()
            if max_fetched is not None:
                if max_fetched.tzinfo is None:
                    max_fetched = max_fetched.replace(tzinfo=timezone.utc)
                latest_calendar_fetch = max_fetched

        # Check if any calendar rows exist in DB at all
        total_events = (await session.execute(
            select(func.count(EconomicCalendar.id))
        )).scalar_one_or_none() or 0

        if total_events == 0 and latest_calendar_fetch is None:
            logger.warning(
                "No economic calendar data exists in database. "
                "Degraded mode: proceeding with warning instead of hard-block."
            )
            return True, "economic_calendar_empty_warning_pass"

        calendar_age_hours = (now - latest_calendar_fetch).total_seconds() / 3600 if latest_calendar_fetch else 999.0

        # Check future coverage in DB (events within [-1h, +12h])
        future_coverage = (await session.execute(
            select(EconomicCalendar.id)
            .where(EconomicCalendar.event_time >= now - timedelta(hours=1))
            .where(EconomicCalendar.event_time <= now + timedelta(hours=12))
            .limit(1)
        )).scalar_one_or_none()

        stale_warning = ""
        if calendar_age_hours > 8.0:
            logger.warning(
                f"Economic calendar data is {calendar_age_hours:.1f}h old (threshold=8.0h). "
                f"Degraded mode: proceeding with warning instead of hard-block."
            )
            stale_warning = f" [WARNING: Calendar data is {calendar_age_hours:.1f}h old — degraded mode]"
        elif calendar_age_hours > 4.0:
            stale_warning = f" [WARNING: Calendar data is {calendar_age_hours:.1f}h old — check upcoming events manually]"

        # Check for actual upcoming high-impact events
        upcoming = (await session.execute(
            select(EconomicCalendar)
            .where(EconomicCalendar.impact.in_(["high", "High", "HIGH"]))
            .where(EconomicCalendar.currency.in_(list(currencies)))
            .where(EconomicCalendar.event_time >= now - window)
            .where(EconomicCalendar.event_time <= now + window)
            .limit(1)
        )).scalar_one_or_none()

        if upcoming is not None and upcoming.event_time is not None:
            delta = abs((upcoming.event_time - now).total_seconds() / 60)
            return False, (
                f"High-impact event within news window: '{upcoming.event_name}' "
                f"({upcoming.currency}) at {upcoming.event_time.strftime('%H:%M UTC')} "
                f"(~{delta:.0f}min away, window={self.news_window_minutes}min)"
                f"{stale_warning}"
            )

        return True, f"no high-impact events in window{stale_warning}"

    async def check_correlation_exposure(
        self,
        session: AsyncSession,
        symbol: str,
        direction: str,
        simulated_positions: Optional[list] = None,
        as_of: Optional[datetime] = None,
        open_positions: Optional[list] = None,
    ) -> tuple[bool, str]:
        """Pastikan trade ini tidak melewati batas korelasi paparan mata uang / heat limit menggunakan DynamicCorrelationMatrix."""
        if open_positions is None:
            if simulated_positions is not None:
                open_positions = simulated_positions
            else:
                open_positions = list((await session.execute(
                    select(Position).where(Position.status == "open")
                )).scalars().all())

        if not open_positions:
            return True, "no existing positions"

        # Evaluate portfolio heat using DynamicCorrelationMatrix if open positions present
        pos_list = []
        for pos in open_positions:
            p_sym = getattr(pos, 'symbol', None) or (pos.get('symbol') if isinstance(pos, dict) else None)
            p_vol = getattr(pos, 'volume', None) or getattr(pos, 'executed_lots', None) or (pos.get('volume', 0.1) if isinstance(pos, dict) else 0.1) or 0.1
            p_dir = getattr(pos, 'direction', None) or (pos.get('direction') if isinstance(pos, dict) else 'buy')
            if p_sym:
                pos_list.append({"symbol": str(p_sym), "volume": float(p_vol), "direction": str(p_dir)})

        if pos_list and hasattr(self, "dynamic_correlation_matrix"):
            try:
                candidate_pos = {"symbol": symbol, "direction": direction, "volume": 0.1}
                all_positions = pos_list + [candidate_pos]
                symbols = list(set([p["symbol"] for p in all_positions]))
                corr_matrix = await self.dynamic_correlation_matrix.get_matrix(session, symbols, as_of=as_of)
                if corr_matrix:
                    heat = self.dynamic_correlation_matrix.calculate_portfolio_heat(all_positions, corr_matrix)
                    if heat.get("portfolio_heat", 0.0) > float(self.correlation_limit):
                        return False, (
                            f"Correlated exposure limit exceeded: calculated portfolio heat {heat['portfolio_heat']:.2f} "
                            f"> limit {self.correlation_limit}"
                        )
            except Exception as exc:
                logger.debug(f"DynamicCorrelationMatrix evaluation fallback: {exc}")

        correlated_exposure = 1.0  # Base exposure for the new trade
        
        for pos in open_positions:
            pos_sym = getattr(pos, 'symbol', None) or (pos.get('symbol') if isinstance(pos, dict) else None)
            pos_vol = getattr(pos, 'volume', None) or getattr(pos, 'executed_lots', None) or (pos.get('volume', 0.1) if isinstance(pos, dict) else 0.1) or 0.1
            pos_dir = getattr(pos, 'direction', None) or (pos.get('direction') if isinstance(pos, dict) else 'buy')

            if not pos_sym:
                continue

            # Dynamic correlation calculation and std_dev
            corr, std_dev = await self._get_dynamic_correlation(session, symbol, pos_sym, as_of=as_of)
            
            if corr != 0.0 and abs(corr) > 0.7:
                # Volatility-adjusted exposure: Aset dengan volatilitas rendah memiliki penalty lebih kecil
                volatility_multiplier = max(std_dev * 100, 0.1) 
                
                max_lot = self.settings.get('trading', {}).get('risk', {}).get('max_lot_per_symbol', 1.0)
                normalized_exposure = (pos_vol / max(max_lot, 0.01)) * volatility_multiplier
                
                same_dir = direction == pos_dir
                actual_direction_factor = 1 if (corr > 0 and same_dir) or (corr < 0 and not same_dir) else -0.5
                correlated_exposure += abs(corr) * normalized_exposure * max(0, actual_direction_factor)

        if correlated_exposure > self.correlation_limit:
            return False, (
                f"Correlated exposure limit exceeded: calculated exposure {correlated_exposure:.2f} "
                f"> limit {self.correlation_limit}"
            )

        return True, f"correlation_ok (exposure={correlated_exposure:.2f}/{self.correlation_limit})"

    async def _check_correlation(
        self, session: AsyncSession, symbol: str, direction: str, simulated_positions: Optional[list] = None, as_of: Optional[datetime] = None
    ) -> tuple[bool, str]:
        """Pastikan trade ini tidak melewati batas korelasi paparan mata uang."""
        return await self.check_correlation_exposure(
            session=session,
            symbol=symbol,
            direction=direction,
            simulated_positions=simulated_positions,
            as_of=as_of,
        )

    async def _get_dynamic_correlation(
        self, session: AsyncSession, symbol1: str, symbol2: str, as_of: Optional[datetime] = None
    ) -> tuple[float, float]:
        """Hitung korelasi harian secara dinamis berdasar PriceOHLCV, return (corr, std_dev2)."""
        from utils.market.dynamic_correlation import get_rolling_correlation
        import pandas as pd
        from database.models import PriceOHLCV
        from sqlalchemy import select
        
        sim_time = as_of or clock.now()
        corr, source = await get_rolling_correlation(session, symbol1, symbol2, as_of=sim_time)
        fallback_std = 0.01
        
        try:
            s2_stmt = (
                select(PriceOHLCV.timestamp, PriceOHLCV.close)
                .where(PriceOHLCV.symbol == symbol2, PriceOHLCV.timeframe == "D1")
            )
            if sim_time is not None:
                s2_stmt = s2_stmt.where(PriceOHLCV.timestamp <= sim_time)
                
            s2_rows = (await session.execute(
                s2_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(60)
            )).all()
            
            if len(s2_rows) >= 30:
                df2 = pd.DataFrame(s2_rows, columns=["timestamp", "close2"]).set_index("timestamp").sort_index()
                std2 = df2["close2"].pct_change().std()
                std2 = fallback_std if pd.isna(std2) else float(std2)
            else:
                std2 = fallback_std
        except Exception:
            std2 = fallback_std
            
        return float(corr), float(std2)

    async def _check_total_portfolio_heat(
        self, session: AsyncSession, proposed_sizing: SizingResult, equity: Optional[float] = None, simulated_positions: Optional[list] = None
    ) -> tuple[bool, str]:
        heat_cfg = self.settings.get("trading", {}).get("risk", {})
        max_heat_pct = float(heat_cfg.get("max_portfolio_heat_pct", 4.0))
        eff_equity = equity if (equity is not None and equity > 0) else float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))

        if simulated_positions is not None:
            open_positions = simulated_positions
        else:
            open_positions = (await session.execute(
                select(Position).where(Position.status == "open")
            )).scalars().all()

        current_heat_usd = 0.0
        position_details = []

        for pos in open_positions:
            pos_sym = getattr(pos, 'symbol', None) or (pos.get('symbol') if isinstance(pos, dict) else None)
            pos_entry = getattr(pos, 'entry_price', None) or (pos.get('entry_price') if isinstance(pos, dict) else None)
            pos_sl = getattr(pos, 'sl', None) or getattr(pos, 'stop_loss', None) or (pos.get('sl') or pos.get('stop_loss') if isinstance(pos, dict) else None)
            pos_vol = getattr(pos, 'volume', None) or getattr(pos, 'executed_lots', None) or (pos.get('volume') or pos.get('executed_lots') if isinstance(pos, dict) else None)
            pos_dir = getattr(pos, 'direction', None) or (pos.get('direction') if isinstance(pos, dict) else 'buy')

            if not pos_entry or not pos_vol or not pos_sym:
                continue
            
            pos_sym_str = str(pos_sym)
            
            # Hitung risiko aktual posisi terbuka
            if pos_sl and pos_sl > 0:
                d_entry = Decimal(str(pos_entry))
                d_sl = Decimal(str(pos_sl))
                d_sl_distance = abs(d_entry - d_sl)
                sl_distance = float(d_sl_distance)
                
                # Check breakeven (SL past/at entry)
                if pos_dir == 'buy' and pos_sl >= pos_entry:
                    heat_this_position = 0.0
                    position_details.append(f"{pos_sym_str}: $0 (breakeven)")
                elif pos_dir == 'sell' and pos_sl <= pos_entry:
                    heat_this_position = 0.0
                    position_details.append(f"{pos_sym_str}: $0 (breakeven)")
                else:
                    from risk.position_sizing import PositionSizer
                    sizer = PositionSizer(self.settings, mt5_client=self._mt5)
                    try:
                        spec = await sizer._get_instrument_spec_dynamic(session, pos_sym_str)
                    except Exception:
                        spec = sizer._get_instrument_spec(pos_sym_str)
                    
                    if spec and spec.pip_size > 0 and spec.pip_value_per_lot > 0:
                        d_pip_size = Decimal(str(spec.pip_size))
                        d_pip_val = Decimal(str(spec.pip_value_per_lot))
                        d_pos_vol = Decimal(str(pos_vol))
                        d_sl_distance_pips = d_sl_distance / d_pip_size
                        # Actual risk = SL_pips * pip_value * lots using Decimal
                        d_heat = d_sl_distance_pips * d_pip_val * d_pos_vol
                        heat_this_position = float(d_heat)
                        # Cap at 3x default risk (sanity check)
                        max_reasonable = eff_equity * (float(heat_cfg.get("risk_percent_per_trade", 1.5)) / 100.0) * 3
                        heat_this_position = min(heat_this_position, max_reasonable)
                        position_details.append(f"{pos_sym}: ~${heat_this_position:.2f} (actual SL risk)")
                    else:
                        # Fallback to default estimate
                        heat_this_position = eff_equity * (float(heat_cfg.get("risk_percent_per_trade", 1.5)) / 100.0)
                        position_details.append(f"{pos_sym}: ~${heat_this_position:.2f} (estimated)")
            else:
                if simulated_positions is None:
                    return False, (
                        f"BLOCKED: Position {pos_sym} "
                        f"has NO stop loss. All new positions are blocked until SL is set."
                    )
                else:
                    heat_this_position = eff_equity * (float(heat_cfg.get("risk_percent_per_trade", 1.5)) / 100.0)
            
            current_heat_usd += heat_this_position

        proposed_heat_usd = proposed_sizing.risk_amount_usd
        total_heat_usd = current_heat_usd + proposed_heat_usd
        total_heat_pct = (total_heat_usd / eff_equity * 100) if eff_equity > 0 else 0.0

        if total_heat_pct > max_heat_pct:
            return False, (
                f"Portfolio heat would reach {total_heat_pct:.1f}% "
                f"(limit={max_heat_pct}%). "
                f"Current positions actual risk: {', '.join(position_details)}. "
                f"Proposed: ${proposed_heat_usd:.2f} ({proposed_sizing.risk_percent:.1f}%)."
            )

        return True, f"portfolio_heat={total_heat_pct:.1f}%/{max_heat_pct}%"


    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def _log_verdict(
        self, session: AsyncSession, symbol: str, direction: str,
        sizing: SizingResult, verdict: RiskVerdict
    ) -> None:
        """Catat keputusan risk gate ke tabel orders_log."""
        from database.models import OrderLog
        import json

        record = OrderLog(
            action="risk_check",
            symbol=symbol,
            params_json=json.dumps({
                "direction":      direction,
                "proposed_lots":  sizing.recommended_lots,
                "risk_amount_usd": sizing.risk_amount_usd,
                "risk_percent":   sizing.risk_percent,
                "sl_pips":        getattr(sizing, 'sl_distance_pips', getattr(sizing, 'sl_pips', 0.0)),
                "rr_ratio":       sizing.rr_ratio,
            }),
            requested_by="strategy_pipeline",
            approved_by="risk_gate" if verdict.approved else None,
            result=json.dumps({
                "approved":          verdict.approved,
                "checks_passed":     verdict.checks_passed,
                "checks_failed":     verdict.checks_failed,
                "rejection_reasons": verdict.rejection_reasons,
            }),
        )
        session.add(record)
        await session.flush()

    # ------------------------------------------------------------------
    # Risk state management
    # ------------------------------------------------------------------

    async def update_risk_state(
        self,
        session: AsyncSession,
        pnl_delta: float,
        equity: Optional[float] = None,
    ) -> None:
        """Update RiskState harian setelah posisi tertutup. Trigger auto-pause jika lewat batas."""
        today_start = get_trading_day_start(self.settings)
        state = (await session.execute(
            select(RiskState)
            .where(RiskState.date >= today_start)
            .order_by(RiskState.date.desc())
            .limit(1)
        )).scalar_one_or_none()

        if state is None:
            state = RiskState(
                date=clock.now(),
                daily_pnl=0.0,
                current_drawdown=0.0,
                trading_paused=False,
            )
            session.add(state)

        state.daily_pnl += pnl_delta

        # Update drawdown to track the worst net PnL of the day
        if state.daily_pnl < state.current_drawdown:
            state.current_drawdown = state.daily_pnl

        # Auto-pause if drawdown breached
        # current_drawdown tracks the lowest point of daily_pnl
        drawdown_pct = (abs(state.current_drawdown) / equity * 100) if (equity is not None and equity > 0 and state.current_drawdown < 0) else 0.0
        if drawdown_pct >= self.max_daily_drawdown_pct and not state.trading_paused:
            state.trading_paused = True
            state.reason = (
                f"Auto-paused: daily drawdown {drawdown_pct:.2f}% "
                f">= limit {self.max_daily_drawdown_pct}%"
            )
            logger.warning(f"TRADING AUTO-PAUSED: {state.reason}")
            
            try:
                from utils.infra.notifier import AgentNotifier
                notifier = AgentNotifier()
                await notifier.send_critical(f"🛑 <b>TRADING AUTO-PAUSED</b>\n{state.reason}")
            except Exception as e:
                logger.error(f"Failed to notify auto-pause: {e}")

        await session.commit()
        logger.info(
            f"RiskState updated: daily_pnl=${state.daily_pnl:.2f}, "
            f"drawdown=${state.current_drawdown:.2f} ({drawdown_pct:.2f}%), "
            f"paused={state.trading_paused}"
        )

    async def pause_trading(
        self, session: AsyncSession, reason: str
    ) -> None:
        """Pause sistem trading secara manual."""
        from database.models import SystemConfig
        today_start = get_trading_day_start(self.settings)
        state = (await session.execute(
            select(RiskState).where(RiskState.date >= today_start).limit(1)
        )).scalar_one_or_none()

        if state is None:
            state = RiskState(date=clock.now(), daily_pnl=0, current_drawdown=0)
            session.add(state)

        state.trading_paused = True
        state.reason = reason

        # Persist across midnight rollover via SystemConfig
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'manual_trading_paused')
        )).scalar_one_or_none()
        if cfg:
            cfg.value = f"true:{reason}"
        else:
            session.add(SystemConfig(key='manual_trading_paused', value=f"true:{reason}"))

        await session.commit()
        logger.warning(f"Trading manually PAUSED: {reason}")

    async def _check_edge_status_not_paused(self, session: AsyncSession, is_backtest: bool = False) -> tuple[bool, str]:
        if is_backtest:
            return (True, 'ok')
        from database.models import SystemConfig
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'trading_paused')
        )).scalar_one_or_none()
        if cfg and cfg.value and cfg.value.split(':', 1)[0].strip().lower() == 'true':
            reason = cfg.value.split(':', 1)[1] if ':' in cfg.value else 'No statistical edge detected (EdgeTracker auto-pause)'
            return (False, f'EdgeTracker auto-pause active: {reason}')
        return (True, 'ok')

    async def clear_edge_status_pause(self, session: AsyncSession) -> None:
        from database.models import SystemConfig
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'trading_paused')
        )).scalar_one_or_none()
        if cfg and cfg.value:
            cfg.value = 'false'
            logger.info('Edge-status auto-pause cleared.')

    async def resume_trading(self, session: AsyncSession) -> None:
        """Lanjutkan (resume) trading secara manual."""
        from database.models import SystemConfig
        today_start = get_trading_day_start(self.settings)
        state = (await session.execute(
            select(RiskState).where(RiskState.date >= today_start).limit(1)
        )).scalar_one_or_none()

        if state:
            state.trading_paused = False
            state.reason = None

        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'manual_trading_paused')
        )).scalar_one_or_none()
        if cfg:
            cfg.value = 'false'

        await self.clear_edge_status_pause(session)
        
        # Bersihkan juga suspended symbols saat resume trading dipanggil
        try:
            from utils.analytics.paper_tracker import PaperTracker
            await PaperTracker(self.settings).unsuspend_all(session)
        except Exception as e:
            logger.debug(f"Failed to clear suspended symbols on resume: {e}")

        await session.commit()
        logger.info('Trading manually RESUMED (RiskState + Manual + EdgeTracker + SuspendedSymbols flags cleared)')

    async def _check_post_loss_cooldown(
        self, session: AsyncSession, symbol: str, as_of: Optional[datetime] = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """Blokir re-entry pada simbol yang sama selama N jam jika baru saja terkena Stop Loss."""
        if is_backtest:
            return True, "cooldown_backtest_ok"
        cooldown_hours = self.settings.get("trading", {}).get("risk", {}).get(
            "post_sl_cooldown_hours", 6
        )
        if cooldown_hours <= 0:
            return True, "cooldown disabled"
        
        now = as_of or clock.now()
        since = now - timedelta(hours=cooldown_hours)
        
        # Check for recent SL hits on this symbol
        from database.models import TradeOutcome
        recent_sl = (await session.execute(
            select(TradeOutcome)
            .where(TradeOutcome.symbol == symbol)
            .where(TradeOutcome.exit_reason == "sl_hit")
            .where(TradeOutcome.closed_at >= since)
            .limit(1)
        )).scalar_one_or_none()
        
        # Also check PaperTradeRecord for sl_hit
        if recent_sl is None:
            recent_sl_paper = (await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.exit_reason == "sl_hit")
                .where(PaperTradeRecord.closed_at >= since)
                .limit(1)
            )).scalar_one_or_none()
            if recent_sl_paper and recent_sl_paper.closed_at is not None:
                hours_ago = (now - recent_sl_paper.closed_at).total_seconds() / 3600
                return False, (
                    f"Post-SL cooldown active for {symbol}: "
                    f"SL was hit {hours_ago:.1f}h ago. Cooldown: {cooldown_hours}h. "
                    f"Prevents immediate re-entry after loss."
                )
        elif recent_sl is not None and recent_sl.closed_at is not None:
            hours_ago = (now - recent_sl.closed_at).total_seconds() / 3600
            return False, (
                f"Post-SL cooldown active for {symbol}: "
                f"SL was hit {hours_ago:.1f}h ago. Cooldown: {cooldown_hours}h."
            )
        
        return True, "no recent SL hits"

    async def _check_schmitt_regime(
        self, session: AsyncSession, symbol: str, simulated_positions: Optional[list] = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """
        Check systemic correlation regime via Schmitt trigger.
        In FUSED regime: market contagion is high, cap concurrent positions to 2.
        """
        if is_backtest:
            return True, "schmitt_regime_backtest_exempt"
        try:
            from indicators.regime_detector import get_schmitt_regime_detector, RegimeState
            detector = get_schmitt_regime_detector()
            if detector.state == RegimeState.FUSED:
                from database.models import Position
                open_count = (await session.execute(
                    select(func.count(Position.id)).where(Position.status == "open")
                )).scalar_one_or_none() or 0
                if simulated_positions:
                    open_count += len(simulated_positions)
                if open_count >= 2:
                    return False, f"Schmitt regime is FUSED (contagion density={detector.last_density:.2f}). Max 2 positions allowed (current={open_count})"
            return True, f"regime={detector.state.value} (density={detector.last_density:.2f})"
        except Exception as e:
            logger.debug(f"Schmitt regime check error: {e}")
            return True, "schmitt_regime_fallback_ok"

    async def _check_vpin_toxicity(
        self, session: AsyncSession, symbol: str, as_of: Optional[datetime] = None, is_backtest: bool = False
    ) -> tuple[bool, str]:
        """
        Check VPIN order flow toxicity for high-volatility assets (BTCUSD, XAUUSD).
        Blocks entry if VPIN > 0.75 (toxic informed order flow).
        """
        if is_backtest and as_of is None:
            return True, "vpin_check_backtest_exempt"
        try:
            from indicators.microstructure import VPIN_SYMBOLS
            if symbol.upper() not in VPIN_SYMBOLS:
                return True, f"{symbol} exempt from VPIN check"

            from database.models import TechnicalIndicator
            stmt = (
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.indicator_name == "ORDER_FLOW_SNAPSHOT")
            )
            if as_of is not None:
                stmt = stmt.where(TechnicalIndicator.timestamp <= as_of)
            row = (await session.execute(
                stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
            )).scalar_one_or_none()

            if row and row.value_json:
                data = json.loads(row.value_json)
                vpin = data.get("vpin")
                if vpin is not None and float(vpin) > 0.75:
                    return False, f"VPIN order flow toxicity {vpin:.2f} > 0.75 threshold (adverse selection risk high)"
                return True, f"VPIN={vpin or 'n/a'} (clean flow)"
            return True, "VPIN check ok (no snapshot)"
        except Exception as e:
            logger.debug(f"VPIN toxicity check error: {e}")
            return True, "vpin_check_fallback_ok"


async def get_current_risk_state(session: Optional[AsyncSession] = None, settings: Optional[dict] = None) -> dict:
    """Mengambil snapshot status risiko portofolio & drawdown saat ini."""
    if not session:
        return {"status": "unavailable", "message": "No active DB session"}
    today_start = get_daily_risk_cutoff(clock.now(), (settings or {}).get("trading", {}).get("risk", {}))
    exec_res = await session.execute(
        select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
    )
    risk_row = exec_res.scalar_one_or_none()
    if asyncio.iscoroutine(risk_row):
        risk_row = await risk_row

    if not risk_row:
        exec_res2 = await session.execute(
            select(RiskState).order_by(RiskState.date.desc()).limit(1)
        )
        risk_row = exec_res2.scalar_one_or_none()
        if asyncio.iscoroutine(risk_row):
            risk_row = await risk_row

    pos_exec = await session.execute(
        select(func.count(Position.id)).where(Position.status == "open")
    )
    pos_count = pos_exec.scalar()
    if asyncio.iscoroutine(pos_count):
        pos_count = await pos_count
    pos_count = pos_count or 0
    max_dd = float((settings or {}).get("trading", {}).get("risk", {}).get("max_daily_drawdown_percent", 3.0))

    if risk_row:
        return {
            "date": risk_row.date.isoformat() if risk_row.date else None,
            "starting_equity": 0.0,
            "current_equity": 0.0,
            "current_drawdown_pct": risk_row.current_drawdown,
            "max_drawdown_limit_pct": max_dd,
            "is_trading_paused": risk_row.trading_paused,
            "pause_reason": risk_row.reason,
            "open_positions_count": pos_count,
            "status": "paused" if risk_row.trading_paused else "normal"
        }
    return {
        "status": "normal",
        "current_drawdown_pct": 0.0,
        "is_trading_paused": False,
        "open_positions_count": pos_count,
    }

