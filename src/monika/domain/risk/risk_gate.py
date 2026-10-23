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
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, UTC
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import monika.core.primitives.clock as clock
from monika.domain.entities.order_status import OrderStatus
from monika.domain.risk.evaluators.base import resolve_model

Position: Any = resolve_model("Position")
RiskState: Any = resolve_model("RiskState")
EconomicCalendar: Any = resolve_model("EconomicCalendar")
OrderLog: Any = resolve_model("OrderLog")
TradeOutcome: Any = resolve_model("TradeOutcome")
PaperTradeRecord: Any = resolve_model("PaperTradeRecord")
AssetAnalysis: Any = resolve_model("AssetAnalysis")
SystemConfig: Any = resolve_model("SystemConfig")
Order: Any = resolve_model("Order")
PriceOHLCV: Any = resolve_model("PriceOHLCV")
VIXData: Any = resolve_model("VIXData")
UserPreference: Any = resolve_model("UserPreference")
TechnicalIndicator: Any = resolve_model("TechnicalIndicator")
TimesFMForecast: Any = resolve_model("TimesFMForecast")


from monika.domain.risk.position_sizing import SizingResult
from monika.domain.risk.evaluators import (
    RiskExecutionChecksMixin,
    RiskIntelligenceChecksMixin,
    RiskMarketChecksMixin,
    RiskPortfolioChecksMixin,
)


logger = logging.getLogger("TradingAgent.RiskGate")


# Simpler: track per base-currency exposure
from monika.domain.market.currency_utils import SYMBOL_CURRENCIES, get_symbol_currencies

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


def get_trading_day_start(settings: dict, now: datetime | None = None) -> datetime:
    """
    Menghitung waktu mulai hari perdagangan berdasarkan broker daily rollover.
    Default: 21:00 UTC (17:00 New York / NY Close), aware terhadap Daylight Saving Time.
    """
    if now is None:
        from monika.core.primitives.clock import now as get_clock_now

        now = get_clock_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

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

            tz_start = (now_tz - timedelta(days=1)).replace(
                hour=broker_rollover_hour, minute=0, second=0, microsecond=0
            )
        return tz_start.astimezone(UTC)
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


