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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union

from monika.application.graph.workflow import build_trading_graph

logger = logging.getLogger("TradingAgent.Agent.SystemAgentLoop")


from monika.application.scheduler.adhoc_proxy import AdHocSchedulerProxy  # noqa: F401 (re-exported)


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
        symbol: Union[str, Sequence[str]],
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        custom_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mengeksekusi siklus analisis LangGraph ad-hoc terisolasi untuk satu atau beberapa simbol.

        Args:
            symbol: Simbol instrumen (misal 'XAUUSD', 'EURUSD, GBPUSD', atau ['EURUSD', 'BTCUSD']).
            progress_callback: Callback asinkron opsional untuk update progres ke chat.
            custom_context: Konteks instruksi tambahan dari user.

        Returns:
            Dict berisi detail keputusan, parameter trading, tesis debat, dan ringkasan teks.
        """
        from monika.application.agent.estop import is_estop_active

        if is_estop_active():
            raise RuntimeError("Emergency Stop (ESTOP) is active. Ad-hoc analysis execution blocked.")

        import re

        raw_tokens: List[str] = []
        if isinstance(symbol, str):
            raw_tokens = [s.strip() for s in re.split(r"[,;\s]+", symbol.strip()) if s.strip()]
        elif isinstance(symbol, (list, tuple, set)):
            raw_tokens = [str(s).strip() for s in symbol if str(s).strip()]

        cleaned_symbols: List[str] = []
        for t in raw_tokens:
            norm = self.normalize_symbol(t)
            if norm and norm not in cleaned_symbols:
                cleaned_symbols.append(norm)

        if not cleaned_symbols:
            return {"success": False, "error": "Simbol instrumen tidak valid atau kosong."}

        if len(cleaned_symbols) > 1:
            if progress_callback:
                try:
                    await progress_callback(
                        f" Memulai analisis ad-hoc paralel untuk {len(cleaned_symbols)} instrumen: *{', '.join(cleaned_symbols)}*..."
                    )
                except Exception:
                    pass

            results: Dict[str, Any] = {}
            summaries: List[str] = []
            for s in cleaned_symbols:
                sub_res = await self._execute_single_ad_hoc_analysis(
                    sym_clean=s,
                    progress_callback=progress_callback,
                    custom_context=custom_context,
                )
                results[s] = sub_res
                if sub_res.get("formatted_summary"):
                    summaries.append(sub_res["formatted_summary"])

            combined_summary = ("\n\n" + ("=" * 40) + "\n\n").join(summaries)
            return {
                "success": any(r.get("success", False) for r in results.values()),
                "is_multi_symbol": True,
                "symbols": cleaned_symbols,
                "results": results,
                "formatted_summary": combined_summary,
                "decisions": {s: r.get("decision", "WAIT") for s, r in results.items()},
            }

        return await self._execute_single_ad_hoc_analysis(
            sym_clean=cleaned_symbols[0],
            progress_callback=progress_callback,
            custom_context=custom_context,
        )

    async def _execute_single_ad_hoc_analysis(
        self,
        sym_clean: str,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        custom_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        cycle_id = f"adhoc_{sym_clean}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
        logger.info(f"[SystemAgentLoop] Starting ad-hoc LangGraph pipeline for {sym_clean} (cycle_id={cycle_id})")

        if progress_callback:
            try:
                await progress_callback(f" Memulai analisis ad-hoc LangGraph untuk *{sym_clean}*...")
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
                    await progress_callback(
                        f"[LAPORAN] Menjalankan pipeline multi-agent (Teknikal, Makro, Sentimen & Debat) untuk *{sym_clean}*..."
                    )
                except Exception:
                    pass

            async with asyncio.timeout(300.0):
                final_state = await graph.ainvoke(initial_state, config=config)

            # Ekstrak hasil per aset
            asset_analyses = final_state.get("asset_analyses", {})
            analysis = asset_analyses.get(sym_clean, {})
            debate_states = final_state.get("debate_states", {})
            debate = debate_states.get(sym_clean, {})
            investment_verdicts = final_state.get("investment_verdicts", {})
            verdict = investment_verdicts.get(sym_clean, {})

            decision = str(
                analysis.get("decision") or verdict.get("final_decision") or verdict.get("action") or "WAIT"
            ).upper()
            confidence = float(analysis.get("confidence") or 0.0)
            entry_price = analysis.get("entry_price") or analysis.get("current_price")
            stop_loss = analysis.get("stop_loss")
            take_profit = analysis.get("take_profit")
            confluence = analysis.get("confluence_score") or analysis.get("confluence", 0)
            rationale = analysis.get("rationale") or analysis.get("notes") or "Analisis ad-hoc selesai."

            # Ekstraksi thesis debat dengan fallback multi-kunci (P5.4 & Q36)
            bull_raw = (
                debate.get("verified_bull_claim")
                or debate.get("bull_thesis")
                or debate.get("bull_case")
                or debate.get("bull_arguments")
                or ""
            )
            if isinstance(bull_raw, dict):
                bull_thesis = (
                    bull_raw.get("thesis") or bull_raw.get("core_argument") or bull_raw.get("argument") or str(bull_raw)
                )
            else:
                bull_thesis = str(bull_raw) if bull_raw else ""

            bear_raw = (
                debate.get("bear_dissent")
                or debate.get("bear_thesis")
                or debate.get("bear_case")
                or debate.get("bear_arguments")
                or ""
            )
            if isinstance(bear_raw, dict):
                bear_thesis = (
                    bear_raw.get("dissent")
                    or bear_raw.get("core_argument")
                    or bear_raw.get("argument")
                    or str(bear_raw)
                )
            else:
                bear_thesis = str(bear_raw) if bear_raw else ""

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
                "formatted_summary": f"[GAGAL] Analisis ad-hoc untuk *{sym_clean}* mengalami kendala: {e}",
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
        confluence_display = f"{confluence}" if confluence is not None else "N/A (Belum Terbentuk)"
        decision_clean = decision.upper().strip()
        if decision_clean == "SKIP":
            decision_display = "WAIT (Setup Belum Memenuhi Kriteria)"
        elif decision_clean == "WAIT":
            decision_display = "WAIT (Stand Aside / Observasi)"
        else:
            decision_display = decision_clean

        lines = [
            f"[TARGET] *HASIL ANALISIS AD-HOC: {symbol}*",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"• *Keputusan*: `{decision_display}`",
            f"• *Tingkat Keyakinan*: `{confidence * 100:.0f}%`",
            f"• *Skor Konfluensi*: `{confluence_display}`",
        ]

        if entry_price is not None:
            lines.append(f"• *Harga Acuan*: `{entry_price}`")
        if stop_loss is not None:
            lines.append(f"• *Stop Loss*: `{stop_loss}`")
        if take_profit is not None:
            lines.append(f"• *Take Profit*: `{take_profit}`")
        if rr_ratio is not None:
            lines.append(f"• *Risk : Reward*: `1 : {rr_ratio}`")

        lines.extend(
            [
                f"",
                f" *Tesis & Catatan Strategi*:",
                f"{rationale.strip()}",
            ]
        )

        if bull_thesis or bear_thesis:
            lines.extend(
                [
                    f"",
                    f" *Debat Bull vs Bear (Divergensi: {divergence:.2f})*:",
                ]
            )
            if bull_thesis:
                lines.append(f"[AKTIF] *Bull*: {bull_thesis[:200].strip()}...")
            if bear_thesis:
                lines.append(f"[KRITIS] *Bear*: {bear_thesis[:200].strip()}...")

        lines.append(f"\n_Analisis diproduksi secara otonom via LangGraph Isolated Pipeline._")
        return "\n".join(lines)
