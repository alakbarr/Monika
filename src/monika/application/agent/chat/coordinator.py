# ==============================================================================
# File: application/agent/chat/coordinator.py
# ==============================================================================

"""
Main ChatAgent coordinator combining modular domain mixins.
"""

from __future__ import annotations

import asyncio
import json
import re
from monika.infrastructure.database.models import ActivityLog
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple, Union

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.agent.chat_tool_router import ChatToolRouter
from monika.application.analysis.tools.tools_definitions import (
    OPERATOR_INTERACTIVE_TOOLS,
    PROPOSE_ACTION,
    SAVE_MARKET_INTELLIGENCE,
)
from monika.infrastructure.database.db import get_session
from monika.infrastructure.providers.llm_factory import get_client_for_task
from monika.application.agent.chat.base import _ChatAgentMixinBase, logger
from monika.application.agent.chat.constants import (
    TELEGRAM_MAX_CHARS,
    _sanitize_chat_format,
    _sanitize_telegram_format,
)
from monika.application.agent.chat.pending_actions import PendingAction
from monika.application.agent.chat.action_state import ActionStateMixin
from monika.application.agent.chat.action_execution import ActionExecutionMixin
from monika.application.agent.chat.prompt_builder import PromptBuilderMixin
from monika.application.agent.chat.streaming import StreamingMixin
from monika.application.agent.chat.tiers import ExecutionTiersMixin
from monika.application.agent.chat.history import HistoryMixin