class RiskGate(
    RiskExecutionChecksMixin,
    RiskPortfolioChecksMixin,
    RiskMarketChecksMixin,
    RiskIntelligenceChecksMixin,
):
    """
    Risk Gate — Layer validasi pra-eksekusi. Sistem yang memutuskan, bukan AI.
    Memvalidasi seluruh proposal trade terhadap serangkaian aturan risiko deterministik.
    """

    def __init__(
        self,
        settings: dict,
        mt5_client=None,
        flash_crash_detector=None,
        data_provider: Any | None = None,
    ):
        """
        Args:
        settings:   Full settings dict (uses trading.risk section).
        mt5_client: Optional live MT5Client for real-time account info.
        flash_crash_detector: Optional FlashCrashDetector instance.
        data_provider: Optional RiskDataProviderProtocol instance for decoupled persistence.
        """
        risk_cfg = (
            settings.get("trading", {}).get("risk") or settings.get("risk", {}) if isinstance(settings, dict) else {}
        )
        self.settings = settings
        self.max_daily_drawdown_pct: float = risk_cfg.get("max_daily_drawdown_percent", 4.0)
        self.max_concurrent: int = risk_cfg.get("max_concurrent_positions", 5)
        self.correlation_limit: int = risk_cfg.get("correlation_limit", 3)
        self.news_window_minutes: int = risk_cfg.get("news_window_minutes", 15)
        self.max_risk_pct: float = float(
            risk_cfg.get("risk_percent_per_trade")
            or risk_cfg.get("max_risk_per_trade_percent")
            or risk_cfg.get("risk_per_trade_pct")
            or 1.0
        )
        self._mt5 = mt5_client
        self.flash_crash_detector = flash_crash_detector
        self._data_provider = data_provider
        from monika.domain.risk.correlation_matrix import DynamicCorrelationMatrix

        self.dynamic_correlation_matrix = DynamicCorrelationMatrix(
            rolling_days=int(risk_cfg.get("correlation_rolling_days", 30)),
            correlation_threshold=float(risk_cfg.get("correlation_threshold", 0.65)),
        )
        self.correlation_matrix = self.dynamic_correlation_matrix
        from monika.domain.risk.risk_rule_plugin import ModularRiskRegistry

        self.modular_risk_registry = ModularRiskRegistry()

    def data_provider(self):
        """Lazy-load default RiskDataProvider via domain port when not explicitly injected."""
        if self._data_provider is None:
            from monika.domain.risk.ports import get_default_risk_data_provider

            self._data_provider = get_default_risk_data_provider(settings=self.settings)
        return self._data_provider

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

    async def evaluate(
        self,
        session: Any,
        symbol: str,
        direction: str,
        sizing: SizingResult,
        account_equity: float | None = None,
        analysis: Any | None = None,
        as_of: datetime | None = None,
        simulated_positions: list | None = None,
        simulated_equity: float | None = None,
        simulated_daily_pnl: float | None = None,
        is_backtest: bool = False,
        pair_group_id: str | None = None,
        is_paper: bool | None = None,
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
        rejections: list[str] = []

        effective_pair_group = pair_group_id or getattr(analysis, "pair_group_id", None)
        effective_is_paper = (
            is_paper if is_paper is not None else self.settings.get("paper_trading", {}).get("enabled", True)
        )
        if not effective_is_paper and not is_backtest:
            if account_equity is None or account_equity <= 0:
                return RiskVerdict(
                    approved=False,
                    symbol=symbol,
                    proposed_lots=sizing.recommended_lots if sizing else 0.0,
                    checks_passed=[],
                    checks_failed=["live_equity_unavailable"],
                    rejection_reasons=[
                        "Live account equity is unavailable or zero; order rejected for capital preservation"
                    ],
                )
            equity = account_equity
        else:
            fallback_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
            equity = (
                simulated_equity
                if (is_backtest and simulated_equity is not None)
                else (account_equity or fallback_equity)
            )

        try:
            from monika.domain.risk.ports import emit_risk_hook

            await emit_risk_hook(
                "PRE_RISK_GATE",
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
            (
                "daily_trade_count",
                self._check_daily_trade_count(session, is_backtest=is_backtest, is_paper=effective_is_paper),
            ),
            ("trading_not_paused", self._check_not_paused(session, is_backtest=is_backtest)),
            ("edge_status_not_paused", self._check_edge_status_not_paused(session, is_backtest=is_backtest)),
            ("vix_threshold", self._check_vix_threshold(session, as_of=as_of, is_backtest=is_backtest)),
            ("flash_crash_cooldown", self._check_flash_crash_cooldown(symbol)),
            ("sizing_valid", self._check_sizing_valid(sizing)),
            ("lot_size", self._check_lot_size(sizing)),
            (
                "daily_drawdown",
                self._check_daily_drawdown(
                    session,
                    equity,
                    simulated_daily_pnl=simulated_daily_pnl,
                    is_backtest=is_backtest,
                    is_paper=effective_is_paper,
                ),
            ),
            (
                "weekly_drawdown",
                self._check_weekly_drawdown(session, equity, is_backtest=is_backtest, is_paper=effective_is_paper),
            ),
            (
                "max_concurrent_positions",
                self._check_max_positions(
                    session, simulated_positions=simulated_positions, is_paper=effective_is_paper
                ),
            ),
            (
                "no_duplicate_symbol",
                self._check_no_duplicate(
                    session,
                    symbol,
                    simulated_positions=simulated_positions,
                    pair_group_id=effective_pair_group,
                    is_paper=effective_is_paper,
                ),
            ),
            (
                "portfolio_heat",
                self._check_total_portfolio_heat(session, sizing, equity, simulated_positions=simulated_positions),
            ),
            ("weekend_proximity", self.assess_weekend_gap_risk(session, symbol, as_of=as_of)),
            ("rollover_window", self._check_rollover_window(symbol, as_of=as_of)),
            ("post_sl_cooldown", self._check_post_loss_cooldown(session, symbol, as_of=as_of, is_backtest=is_backtest)),
            (
                "news_window",
                self._check_news_window(
                    session, symbol, as_of=as_of, is_backtest=is_backtest, is_paper=effective_is_paper
                ),
            ),
            (
                "correlation_exposure",
                self._check_correlation(
                    session,
                    symbol,
                    direction,
                    simulated_positions=simulated_positions,
                    as_of=as_of,
                    volume=getattr(sizing, "recommended_lots", getattr(sizing, "lot_size", None)) if sizing else None,
                ),
            ),
            ("consecutive_losses", self._check_consecutive_losses(session, symbol, is_backtest=is_backtest)),
            ("data_freshness", self._check_data_freshness(session, symbol, as_of=as_of, is_backtest=is_backtest)),
            (
                "timesfm_expectancy",
                self._check_timesfm_expectancy(
                    session, symbol, direction, sizing, is_backtest=is_backtest, proposal=analysis
                ),
            ),
            (
                "schmitt_regime",
                self._check_schmitt_regime(
                    session, symbol, simulated_positions=simulated_positions, is_backtest=is_backtest
                ),
            ),
            (
                "macro_regime",
                self._check_macro_regime(session, symbol, direction, as_of=as_of, is_backtest=is_backtest),
            ),
            ("vpin_toxicity", self._check_vpin_toxicity(session, symbol, as_of=as_of, is_backtest=is_backtest)),
            (
                "adv_liquidity_floor",
                self._check_adv_liquidity(session, symbol, sizing, as_of=as_of, is_backtest=is_backtest),
            ),
            (
                "copula_tail_risk",
                self._check_copula_tail_risk(
                    session, symbol, simulated_positions=simulated_positions, as_of=as_of, is_backtest=is_backtest
                ),
            ),
            ("evidence_gate", self._check_evidence_gate(session, symbol, analysis=analysis, is_backtest=is_backtest)),
            (
                "bounded_mandate",
                self._check_bounded_mandate(
                    session, symbol, sizing, as_of=as_of, simulated_positions=simulated_positions
                ),
            ),
            ("min_rr_ratio", self._check_min_rr_ratio(sizing)),
            (
                "max_spread",
                self._check_max_spread(session, symbol, is_backtest=is_backtest, is_paper=effective_is_paper),
            ),
        ]

        if analysis is not None:
            checks.append(("analysis_quality_scores", self._check_analysis_quality_scores(analysis, session=session)))
            checks.append(
                (
                    "strategy_factor_exposure",
                    self._check_strategy_factor_exposure(session, analysis, simulated_positions=simulated_positions),
                )
            )

        for name, coro in checks:
            await run_check(name, coro)

        if hasattr(self, "modular_risk_registry") and self.modular_risk_registry:
            try:
                mod_ok, mod_passed, mod_failed, mod_reasons = await self.modular_risk_registry.evaluate_modular_rules(
                    session=session,
                    symbol=symbol,
                    direction=direction,
                    sizing=sizing,
                    account_equity=equity,
                    analysis=analysis,
                    is_backtest=is_backtest,
                )
                checks_passed.extend(mod_passed)
                checks_failed.extend(mod_failed)
                rejections.extend(mod_reasons)
            except Exception as e:
                logger.error(f"Modular risk registry evaluation failed: {e}")
                checks_failed.append("modular_risk_registry")
                rejections.append(f"[modular_risk_registry] Evaluation crashed: {e}")

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
                from monika.domain.risk.ports import get_default_event_publisher

                event_store_cls = get_default_event_publisher()
                if event_store_cls and hasattr(event_store_cls, "emit"):
                    await event_store_cls.emit(
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

            try:
                from monika.core.telemetry.metrics_exporter import metrics

                if approved:
                    metrics.inc_counter("risk_checks_approved_total", 1.0, labels={"symbol": symbol})
                else:
                    metrics.inc_counter("risk_checks_rejected_total", 1.0, labels={"symbol": symbol})
            except Exception:
                pass

        if is_backtest:
            log_fn = logger.debug
        else:
            log_fn = logger.info if approved else logger.warning
        log_fn(verdict.summary())
        return verdict

    async def evaluate_proposal(
        self,
        session: Any,
        proposal: Any,
        account_equity: float | None = None,
        analysis: Any | None = None,
        as_of: datetime | None = None,
        is_backtest: bool = False,
        is_paper: bool | None = None,
    ) -> RiskVerdict:
        """
        PR-14: Financial Fortress entrypoint validating an immutable TradeProposal.
        First executes FortressAdmissionValidator boundary checks.
        If admitted, transforms proposal parameters into SizingResult and delegates to evaluate().
        """
        from monika.domain.risk.trade_proposal import FortressAdmissionValidator

        admitted, rejections = FortressAdmissionValidator.validate_proposal(proposal)
        if not admitted:
            logger.warning(
                f"[{proposal.symbol}] Fortress admission rejected proposal {proposal.proposal_id}: {rejections}"
            )
            return RiskVerdict(
                approved=False,
                symbol=proposal.symbol,
                proposed_lots=proposal.lot_size,
                checks_passed=[],
                checks_failed=["fortress_admission"],
                rejection_reasons=rejections,
            )

        # PR-3: Validate against registered runtime invariants
        try:
            from monika.domain.risk.invariants import get_global_invariant_registry

            current_dd_pct = 0.0
            try:
                state = await self._get_risk_state(session)
                if state and state.daily_drawdown_pct is not None:
                    current_dd_pct = float(state.daily_drawdown_pct)
            except Exception:
                logger.error("Failed to fetch risk state for invariant validation", exc_info=True)
                if session is not None:
                    return RiskVerdict(
                        approved=False,
                        symbol=proposal.symbol,
                        proposed_lots=proposal.lot_size,
                        checks_passed=[],
                        checks_failed=["DB_RISK_STATE_ERROR"],
                        rejection_reasons=["Fail-Closed: Risk state database query failed during drawdown evaluation"],
                    )
            open_pos_list: list[Any] = []
            if session is not None:
                try:
                    from sqlalchemy import select

                    pos_model = Position or resolve_model("Position")
                    if pos_model:
                        open_pos_list = list(
                            (await session.execute(select(pos_model).where(pos_model.status == "open"))).scalars().all()
                        )
                except Exception as e:
                    logger.debug(f"Failed to fetch open positions for invariant check: {e}")

            inv_ctx = {
                "proposal": proposal,
                "max_drawdown_limit": self.max_daily_drawdown_pct,
                "current_drawdown_pct": current_dd_pct,
                "min_rr_ratio": float(self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.5)),
                "open_positions": open_pos_list,
                "max_concurrent_positions": self.max_concurrent,
            }
            inv_results = get_global_invariant_registry().run_all(inv_ctx, fail_fast=False)
            inv_failures = [r for r in inv_results if r.failed]
            if inv_failures:
                failure_names = [f.name for f in inv_failures]
                failure_msgs = [f"[{f.name}] {f.message}" for f in inv_failures]
                logger.warning(
                    f"[{proposal.symbol}] Runtime invariant failures for proposal {proposal.proposal_id}: {failure_msgs}"
                )
                return RiskVerdict(
                    approved=False,
                    symbol=proposal.symbol,
                    proposed_lots=proposal.lot_size,
                    checks_passed=[],
                    checks_failed=failure_names,
                    rejection_reasons=failure_msgs,
                )
        except Exception as e:
            logger.error(f"[{proposal.symbol}] Runtime invariant registry check critical error: {e}")
            return RiskVerdict(
                approved=False,
                symbol=proposal.symbol,
                proposed_lots=proposal.lot_size,
                checks_passed=[],
                checks_failed=["invariant_registry_error"],
                rejection_reasons=[f"Runtime invariant registry check error (fail-closed): {e}"],
            )

        if proposal.direction == "WAIT":
            return RiskVerdict(
                approved=True,
                symbol=proposal.symbol,
                proposed_lots=0.0,
                checks_passed=["fortress_admission", "non_directional"],
                checks_failed=[],
                rejection_reasons=[],
            )

        eq = (
            account_equity
            or proposal.account_equity
            or float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        )
        if proposal.direction == "BUY":
            if proposal.stop_loss >= proposal.entry_price:
                return RiskVerdict(
                    approved=False,
                    symbol=proposal.symbol,
                    proposed_lots=proposal.lot_size,
                    checks_passed=[],
                    checks_failed=["geometric_invariants"],
                    rejection_reasons=[
                        f"BUY geometry violation: Stop loss ({proposal.stop_loss}) >= Entry ({proposal.entry_price})"
                    ],
                )
            if proposal.take_profit and proposal.take_profit <= proposal.entry_price:
                return RiskVerdict(
                    approved=False,
                    symbol=proposal.symbol,
                    proposed_lots=proposal.lot_size,
                    checks_passed=[],
                    checks_failed=["geometric_invariants"],
                    rejection_reasons=[
                        f"BUY geometry violation: Take profit ({proposal.take_profit}) <= Entry ({proposal.entry_price})"
                    ],
                )
            sl_dist = max(1e-7, proposal.entry_price - proposal.stop_loss)
            tp_dist = max(0.0, proposal.take_profit - proposal.entry_price) if proposal.take_profit else 0.0
        elif proposal.direction == "SELL":
            if proposal.stop_loss <= proposal.entry_price:
                return RiskVerdict(
                    approved=False,
                    symbol=proposal.symbol,
                    proposed_lots=proposal.lot_size,
                    checks_passed=[],
                    checks_failed=["geometric_invariants"],
                    rejection_reasons=[
                        f"SELL geometry violation: Stop loss ({proposal.stop_loss}) <= Entry ({proposal.entry_price})"
                    ],
                )
            if proposal.take_profit and proposal.take_profit >= proposal.entry_price:
                return RiskVerdict(
                    approved=False,
                    symbol=proposal.symbol,
                    proposed_lots=proposal.lot_size,
                    checks_passed=[],
                    checks_failed=["geometric_invariants"],
                    rejection_reasons=[
                        f"SELL geometry violation: Take profit ({proposal.take_profit}) >= Entry ({proposal.entry_price})"
                    ],
                )
            sl_dist = max(1e-7, proposal.stop_loss - proposal.entry_price)
            tp_dist = max(0.0, proposal.entry_price - proposal.take_profit) if proposal.take_profit else 0.0
        else:
            sl_dist = abs(proposal.entry_price - proposal.stop_loss)
            tp_dist = abs(proposal.take_profit - proposal.entry_price) if proposal.take_profit else 0.0

        rr = (tp_dist / sl_dist) if sl_dist > 1e-7 else 1.0
        risk_pct = float(proposal.metadata.get("risk_pct", 1.0)) if isinstance(proposal.metadata, dict) else 1.0
        risk_amount = eq * (risk_pct / 100.0)
        pip_val = 10.0
        try:
            from monika.domain.risk.position_sizing import get_instrument_spec

            spec = get_instrument_spec(proposal.symbol)
            if spec and spec.pip_value_per_lot > 0:
                pip_val = float(spec.pip_value_per_lot)
            pips = (
                sl_dist / spec.pip_size
                if spec and spec.pip_size > 0
                else (sl_dist * 100.0 if "JPY" in proposal.symbol else sl_dist * 10000.0)
            )
        except Exception:
            pips = sl_dist * 100.0 if "JPY" in proposal.symbol else sl_dist * 10000.0

        sizing = SizingResult(
            symbol=proposal.symbol,
            direction=proposal.direction.lower(),
            entry_price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
            account_equity=eq,
            risk_percent=risk_pct,
            risk_amount_usd=risk_amount,
            sl_distance_price=sl_dist,
            sl_distance_pips=pips,
            pip_value_per_lot=pip_val,
            raw_lots=proposal.lot_size,
            recommended_lots=proposal.lot_size,
            rr_ratio=rr,
            is_valid=True,
        )

        return await self.evaluate(
            session=session,
            symbol=proposal.symbol,
            direction=proposal.direction.lower(),
            sizing=sizing,
            account_equity=account_equity or proposal.account_equity,
            analysis=analysis or getattr(proposal, "analysis", None),
            as_of=as_of,
            is_backtest=is_backtest,
            is_paper=is_paper,
        )

    # Backward compatibility aliases
    check = evaluate
    check_proposal = evaluate_proposal
    _check_weekend_gap_risk = RiskMarketChecksMixin.assess_weekend_gap_risk

    async def _get_risk_state(self, session: Any) -> Any | None:
        """Fetch current RiskState from DB."""
        if not session:
            return None
        try:
            from sqlalchemy import desc, select

            risk_model = RiskState or resolve_model("RiskState")
            if risk_model is None:
                return None
            stmt = select(risk_model).order_by(desc(risk_model.date)).limit(1)
            return (await session.execute(stmt)).scalar_one_or_none()
        except Exception:
            return None

    async def _log_verdict(
        self, session: Any, symbol: str, direction: str, sizing: SizingResult, verdict: RiskVerdict
    ) -> None:
        """Catat keputusan risk gate ke tabel orders_log."""
        import json

        log_model = OrderLog or resolve_model("OrderLog")
        if log_model is None:
            return
        record = log_model(
            action="risk_check",
            symbol=symbol,
            params_json=json.dumps(
                {
                    "direction": direction,
                    "proposed_lots": sizing.recommended_lots,
                    "risk_amount_usd": sizing.risk_amount_usd,
                    "risk_percent": sizing.risk_percent,
                    "sl_pips": getattr(sizing, "sl_distance_pips", getattr(sizing, "sl_pips", 0.0)),
                    "rr_ratio": sizing.rr_ratio,
                }
            ),
            requested_by="strategy_pipeline",
            approved_by="risk_gate" if verdict.approved else None,
            result=json.dumps(
                {
                    "approved": verdict.approved,
                    "checks_passed": verdict.checks_passed,
                    "checks_failed": verdict.checks_failed,
                    "rejection_reasons": verdict.rejection_reasons,
                }
            ),
        )
        session.add(record)
        await session.flush()

    async def update_risk_state(
        self,
        session: Any,
        pnl_delta: float,
        equity: float | None = None,
    ) -> None:
        """Update RiskState harian setelah posisi tertutup. Trigger auto-pause jika lewat batas."""
        from sqlalchemy import select

        risk_model = RiskState or resolve_model("RiskState")
        today_start = get_trading_day_start(self.settings)
        state = (
            await session.execute(
                select(risk_model).where(risk_model.date >= today_start).order_by(risk_model.date.desc()).limit(1)
            )
        ).scalar_one_or_none()

        if state is None:
            state = risk_model(
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
        drawdown_pct = (
            (abs(state.current_drawdown) / equity * 100)
            if (equity is not None and equity > 0 and state.current_drawdown < 0)
            else 0.0
        )
        if drawdown_pct >= self.max_daily_drawdown_pct and not state.trading_paused:
            state.trading_paused = True
            state.reason = f"Auto-paused: daily drawdown {drawdown_pct:.2f}% >= limit {self.max_daily_drawdown_pct}%"
            logger.warning(f"TRADING AUTO-PAUSED: {state.reason}")

            try:
                from monika.domain.risk.ports import get_default_notifier

                notifier = get_default_notifier()
                if notifier and hasattr(notifier, "send_critical"):
                    await notifier.send_critical(f"[STOP] <b>TRADING AUTO-PAUSED</b>\n{state.reason}")
            except Exception as e:
                logger.error(f"Failed to notify auto-pause: {e}")

        await session.commit()
        logger.info(
            f"RiskState updated: daily_pnl=${state.daily_pnl:.2f}, "
            f"drawdown=${state.current_drawdown:.2f} ({drawdown_pct:.2f}%), "
            f"paused={state.trading_paused}"
        )

    async def pause_trading(self, session: Any, reason: str, duration_hours: float | None = None) -> None:
        """Pause sistem trading secara manual dengan opsi durasi auto-unpause."""
        from datetime import timedelta
        from sqlalchemy import select

        risk_model = RiskState or resolve_model("RiskState")
        sys_model = SystemConfig or resolve_model("SystemConfig")
        today_start = get_trading_day_start(self.settings)
        state = (
            await session.execute(select(risk_model).where(risk_model.date >= today_start).limit(1))
        ).scalar_one_or_none()

        now = clock.now()
        unpause_at = (now + timedelta(hours=duration_hours)) if duration_hours and duration_hours > 0 else None

        if state is None:
            state = risk_model(date=now, daily_pnl=0, current_drawdown=0)
            session.add(state)

        state.trading_paused = True
        state.reason = reason
        state.unpause_at = unpause_at

        # Persist across midnight rollover via SystemConfig
        cfg_val = f"true:{reason}"
        if unpause_at:
            cfg_val += f"|unpause_at:{unpause_at.isoformat()}"

        cfg = (
            await session.execute(select(sys_model).where(sys_model.key == "manual_trading_paused"))
        ).scalar_one_or_none()
        if cfg:
            cfg.value = cfg_val
        else:
            session.add(sys_model(key="manual_trading_paused", value=cfg_val))

        await session.commit()
        unpause_info = f" (auto-unpause at {unpause_at.strftime('%Y-%m-%d %H:%M UTC')})" if unpause_at else ""
        logger.warning(f"Trading manually PAUSED: {reason}{unpause_info}")

    async def clear_edge_status_pause(self, session: Any) -> None:
        from sqlalchemy import select

        sys_model = SystemConfig or resolve_model("SystemConfig")
        cfg = (await session.execute(select(sys_model).where(sys_model.key == "trading_paused"))).scalar_one_or_none()
        if cfg and cfg.value:
            cfg.value = "false"
            logger.info("Edge-status auto-pause cleared.")

    async def resume_trading(self, session: Any) -> None:
        """Lanjutkan (resume) trading secara manual."""
        from sqlalchemy import select

        risk_model = RiskState or resolve_model("RiskState")
        sys_model = SystemConfig or resolve_model("SystemConfig")
        today_start = get_trading_day_start(self.settings)
        state = (
            await session.execute(select(risk_model).where(risk_model.date >= today_start).limit(1))
        ).scalar_one_or_none()

        if state:
            state.trading_paused = False
            state.reason = None
            state.unpause_at = None

        for key in ("manual_trading_paused", "kill_switch", "trading_paused", "system_paused"):
            cfg = (await session.execute(select(sys_model).where(sys_model.key == key))).scalar_one_or_none()
            if cfg:
                cfg.value = "false"

        await self.clear_edge_status_pause(session)

        # Bersihkan juga suspended symbols saat resume trading dipanggil
        try:
            from monika.domain.risk.ports import get_default_suspended_symbols_provider

            provider_factory = get_default_suspended_symbols_provider()
            if provider_factory is not None:
                tracker = provider_factory(self.settings)
                await tracker.unsuspend_all(session)
        except Exception as e:
            logger.debug(f"Failed to clear suspended symbols on resume: {e}")

        await session.commit()
        logger.info(
            "Trading manually RESUMED (RiskState + Manual + KillSwitch + EdgeTracker + SuspendedSymbols flags cleared)"
        )

    async def get_current_scorecard(
        self,
        session: Any,
        symbol: str = "EURUSD",
        equity: float | None = None,
    ) -> dict[str, Any]:
        """Menghasilkan evaluasi scorecard 22-poin Risk Gate saat ini untuk status inspeksi."""
        fallback_equity = float(self.settings.get("paper_trading", {}).get("initial_balance", 10000.0))
        eq = equity or fallback_equity
        dummy_sizing = SizingResult(
            symbol=symbol,
            direction="BUY",
            entry_price=1.0,
            stop_loss=0.99,
            take_profit=1.02,
            account_equity=eq,
            risk_percent=self.max_risk_pct,
            risk_amount_usd=eq * (self.max_risk_pct / 100.0),
            sl_distance_price=0.01,
            sl_distance_pips=20.0,
            pip_value_per_lot=10.0,
            raw_lots=0.01,
            recommended_lots=0.01,
            rr_ratio=2.0,
            is_valid=True,
        )

        checks_data: dict[str, Any] = {}
        passed: list[str] = []
        failed: list[str] = []

        checks = [
            ("daily_trade_count", self._check_daily_trade_count(session)),
            ("trading_not_paused", self._check_not_paused(session)),
            ("edge_status_not_paused", self._check_edge_status_not_paused(session)),
            ("vix_threshold", self._check_vix_threshold(session)),
            ("flash_crash_cooldown", self._check_flash_crash_cooldown(symbol)),
            ("sizing_valid", self._check_sizing_valid(dummy_sizing)),
            ("lot_size", self._check_lot_size(dummy_sizing)),
            ("daily_drawdown", self._check_daily_drawdown(session, eq)),
            ("weekly_drawdown", self._check_weekly_drawdown(session, eq)),
            ("max_concurrent_positions", self._check_max_positions(session)),
            ("no_duplicate_symbol", self._check_no_duplicate(session, symbol)),
            ("portfolio_heat", self._check_total_portfolio_heat(session, dummy_sizing, eq)),
            ("weekend_proximity", self.assess_weekend_gap_risk(session, symbol)),
            ("rollover_window", self._check_rollover_window(symbol)),
            ("post_sl_cooldown", self._check_post_loss_cooldown(session, symbol)),
            ("news_window", self._check_news_window(session, symbol)),
            ("correlation_exposure", self._check_correlation(session, symbol, "buy")),
            ("consecutive_losses", self._check_consecutive_losses(session, symbol)),
            ("data_freshness", self._check_data_freshness(session, symbol)),
            ("timesfm_expectancy", self._check_timesfm_expectancy(session, symbol, "buy", dummy_sizing)),
            ("schmitt_regime", self._check_schmitt_regime(session, symbol)),
            ("macro_regime", self._check_macro_regime(session, symbol, "buy")),
            ("vpin_toxicity", self._check_vpin_toxicity(session, symbol)),
            ("adv_liquidity_floor", self._check_adv_liquidity(session, symbol, dummy_sizing)),
            ("copula_tail_risk", self._check_copula_tail_risk(session, symbol)),
            ("evidence_gate", self._check_evidence_gate(session, symbol)),
            ("bounded_mandate", self._check_bounded_mandate(session, symbol, dummy_sizing)),
        ]

        for name, coro in checks:
            try:
                ok, reason = await coro
                checks_data[name] = {"passed": bool(ok), "reason": str(reason)}
                if ok:
                    passed.append(name)
                else:
                    failed.append(name)
            except Exception as e:
                checks_data[name] = {"passed": False, "reason": f"Check error: {e}"}
                failed.append(name)

        return {
            "symbol": symbol,
            "account_equity": eq,
            "total_checks": len(checks),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "pass_rate_pct": round((len(passed) / len(checks)) * 100, 1),
            "checks_passed": passed,
            "checks_failed": failed,
            "checks": checks_data,
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def get_current_risk_state(session: Any | None = None, settings: dict | None = None) -> dict:
    """Mengambil snapshot status risiko portofolio & drawdown saat ini."""
    if not session:
        try:
            from monika.domain.risk.ports import get_default_session_factory

            session_fn = get_default_session_factory()
            if session_fn:
                async with session_fn() as sess:
                    return await get_current_risk_state(session=sess, settings=settings)
        except Exception:
            pass
        return {"status": "unavailable", "message": "No active DB session"}

    from sqlalchemy import func, select

    risk_model = RiskState or resolve_model("RiskState")
    pos_model = Position or resolve_model("Position")

    today_start = get_daily_risk_cutoff(clock.now(), (settings or {}).get("trading", {}).get("risk", {}))
    exec_res = await session.execute(
        select(risk_model).where(risk_model.date >= today_start).order_by(risk_model.date.desc()).limit(1)
    )
    risk_row = exec_res.scalar_one_or_none()
    if asyncio.iscoroutine(risk_row):
        risk_row = await risk_row

    if not risk_row:
        exec_res2 = await session.execute(select(risk_model).order_by(risk_model.date.desc()).limit(1))
        risk_row = exec_res2.scalar_one_or_none()
        if asyncio.iscoroutine(risk_row):
            risk_row = await risk_row

    pos_exec = await session.execute(select(func.count(pos_model.id)).where(pos_model.status == "open"))
    pos_count = pos_exec.scalar()
    if asyncio.iscoroutine(pos_count):
        pos_count = await pos_count
    pos_count = pos_count or 0
    max_dd = float((settings or {}).get("trading", {}).get("risk", {}).get("max_daily_drawdown_percent", 4.0))

    # Fetch live equity from MT5 or fallback to paper trading initial balance
    live_equity = 0.0
    try:
        from monika.domain.risk.ports import get_default_broker_client

        client: Any = get_default_broker_client(settings)
        if client and hasattr(client, "get_account_info"):
            try:
                async with asyncio.timeout(2.0):
                    acc = await client.get_account_info()
                    if acc and acc.get("equity"):
                        live_equity = float(acc["equity"])
            except Exception:
                pass
    except Exception:
        pass
    if live_equity <= 0:
        live_equity = float((settings or {}).get("paper_trading", {}).get("initial_balance", 10000.0))

    if risk_row:
        return {
            "date": risk_row.date.isoformat() if risk_row.date else None,
            "starting_equity": live_equity,
            "current_equity": live_equity,
            "current_drawdown_pct": risk_row.current_drawdown,
            "max_drawdown_limit_pct": max_dd,
            "is_trading_paused": risk_row.trading_paused,
            "pause_reason": risk_row.reason,
            "open_positions_count": pos_count,
            "status": "paused" if risk_row.trading_paused else "normal",
        }
    return {
        "status": "normal",
        "starting_equity": live_equity,
        "current_equity": live_equity,
        "current_drawdown_pct": 0.0,
        "max_drawdown_limit_pct": max_dd,
        "is_trading_paused": False,
        "open_positions_count": pos_count,
    }
