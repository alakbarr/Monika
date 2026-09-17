# ==============================================================================
# File: agent/agent_loop.py
# ==============================================================================

"""
System Agent Loop & Ad-Hoc Pipeline Trigger.

Provides an operational agent loop coordinating system tasks and triggering
isolated single-asset LangGraph analytical pipeline executions on demand from
interactive control interfaces (Telegram / Terminal UI).

Key Capabilities:
1. Receives ad-hoc asset analysis requests (e.g., 'Analyze XAUUSD now').
2. Initializes isolated StateGraph context for single-symbol execution.
3. Compiles and executes the LangGraph state machine (build_trading_graph).
4. Extracts Bull/Bear dialectical debate evaluations, confluence scoring, SL/TP levels, and sizing.
5. Emits structured executive summaries formatted for chat and telemetry.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable, Awaitable, List

from graph.workflow import build_trading_graph

logger = logging.getLogger("TradingAgent.Agent.SystemAgentLoop")


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
                from execution.mt5_client import MT5Client
                self._mt5 = MT5Client(settings=self.settings)
            except Exception:
                pass

        self._risk_gate = risk_gate
        if self._risk_gate is None:
            try:
                from risk.risk_gate import RiskGate
                self._risk_gate = RiskGate(settings=self.settings)
            except Exception:
                pass

        self._execution_service = execution_service
        if self._execution_service is None:
            try:
                from execution.execution_service import ExecutionService
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
            from analysis.stages.fundamental_stage import FundamentalStage
            self._fundamental = FundamentalStage(self.settings)
        except Exception as e:
            logger.debug(f"Failed to instantiate FundamentalStage in AdHocSchedulerProxy: {e}")
            self._fundamental = None

        try:
            from analysis.stages.per_asset_stage import PerAssetStage
            self._per_asset = PerAssetStage(self.settings, mt5_client=self._mt5)
        except Exception as e:
            logger.debug(f"Failed to instantiate PerAssetStage in AdHocSchedulerProxy: {e}")
            self._per_asset = None

        try:
            from utils.analytics.paper_tracker import PaperTracker
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
            from database.models import PaperTradeRecord
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


class SystemAgentLoop:
    """
    Central System Agent Loop for conversational autonomy and ad-hoc pipeline execution.
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """Normalisasi format simbol (kapital, tanpa garis miring)."""
        if not symbol:
            return ""
        return symbol.strip().upper().replace("/", "")

    async def execute_ad_hoc_analysis(
        self,
        symbol: str,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        custom_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mengeksekusi siklus analisis LangGraph ad-hoc terisolasi untuk simbol tertentu.
        
        Args:
            symbol: Simbol instrumen (misal 'XAUUSD', 'EURUSD').
            progress_callback: Callback asinkron opsional untuk update progres ke chat.
            custom_context: Konteks instruksi tambahan dari user.
            
        Returns:
            Dict berisi detail keputusan, parameter trading, tesis debat, dan ringkasan teks.
        """
        sym_clean = self.normalize_symbol(symbol)
        if not sym_clean:
            return {"success": False, "error": "Simbol instrumen tidak valid atau kosong."}

        cycle_id = f"adhoc_{sym_clean}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
        logger.info(f"[SystemAgentLoop] Starting ad-hoc LangGraph pipeline for {sym_clean} (cycle_id={cycle_id})")

        if progress_callback:
            try:
                await progress_callback(f"🚀 Memulai analisis ad-hoc LangGraph untuk *{sym_clean}*...")
            except Exception as cb_err:
                logger.debug(f"Progress callback error: {cb_err}")

        # Inisialisasi TradingState terisolasi untuk single symbol
        initial_state: Dict[str, Any] = {
            "symbols": [sym_clean],
            "market_regime": "unknown",
            "vix_level": None,
            "brief_confidence": None,
            "asset_analyses": {},
            "debate_states": {},
            "risk_debate_states": {},
            "investment_verdicts": {},
            "portfolio_decisions": {},
            "approved_trades": [],
            "errors": [],
            "node_errors": {},
            "data_quality_scores": {},
            "cycle_id": cycle_id,
            "fundamental_retry_count": 0,
            "should_pause": False,
            "actionable_trades": [],
            "weekend_symbols_override": None,
            "stale_assets": [],
            "reflection_applied": False,
            "prior_cycle_insights": {},
            "consecutive_wait_count": 0,
            "last_buy_sell_cycle": None,
            "ssvp_per_symbol_contexts": {},
            "ssvp_cds_score": None,
            "ssvp_blocked": False,
            "ssvp_reconciliation_context": None,
            "context_snapshot_id": None,
            "ssvp_retry_count": 0,
            "user_market_intel": [],
            "refinement_count": 0,
            "rejection_feedback": None,
            "is_negotiable_rejection": False,
            "summary": {"is_ad_hoc": True, "custom_context": custom_context or ""},
        }

        try:
            # Bangun graf mandiri (in-memory MemorySaver)
            graph = build_trading_graph(db_url=None)
            ad_hoc_scheduler = AdHocSchedulerProxy(self.settings, [sym_clean])
            config = {
                "configurable": {
                    "thread_id": cycle_id,
                    "forced": True,
                    "is_ad_hoc": True,
                    "scheduler": ad_hoc_scheduler,
                    "settings": self.settings,
                }
            }

            if progress_callback:
                try:
                    await progress_callback(f"📊 Menjalankan pipeline multi-agent (Teknikal, Makro, Sentimen & Debat) untuk *{sym_clean}*...")
                except Exception:
                    pass

            final_state = await graph.ainvoke(initial_state, config=config)

            # Ekstrak hasil per aset
            asset_analyses = final_state.get("asset_analyses", {})
            analysis = asset_analyses.get(sym_clean, {})
            debate_states = final_state.get("debate_states", {})
            debate = debate_states.get(sym_clean, {})
            investment_verdicts = final_state.get("investment_verdicts", {})
            verdict = investment_verdicts.get(sym_clean, {})

            decision = str(analysis.get("decision") or verdict.get("final_decision") or verdict.get("action") or "WAIT").upper()
            confidence = float(analysis.get("confidence") or 0.0)
            entry_price = analysis.get("entry_price") or analysis.get("current_price")
            stop_loss = analysis.get("stop_loss")
            take_profit = analysis.get("take_profit")
            confluence = analysis.get("confluence_score") or analysis.get("confluence", 0)
            rationale = analysis.get("rationale") or analysis.get("notes") or "Analisis ad-hoc selesai."

            bull_thesis = debate.get("bull_case") or debate.get("bull_arguments") or ""
            bear_thesis = debate.get("bear_case") or debate.get("bear_arguments") or ""
            divergence = debate.get("divergence_score", 0.0)

            # Hitung Risk:Reward jika SL dan TP ada
            rr_ratio = None
            if entry_price and stop_loss and take_profit and entry_price > 0:
                try:
                    risk_dist = abs(float(entry_price) - float(stop_loss))
                    reward_dist = abs(float(take_profit) - float(entry_price))
                    if risk_dist > 0:
                        rr_ratio = round(reward_dist / risk_dist, 2)
                except Exception:
                    pass

            # Susun teks ringkasan eksekutif
            formatted_text = self._build_executive_summary(
                symbol=sym_clean,
                decision=decision,
                confidence=confidence,
                confluence=confluence,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                rr_ratio=rr_ratio,
                rationale=rationale,
                bull_thesis=bull_thesis,
                bear_thesis=bear_thesis,
                divergence=divergence,
            )

            logger.info(
                f"[SystemAgentLoop] Completed ad-hoc analysis for {sym_clean} -> "
                f"Decision={decision}, Conf={confidence:.2f}, Confluence={confluence}"
            )

            return {
                "success": True,
                "symbol": sym_clean,
                "cycle_id": cycle_id,
                "decision": decision,
                "confidence": confidence,
                "confluence_score": confluence,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward_ratio": rr_ratio,
                "rationale": rationale,
                "bull_thesis": bull_thesis,
                "bear_thesis": bear_thesis,
                "divergence": divergence,
                "formatted_summary": formatted_text,
                "final_state": final_state,
            }

        except Exception as e:
            logger.error(f"[SystemAgentLoop] Ad-hoc analysis failed for {sym_clean}: {e}", exc_info=True)
            return {
                "success": False,
                "symbol": sym_clean,
                "error": str(e),
                "formatted_summary": f"❌ Analisis ad-hoc untuk *{sym_clean}* mengalami kendala: {e}",
            }

    def _build_executive_summary(
        self,
        symbol: str,
        decision: str,
        confidence: float,
        confluence: Any,
        entry_price: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        rr_ratio: Optional[float],
        rationale: str,
        bull_thesis: str,
        bear_thesis: str,
        divergence: float,
    ) -> str:
        """Menyusun representasi teks bersih dan terstruktur untuk chat."""
        lines = [
            f"🎯 *HASIL ANALISIS AD-HOC: {symbol}*",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"• *Keputusan*: `{decision}`",
            f"• *Tingkat Keyakinan*: `{confidence * 100:.0f}%`",
            f"• *Skor Konfluensi*: `{confluence}`",
        ]

        if entry_price is not None:
            lines.append(f"• *Harga Acuan*: `{entry_price}`")
        if stop_loss is not None:
            lines.append(f"• *Stop Loss*: `{stop_loss}`")
        if take_profit is not None:
            lines.append(f"• *Take Profit*: `{take_profit}`")
        if rr_ratio is not None:
            lines.append(f"• *Risk : Reward*: `1 : {rr_ratio}`")

        lines.extend([
            f"",
            f"📑 *Tesis & Catatan Strategi*:",
            f"{rationale.strip()}",
        ])

        if bull_thesis or bear_thesis:
            lines.extend([
                f"",
                f"⚖️ *Debat Bull vs Bear (Divergensi: {divergence:.2f})*:",
            ])
            if bull_thesis:
                lines.append(f"🟢 *Bull*: {bull_thesis[:200].strip()}...")
            if bear_thesis:
                lines.append(f"🔴 *Bear*: {bear_thesis[:200].strip()}...")

        lines.append(f"\n_Analisis diproduksi secara otonom via LangGraph Isolated Pipeline._")
        return "\n".join(lines)