class ChatAgent(
    ActionStateMixin,
    ActionExecutionMixin,
    PromptBuilderMixin,
    StreamingMixin,
    ExecutionTiersMixin,
    HistoryMixin,
):
    """
    Mengelola sesi percakapan dengan AI untuk user Telegram tertentu.
    Satu instance per user (disimpan di bot.py).
    """

    def __init__(
        self,
        settings: dict,
        user_id: int | str,
        is_admin: bool = False,
        interface: str = "telegram",
        execution_service: Optional[Any] = None,
    ):
        self.settings = settings
        self.user_id = user_id
        self.is_admin = is_admin
        self.interface = interface
        self.execution_service = execution_service

        is_cli = interface in ("cli", "interactive") or (
            isinstance(user_id, str) and (user_id.startswith("cli") or user_id == "api_client")
        )

        # Tier 1 (Lite / Fast): untuk query data cepat/sederhana
        role_lite = "chat_interactive_fast" if is_cli else "chat_telegram"
        self._client_lite = get_client_for_task(role_lite, settings)

        # Tier 2 (Medium / Balanced): untuk query menengah/eksekusi
        role_medium = "chat_interactive_balanced" if is_cli else "chat_telegram_medium"
        self._client_medium = get_client_for_task(role_medium, settings)

        # Tier 3 (Deep / Reasoning): untuk analisis mendalam/kompleks
        role_deep = "chat_interactive_reasoning" if is_cli else "chat_telegram_complex"
        self._client_deep = get_client_for_task(role_deep, settings)

        # Tier 4 (Deep Research / Pro): untuk ad-hoc deep research dan market intelligence
        role_research = "chat_interactive_pro" if is_cli else "deep_research"
        self._client_research = get_client_for_task(role_research, settings)

        # Client for quick intent tier routing (Jev System One sub-100ms)
        self._client_intent = get_client_for_task("jev_telegram_intent", settings)

        # Backward compatibility aliases
        self._gemini_lite = self._client_lite
        self._groq_medium = self._client_medium
        self._claude_sonnet = self._client_deep

        self._pending_actions: dict[str, PendingAction] = {}
        self._pending_charts: list[Any] = []
        self._pending_files: list[tuple[str, Any]] = []
        self.last_active: Optional[datetime] = None
        self._tool_router = ChatToolRouter(OPERATOR_INTERACTIVE_TOOLS)

        from monika.application.analysis.tools.tool_guardrails import ToolGuardrailController

        self.guardrail_controller = ToolGuardrailController(self.settings)

        # HIGH-3: Session-Level Tool Approval Gate (TTL 4h)
        self._session_approvals: dict[str, datetime] = {}
        self.SESSION_APPROVAL_TTL_HOURS: int = 4

        # M3: Denial Circuit Breaker
        self._consecutive_denials: int = 0
        self.DENIAL_BREAKER_THRESHOLD: int = 3
        self._proposals_paused: bool = False

        # 3-Tier Interruption State (steer, redirect, hard_cancel)
        self._active_task: Optional[asyncio.Task] = None
        self._interrupt_message: Optional[str] = None
        self._steer_queue: list[str] = []
        self._hard_cancelled: bool = False

        # Tool event listener for dashboard WebSocket streaming
        self.tool_event_listener: Optional[Any] = None
        self._last_turn_streamed: bool = False
        self._last_intercepted_pending: Optional[PendingAction] = None

        # Sticky Session Model Affinity (preserves KV cache across multi-turn dialogue)
        self._active_session_tier: Optional[str] = None
        self._active_session_model: Optional[str] = None

    async def reset(self, session_id: Optional[Union[str, int]] = None, hard_delete: bool = True) -> int:
        """
        Hard-resets current chat session:
        1. Purges conversation history from database & SessionDbWal.
        2. Clears all pending actions, charts, files, and session approvals.
        3. Clears denial breaker, steer queue, and sticky model affinity.
        """
        target_id = str(session_id) if session_id is not None else str(self.user_id)
        deleted_count = await self.reset_session(target_id, hard_delete=hard_delete)
        self.reset_state()
        logger.info(f"[ChatAgent] Hard reset complete for user/session '{target_id}' ({deleted_count} msgs deleted).")
        return deleted_count

    def reset_state(self) -> None:
        """Resets all in-memory operational state without dropping database history."""
        self._pending_actions.clear()
        self._pending_charts.clear()
        self._pending_files.clear()
        self._session_approvals.clear()
        self._consecutive_denials = 0
        self._proposals_paused = False
        self._steer_queue.clear()
        self._hard_cancelled = False
        self._active_session_tier = None
        self._active_session_model = None

    async def _resolve_tier_with_sticky(self, clean_message: str, preference: Optional[str] = "auto") -> str:
        """Resolves model tier respecting manual overrides, deep research intent, and sticky session affinity."""
        pref = preference or "auto"
        if pref != "auto":
            self._active_session_tier = pref
            return pref

        complexity = await self._classify_query_complexity(clean_message)
        if complexity == "deep_research":
            return "deep_research"

        is_sticky_enabled = self.settings.get("llm", {}).get("chat_sticky_model", True)
        if is_sticky_enabled and self._active_session_tier and self._active_session_tier != "deep_research":
            return self._active_session_tier

        resolved_tier = (
            "tier_lite" if complexity == "simple" else ("tier_medium" if complexity == "medium" else "tier_deep")
        )
        if is_sticky_enabled:
            self._active_session_tier = resolved_tier
        return resolved_tier

    def is_busy(self) -> bool:
        """Check if chat agent is currently processing a turn."""
        return self._active_task is not None and not self._active_task.done()

    def steer(self, guidance: str) -> str:
        """
        Tier 1 Interruption: Injects guidance into current active turn without aborting.
        Guidance is consumed before the next tool call / model turn.
        """
        self._steer_queue.append(guidance)
        logger.info(f"[ChatAgent] Steer guidance queued for user {self.user_id}: {guidance}")
        return f"Steer guidance registered: '{guidance}'. It will guide the next analytical step."

    def redirect(self, new_task: str) -> bool:
        """
        Tier 2 Interruption: Gracefully cancels the current ongoing turn and sets up redirect message.
        """
        if self._active_task and not self._active_task.done():
            self._interrupt_message = f"Redirected to: {new_task}"
            self._active_task.cancel()
            self._active_task = None
            logger.info(f"[ChatAgent] Turn redirected for user {self.user_id}: {new_task}")
            return True
        return False

    def hard_cancel(self) -> bool:
        """
        Tier 3 Interruption: Hard-aborts current turn, clears steer queue, and resets agent state.
        """
        self._hard_cancelled = True
        self._steer_queue.clear()
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            self._active_task = None
            logger.info(f"[ChatAgent] Hard cancel executed for user {self.user_id}.")
            return True
        return False

    def interrupt(self, redirect_message: str = "Turn interrupted by user") -> bool:
        """Backward compatibility: calls redirect."""
        return self.redirect(redirect_message)

    def pop_pending_charts(self) -> list[Any]:
        """Ambil dan bersihkan chart PNG buffer yang tertunda dikirim."""
        charts = list(self._pending_charts)
        self._pending_charts.clear()
        return charts

    def pop_pending_files(self) -> list[tuple[str, Any]]:
        """Ambil dan bersihkan file/dokumen yang tertunda dikirim ke user."""
        files = list(self._pending_files)
        self._pending_files.clear()
        return files

    async def handle(
        self,
        user_message: Union[str, Any],
        context: Optional[Any] = None,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
        session_id: Optional[str] = None,
        override_text: Optional[str] = None,
        stream: bool = False,
        update: Optional[Any] = None,
        token_callback: Optional[Any] = None,
        image_bytes: Optional[bytes] = None,
        **kwargs: Any,
    ) -> tuple[str, Optional[PendingAction]]:
        """Memproses pesan dari user dengan dukungan active turn interruption, topic isolation, dan token streaming."""
        self._active_task = asyncio.current_task()
        self.was_last_turn_streamed = False
        self._last_turn_streamed = False
        try:
            effective_update = update
            if not isinstance(user_message, str):
                effective_update = user_message
                text = override_text or (
                    effective_update.message.text
                    if hasattr(effective_update, "message")
                    and effective_update.message
                    and effective_update.message.text
                    else ""
                )
            else:
                text = override_text if override_text is not None else user_message

            # Stream response if requested and update is available, provided it is not an action query requiring ToolExecutor and interactive cards
            is_action_query = bool(
                re.search(
                    r"\b(close|tutup|modify|ubah|override|batalkan|cancel|adjust|geser|buy|beli|sell|jual|trade|eksekusi|pause|jeda|hentikan|stop|resume|lanjutkan|emergency|panic)\b",
                    text,
                    re.IGNORECASE,
                )
            )
            if (
                stream
                and not is_action_query
                and not image_bytes
                and effective_update
                and (hasattr(effective_update, "message") or hasattr(effective_update, "reply_text"))
            ):
                return await self._handle_streaming(
                    update=effective_update,
                    context=context,
                    user_message=text,
                    session_id=session_id,
                    typing_callback=typing_callback,
                    status_callback=status_callback,
                )

            if token_callback and not is_action_query and not image_bytes:
                return await self._handle_token_callback_stream(
                    user_message=text,
                    token_callback=token_callback,
                    session_id=session_id,
                    typing_callback=typing_callback,
                    status_callback=status_callback,
                )

            return await self._handle_internal(
                user_message=text,
                typing_callback=typing_callback,
                status_callback=status_callback,
                session_id=session_id,
                image_bytes=image_bytes,
            )
        except asyncio.CancelledError:
            interrupt_note = self._interrupt_message or "Turn was interrupted."
            self._interrupt_message = None
            logger.info(f"[ChatAgent] Turn interrupted for user {self.user_id}: {interrupt_note}")
            await self._close_durable_failed_turn(session_id=session_id, reason=interrupt_note)
            raise
        except Exception as unhandled_exc:
            from monika.application.agent.error_classifier import classify_api_error

            classified = classify_api_error(unhandled_exc)
            reason_str = classified.reason.value if classified.reason else "UNKNOWN"
            err_msg = f"Maaf, terjadi kendala teknis: {reason_str}. {classified.message}"
            logger.error(f"[ChatAgent] Unhandled turn exception: {unhandled_exc}", exc_info=True)
            await self._close_durable_failed_turn(session_id=session_id, reason=f"Error: {reason_str}")
            return f"[PERINGATAN] {err_msg}", None
        finally:
            self._active_task = None

    async def _handle_internal(
        self,
        user_message: str,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
        session_id: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Logika internal pemrosesan pesan dari user."""
        self._last_turn_streamed = False
        import re

        from monika.application.analysis.tools.tool_executor import ToolExecutor

        # Synchronize active MCP tools into ChatToolRouter
        await self._ensure_mcp_tools_synced()

        # Tentukan model
        preference = self._detect_model_preference(user_message)

        # Strip prefix jika ada manual override
        clean_message = user_message
        if preference == "deep_research":
            clean_message = re.sub(r"^/(research|pro)\s*", "", user_message, flags=re.IGNORECASE)
        elif preference in ("tier_lite", "gemini_lite"):
            preference = "tier_lite"
            clean_message = re.sub(r"^/(fast|quick|lite|tier1)\s+", "", user_message, flags=re.IGNORECASE)
        elif preference in ("tier_medium", "groq_medium"):
            preference = "tier_medium"
            clean_message = re.sub(r"^/(medium|mid|balanced|tier2)\s+", "", user_message, flags=re.IGNORECASE)
        elif preference in ("tier_deep", "claude_sonnet"):
            preference = "tier_deep"
            clean_message = re.sub(
                r"^/(analyze|analisis|deep|reasoning|complex|tier3)\s+", "", user_message, flags=re.IGNORECASE
            )

        if preference != "auto":
            self._active_session_tier = preference

        # Check hard cancel state
        if self._hard_cancelled:
            self._hard_cancelled = False
            return "[PERINGATAN] Sesi sebelumnya dibatalkan secara penuh (Hard Cancel).", None

        # Check and inject steer guidance if present
        if self._steer_queue:
            guidance_text = "\n".join(f"- {g}" for g in self._steer_queue)
            self._steer_queue.clear()
            clean_message = f"[OPERATOR STEERING GUIDANCE]:\n{guidance_text}\n\n{clean_message}"

        # Prompt injection safety pre-flight check
        try:
            from monika.core.security.prompt_injection_scanner import PromptInjectionScanner

            scan_res = PromptInjectionScanner.scan(clean_message, threshold=0.75)
            if not scan_res.is_safe:
                logger.warning(
                    f"[ChatAgent] Rejected hostile message from user {self.user_id}: {scan_res.rejection_reason}"
                )
                return (
                    f"[KEAMANAN] Pesan ditolak karena terdeteksi potensi prompt injection/adversarial jailbreak ({scan_res.rejection_reason}).",
                    None,
                )
            if scan_res.sanitized_text and scan_res.threat_score > 0.0:
                clean_message = scan_res.sanitized_text
        except Exception as scan_err:
            logger.debug(f"[ChatAgent] Prompt injection pre-flight non-fatal error: {scan_err}")

        # Auto-detect jika tidak ada manual preference
        if preference == "auto":
            # Check for direct conversational pause / resume command
            pause_match = re.search(
                r"\b(?:pause|jeda|hentikan\s+trading|stop\s+trading)\b", clean_message, re.IGNORECASE
            )
            resume_match = re.search(
                r"\b(?:resume|lanjutkan\s+trading|start\s+trading)\b", clean_message, re.IGNORECASE
            )
            if pause_match:
                pending = self._create_pending_action(
                    {
                        "action_type": "pause_trading",
                        "params": {"reason": "User requested pause via Telegram chat"},
                        "description": "Jeda (Pause) seluruh aktivitas trading dan order baru",
                    }
                )
                reply_text = "[PERINGATAN] *Konfirmasi Jeda Trading*\n\nApakah Anda yakin ingin menjeda (pause) seluruh aktivitas trading dan eksekusi order otomatis?"
                return reply_text, pending
            elif resume_match:
                pending = self._create_pending_action(
                    {
                        "action_type": "resume_trading",
                        "params": {},
                        "description": "Lanjutkan (Resume) aktivitas trading dan eksekusi order",
                    }
                )
                reply_text = (
                    "▶ *Konfirmasi Lanjutkan Trading*\n\nApakah Anda ingin melanjutkan (resume) aktivitas trading?"
                )
                return reply_text, pending

            # HIGH-1 & P5.1 (Q36): Check for ad-hoc / debate re-evaluation LangGraph pipeline trigger
            # Disambiguation: Conversational inquiries ("Bagaimana analisis XAUUSD hari ini?", "Gimana gold?")
            # must route to the conversational ChatAgent with 6-pillar SOP, NOT the automated pipeline.
            is_inquiry = bool(
                re.search(
                    r"\b(bagaimana|gimana|apa|apakah|menurutmu|ceritakan|pandanganmu|kenapa|tolong\s+jelaskan|adakah|review)\b",
                    clean_message,
                    re.IGNORECASE,
                )
                or clean_message.strip().endswith("?")
            )

            adhoc_match = None
            if not is_inquiry:
                adhoc_match = re.search(
                    r"\b(?:jalankan\s+pipeline|run\s+pipeline|eksekusi\s+pipeline|trigger\s+pipeline|analisis\s+ad-?hoc|analisa\s+ad-?hoc|tolong\s+analis[a|is]|analisis|analisa|analyze|bedah|setup|debat\s*ulang|ulangi\s*debat|re-?debate|evaluasi\s*ulang\s*debat|bandingkan|komparasi|bull\s*vs\s*bear)\s+([A-Za-z0-9,/_\s]{3,100})\b",
                    clean_message,
                    re.IGNORECASE,
                )
            if adhoc_match:
                candidate_str = adhoc_match.group(1).strip()
                import re as _re

                raw_syms = [
                    _re.sub(r"[^A-Z0-9]", "", s.upper()) for s in _re.split(r"[,;\s]+", candidate_str) if s.strip()
                ]
                configured_syms = set(
                    s.upper().replace("/", "") for s in self.settings.get("trading", {}).get("symbols", [])
                )
                KNOWN_ASSETS = {
                    "XAUUSD",
                    "EURUSD",
                    "GBPUSD",
                    "USDJPY",
                    "AUDUSD",
                    "USDCAD",
                    "USDCHF",
                    "NZDUSD",
                    "BTCUSD",
                    "ETHUSD",
                    "XTIUSD",
                    "XBRUSD",
                    "SOLUSD",
                } | configured_syms
                valid_syms = [s for s in raw_syms if s in KNOWN_ASSETS]
                if valid_syms:
                    is_debate_rerun = bool(
                        re.search(
                            r"\b(debat\s*ulang|ulangi\s*debat|re-?debate|evaluasi\s*ulang\s*debat|bandingkan|komparasi|bull\s*vs\s*bear)\b",
                            clean_message,
                            re.IGNORECASE,
                        )
                    )
                    from monika.application.agent.agent_loop import SystemAgentLoop

                    agent_loop = SystemAgentLoop(settings=self.settings)
                    action_desc = "Evaluasi debat ulang" if is_debate_rerun else "Ad-hoc LangGraph pipeline"
                    syms_label = ", ".join(valid_syms)
                    if status_callback:
                        try:
                            res = status_callback(f" Menjalankan {action_desc} untuk *{syms_label}*...")
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
                    adhoc_res = await agent_loop.execute_ad_hoc_analysis(
                        valid_syms if len(valid_syms) > 1 else valid_syms[0],
                        progress_callback=status_callback,
                        custom_context=f"DEBATE_RE_EVALUATION: {clean_message}" if is_debate_rerun else clean_message,
                    )
                    reply_text = adhoc_res.get("formatted_summary") or f"Analisis ad-hoc untuk {syms_label} selesai."
                    try:
                        async with get_session() as session:
                            await self._save_message(session, "user", clean_message, session_id=session_id)
                            await self._save_message(session, "assistant", reply_text, session_id=session_id)
                    except Exception as save_err:
                        logger.debug(f"[ChatAgent] Failed to save ad-hoc message to DB: {save_err}")
                    return f"{reply_text}\n\n_[SystemAgentLoop | LangGraph Isolated Pipeline]_", None

            self._last_intercepted_pending = None
            preference = await self._resolve_tier_with_sticky(clean_message, preference)

        client = (
            self._client_research
            if preference == "deep_research"
            else (
                self._client_lite
                if preference == "tier_lite"
                else (self._client_medium if preference == "tier_medium" else self._client_deep)
            )
        )
        model_name = getattr(client, "model_name", None) or getattr(client, "model", "AI")
        model_label = f"{model_name}"

        # Progress Heartbeat & Typing Loop (runs every 4 seconds during tool/LLM processing)
        heartbeat_task = None
        if typing_callback:

            async def _heartbeat_loop():
                try:
                    while True:
                        await asyncio.sleep(4.0)
                        try:
                            res = typing_callback()
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
                except asyncio.CancelledError:
                    pass

            heartbeat_task = asyncio.create_task(_heartbeat_loop())

        if preference == "deep_research" and status_callback:
            try:
                res = status_callback(" Memulai riset mendalam...")
                if asyncio.iscoroutine(res):
                    await res
            except Exception as _st_err:
                logger.debug(f"Failed to send deep research status: {_st_err}")

        try:
            async with get_session() as session:
                history = await self._load_history(session, session_id=session_id)
                db_message = (
                    re.sub(
                        r"<volatile_overlay>[\s\S]*?</volatile_overlay>\s*|<context_snapshot>[\s\S]*?</context_snapshot>\s*",
                        "",
                        clean_message,
                    ).strip()
                    or clean_message
                )
                await self._save_message(session, "user", db_message, session_id=session_id)
                system_prompt = await self._build_system_prompt(session)
                executor = ToolExecutor(session, settings=self.settings)
                executor.is_admin = getattr(self, "is_admin", False)
                self._instrument_executor(executor)

                if preference == "deep_research":
                    response = await self._run_tier_deep_research(
                        system_prompt, history, clean_message, tool_executor=executor, status_callback=status_callback
                    )
                elif preference == "tier_lite":
                    response = await self._run_tier_lite(
                        system_prompt, history, clean_message, tool_executor=executor, image_bytes=image_bytes
                    )
                elif preference == "tier_medium":
                    response = await self._run_tier_medium(
                        system_prompt, history, clean_message, tool_executor=executor, image_bytes=image_bytes
                    )
                else:
                    response = await self._run_tier_deep(
                        system_prompt, history, clean_message, tool_executor=executor, image_bytes=image_bytes
                    )

                if getattr(executor, "_pending_charts", None):
                    self._pending_charts.extend(executor._pending_charts.values())
                    executor._pending_charts.clear()
                if hasattr(executor, "pop_pending_files"):
                    self._pending_files.extend(executor.pop_pending_files())
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

        reply_text = response.get("reply", "Maaf, saya tidak dapat memproses permintaan ini.")
        reply_text = _sanitize_chat_format(reply_text)
        pending = None
        proposed_call = response.get("proposed_action")

        def _reply_makes_unfounded_price_claim(reply_text: str, tool_calls_made: int) -> bool:
            if tool_calls_made > 0:
                return False
            # Educational/glossary/hypothetical exemption
            edu_pattern = r"\b(contoh|misal|misalkan|ilustrasi|definisi|adalah|yaitu|kontrak standar|rumus|cara hitung|pengertian|maksudnya|sebagai acuan|standard lot|micro lot|cent)\b"
            if re.search(edu_pattern, reply_text, re.IGNORECASE) and not re.search(
                r"\b(live|posisi terbuka|saat ini|sekarang|running pnl|floating|real account)\b",
                reply_text,
                re.IGNORECASE,
            ):
                return False

            # Require specific symbol context or live claim to flag price claims
            symbol_pattern = (
                r"\b(XAUUSD|EURUSD|GBPUSD|USDJPY|BTCUSD|AUDUSD|USDCAD|USDCHF|NZDUSD|XTIUSD|XBRUSD|USTEC|NAS100|US30)\b"
            )
            has_symbol = bool(re.search(symbol_pattern, reply_text, re.IGNORECASE))

            live_claim_pattern = r"\b(saldo|equity|balance|floating|current price|harga sekarang|harga saat ini|posisi saya|open position)\b"
            has_live_claim = bool(re.search(live_claim_pattern, reply_text, re.IGNORECASE))

            if not (has_symbol or has_live_claim):
                # Pure conceptual explanation without concrete live market claim
                return False

            price_pattern = r"\b\d{1,3}(?:,\d{3})*(?:\.\d{1,5})?\b"
            keyword_pattern = (
                r"\b(SL|TP|entry|stop\s*loss|take\s*profit|harga|price|resistance|support|"
                r"pnl|p&l|profit|loss|lot|balance|equity|saldo|untung|rugi|margin)\b"
            )
            matches = re.findall(price_pattern, reply_text)
            has_meaningful_number = any(len(m.replace(",", "").replace(".", "")) >= 3 for m in matches)
            return has_meaningful_number and bool(re.search(keyword_pattern, reply_text, re.IGNORECASE))

        if _reply_makes_unfounded_price_claim(reply_text, response.get("tool_calls_made", 0)):
            logger.warning(
                "[ChatAgent] Unfounded price/PnL/status claim terdeteksi dengan 0 tool calls — memaksa retry grounded."
            )
            forced_prompt = (
                f"{clean_message}\n\n"
                "[SYSTEM MANDATE]: Your previous response cited specific numbers, prices, PnL, win rates, triggers, "
                "or account balances WITHOUT calling any data tools. You are STRICTLY REQUIRED to call the appropriate tool "
                "(e.g. get_paper_trading_performance, get_open_positions, get_trade_history, get_active_triggers, "
                "get_system_health, get_price_history, get_smc_zones, get_account_info, get_edge_tracker_status, get_chart, etc.) "
                "before citing any numbers. Re-answer completely grounded in fresh tool data, in Bahasa Indonesia. "
                "Do NOT include previous unrelated topics. Answer ONLY the specific question asked."
            )
            async with get_session() as retry_session:
                retry_executor = ToolExecutor(retry_session, settings=self.settings)
                retry_executor.is_admin = getattr(self, "is_admin", False)
                self._instrument_executor(retry_executor)
                if preference == "deep_research":
                    retry_response = await self._run_tier_deep_research(
                        system_prompt, history, forced_prompt, tool_executor=retry_executor
                    )
                elif preference == "tier_lite":
                    retry_response = await self._run_tier_lite(
                        system_prompt, history, forced_prompt, tool_executor=retry_executor
                    )
                elif preference == "tier_medium":
                    retry_response = await self._run_tier_medium(
                        system_prompt, history, forced_prompt, tool_executor=retry_executor
                    )
                else:
                    retry_response = await self._run_tier_deep(
                        system_prompt, history, forced_prompt, tool_executor=retry_executor
                    )

                if getattr(retry_executor, "_pending_charts", None):
                    self._pending_charts.extend(retry_executor._pending_charts.values())
                    retry_executor._pending_charts.clear()
                if hasattr(retry_executor, "pop_pending_files"):
                    self._pending_files.extend(retry_executor.pop_pending_files())

            if retry_response.get("tool_calls_made", 0) > 0:
                response = retry_response
                reply_text = _sanitize_chat_format(response.get("reply", reply_text))
                proposed_call = response.get("proposed_action")
            else:
                # Retry tetap tidak memanggil tool — jangan biarkan angka tanpa dasar sampai ke user.
                reply_text = (
                    "[Peringatan] Saya tidak dapat memberikan angka, PnL, harga, atau status spesifik tanpa memverifikasi "
                    "data real-time dari sistem. Silakan ulangi pertanyaan atau gunakan perintah langsung seperti /stats, /positions, atau /report."
                )
                proposed_call = None

        # Simpan teks bersih ke DB (tanpa footer metadata)
        async with get_session() as session:
            await self._save_message(session, "assistant", reply_text, session_id=session_id)

        # Format pesan tampilan dengan footer bersih tanpa emoji
        inp = response.get("input_tokens", 0)
        outp = response.get("output_tokens", 0)
        if inp > 0 or outp > 0:
            display_text = f"{reply_text}\n\n_[{model_label} | {inp} in, {outp} out]_"
        else:
            display_text = f"{reply_text}\n\n_[{model_label}]_"

        if proposed_call:
            pending = self._create_pending_action(proposed_call)
        elif getattr(self, "_last_intercepted_pending", None):
            pending = self._last_intercepted_pending
            self._last_intercepted_pending = None

        if pending:
            action_sym = str(pending.params.get("symbol") or "")
            # AGENTS.md Directive §1 Safety & Institutional Mandate:
            # Capital trade orders, system/OS mutations, and configurations NEVER auto-execute
            # under session approval. Every order mutation requires explicit single-use confirmation card.
            CAPITAL_AND_DANGEROUS_ACTIONS = {
                "place_order",
                "close_position",
                "close_positions_batch",
                "close_all_positions",
                "modify_sl_tp",
                "bulk_breakeven",
                "set_trailing_stop",
                "cancel_order",
                "cancel_stale_pending_orders",
                "close_paper_trade",
                "modify_paper_sl_tp",
                "partial_close_and_breakeven",
                "pause_trading",
                "resume_trading",
                "execute_terminal_command",
                "desktop_gui_action",
                "db_mutation",
                "mcp_write",
                "file_write",
                "update_config",
                "update_config_parameter",
                "restart_service",
                "restart_mt5_service",
            }
            can_auto_execute = (
                bool(action_sym)
                and self.is_symbol_session_approved(action_sym)
                and pending.action_type not in CAPITAL_AND_DANGEROUS_ACTIONS
            )
            if can_auto_execute:
                logger.info(f"[ChatAgent] Auto-executing session-approved action #{pending.action_id} for {action_sym}")
                try:
                    auto_res = await self._execute_action(pending)
                    display_text += f"\n\n[BERHASIL] *Auto-Executed (Session Approval Active for {action_sym.upper()})*:\n{auto_res}"
                    try:
                        async with get_session() as session:
                            session.add(
                                ActivityLog(
                                    category="trading",
                                    description=f"Telegram user {self.user_id} AUTO-EXECUTED (Session Approved): {pending.description} → {auto_res}",
                                    actor="telegram_chat_agent",
                                )
                            )
                            await session.commit()
                    except Exception as log_err:
                        logger.debug(f"[ChatAgent] Failed to log auto-execution to ActivityLog: {log_err}")
                except Exception as exec_err:
                    logger.error(f"[ChatAgent] Auto-execution failed for #{pending.action_id}: {exec_err}")
                    display_text += f"\n\n[GAGAL] *Auto-Execution Failed (Session Approval Active)*: {exec_err}"
                pending = None
            else:
                self._pending_actions[pending.action_id] = pending
                try:
                    asyncio.create_task(self._persist_pending_action(pending))
                except Exception:
                    pass

        return display_text, pending
