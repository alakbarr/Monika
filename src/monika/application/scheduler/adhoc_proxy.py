"""
Ad-Hoc Scheduler Proxy for standalone/on-demand LangGraph execution.
Decouples agent loop orchestration from monika.application.graph node dependencies.
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("TradingAgent.Scheduler.AdHocProxy")


class AdHocSchedulerProxy:
    """Proxy scheduler for ad-hoc single-asset LangGraph pipelines."""

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        symbols: Optional[List[str]] = None,
        dry_run: bool = True,
        mt5_client: Optional[Any] = None,
        execution_service: Optional[Any] = None,
        risk_gate: Optional[Any] = None,
    ):
        self.settings = settings or {}
        self.asset_universe = symbols or []
        self.mt5_timeframes = ["M15", "H1", "H4", "D1"]
        self.dry_run = dry_run
        self._mt5 = mt5_client
        if self._mt5 is None:
            try:
                from monika.infrastructure.brokers.mt5_client import MT5Client
                self._mt5 = MT5Client(settings=self.settings)
            except Exception:
                pass

        self._risk_gate = risk_gate
        if self._risk_gate is None:
            try:
                from monika.domain.risk.risk_gate import RiskGate
                self._risk_gate = RiskGate(settings=self.settings)
            except Exception:
                pass

        self._execution_service = execution_service
        if self._execution_service is None:
            try:
                from monika.application.execution.execution_service import ExecutionService
                self._execution_service = ExecutionService(
                    settings=self.settings,
                    mt5_client=self._mt5,
                    risk_gate=self._risk_gate,
                    dry_run=self.dry_run,
                )
            except Exception:
                pass

        self.macro_data_scheduler = None
        self._activity_log = None
        self._stage1_consecutive_failures = 0
        self._max_stage1_failures_before_alert = 3

        # Sub-stage components
        try:
            from monika.application.analysis.stages.fundamental_stage import FundamentalStage
            self._fundamental = FundamentalStage(self.settings)
        except Exception as e:
            logger.debug(f"Failed to instantiate FundamentalStage in AdHocSchedulerProxy: {e}")
            self._fundamental = None

        try:
            from monika.application.analysis.stages.per_asset_stage import PerAssetStage
            self._per_asset = PerAssetStage(self.settings, mt5_client=self._mt5)
        except Exception as e:
            logger.debug(f"Failed to instantiate PerAssetStage in AdHocSchedulerProxy: {e}")
            self._per_asset = None

        try:
            from monika.core.analytics.paper_tracker import PaperTracker
            self._paper_tracker = PaperTracker(self.settings)
        except Exception as e:
            logger.debug(f"Failed to instantiate PaperTracker in AdHocSchedulerProxy: {e}")
            self._paper_tracker = None

    @property
    def execution_service(self):
        return self._execution_service

    @execution_service.setter
    def execution_service(self, value):
        self._execution_service = value

    @property
    def risk_gate(self):
        return self._risk_gate

    @risk_gate.setter
    def risk_gate(self, value):
        self._risk_gate = value

    async def _pre_cycle_setup(self, forced: bool = False) -> dict:
        """Pre-cycle setup for ad-hoc runs."""
        return {
            "should_skip": False,
            "skip_reason": None,
            "weekend_symbols_override": None,
            "effective_auto_execute": self.settings.get("trading", {}).get("auto_execute", False),
        }

    async def _should_skip_full_cycle(self) -> tuple[bool, str]:
        """Ad-hoc single-asset runs are user/trigger initiated — never smart-skip."""
        return False, ""

    async def _log(self, session, message: str, category: str = "ad_hoc"):
        """Non-blocking log helper."""
        pass

    async def _get_symbol_paper_stats(self, session, symbol: str) -> dict:
        """Paper stats retrieval for single symbol rolling window (matching CycleScheduler contract)."""
        if not session:
            return {"sufficient": False, "trades": 0, "win_rate": 50.0, "blocked": False}
        try:
            from monika.infrastructure.database.models import PaperTradeRecord
            from sqlalchemy import select
            stmt = (
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.status == "closed")
                .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
                .order_by(PaperTradeRecord.closed_at.desc().nullslast(), PaperTradeRecord.id.desc())
                .limit(20)
            )
            records = (await session.execute(stmt)).scalars().all()
            if len(records) < 5:
                return {"sufficient": False, "trades": len(records), "win_rate": 0.0, "blocked": False}
            wins = [r for r in records if r.exit_reason == "tp_hit"]
            win_rate = len(wins) / len(records) * 100.0
            return {
                "sufficient": True,
                "trades": len(records),
                "win_rate": win_rate,
                "blocked": win_rate < 35.0 and len(records) >= 8,
            }
        except Exception as e:
            logger.debug(f"Symbol stats check failed in AdHocSchedulerProxy: {e}")
            return {"sufficient": False, "trades": 0, "win_rate": 50.0, "blocked": False}

    async def _refresh_data_sources(self) -> Dict[str, Any]:
        return {"status": "ad_hoc_refresh_skipped"}
