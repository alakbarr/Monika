# ==============================================================================
# File: telegram_bot/chat_agent.py
# ==============================================================================

"""
Chat Agent — Interface chat LLM via Telegram.

Konsep Inti:
1. LLM MEMBACA data via tools & MENGUSULKAN aksi, BUKAN mengeksekusi langsung.
2. Usulan aksi (buy/sell/close/pause) butuh konfirmasi user (inline keyboard).
3. Histori chat tersimpan di DB (telegram_conversations).
4. LLM punya akses ke TELEGRAM_TOOLS (read-only) & PROPOSE_ACTION.
5. Menampilkan indikator 'typing' saat LLM memproses.
6. Auto-split respons panjang (>4096 karakter) sesuai batas Telegram.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Union

try:
    from telegram.error import RetryAfter, BadRequest
except ImportError:
    class _FallbackRetryAfter(Exception):
        retry_after = 1.0
    class _FallbackBadRequest(Exception):
        pass
    RetryAfter = _FallbackRetryAfter  # type: ignore[assignment,misc]
    BadRequest = _FallbackBadRequest  # type: ignore[assignment,misc]

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import get_session
from database.models import TelegramConversation, ActivityLog, Position, RiskState, FundamentalBrief
from analysis.providers.llm_factory import get_client_for_task
from analysis.tools.tools_definitions import TELEGRAM_TOOLS, PROPOSE_ACTION, SAVE_MARKET_INTELLIGENCE
from telegram_bot.chat_tool_router import ChatToolRouter

logger = logging.getLogger("TradingAgent.ChatAgent")

# Telegram message character limit
TELEGRAM_MAX_CHARS    = 4096
HISTORY_WINDOW        = 50    # Max conversation turns to include in context (expanded for micro-compaction)
MAX_HISTORY_CHARS     = 8000  # Max total characters from history
SESSION_TIMEOUT_HOURS = 2     # Jeda >2 jam memutus rantai riwayat sesi lama


def _sanitize_telegram_format(text: str) -> str:
    """
    Sanitasi respon teks agar 100% kompatibel dengan Telegram Markdown:
    1. Konversi heading markdown (#, ##, ###, ####) menjadi *Judul* (Bold).
    2. Hapus seluruh karakter emoji / icon Unicode dekoratif.
    3. Hapus halusinasi footer model di badan teks.
    4. Bersihkan spasi dan baris kosong berlebih.
    """
    if not text:
        return text

    # 0. Saring blok thinking (<think>), context tags internal, dan rahasia
    try:
        from utils.streaming.stream_scrubber import StatefulStreamScrubber
        scrubber = StatefulStreamScrubber()
        text = scrubber.process_delta(text) + scrubber.flush()
    except Exception:
        pass
    
    # 1. Konversi heading markdown (#, ##, ###, ####) menjadi *Bold*
    text = re.sub(r'(?m)^#{1,6}\s*(.+?)\s*$', r'*\1*', text)
    
    # 2. Hapus emoji Unicode
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map
        "\U0001F700-\U0001F77F"  # Alchemical Symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols
        "\U0001FA00-\U0001FA6F"  # Chess / Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed Characters
        "\U00002600-\U000026FF"  # Miscellaneous Symbols
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)
    
    # 3. Bersihkan tag model yang mungkin dihalusinasikan oleh LLM di akhir teks
    text = re.sub(
        r'(?m)^\s*\[?_?(?:gemini|claude|deepseek|qwen|gpt|llama|groq|minimax|glm)[-\w\.:]*(?:\s*\|\s*\d+\s*in,\s*\d+\s*out)?_?\]?\s*$',
        '',
        text
    )
    
    # 4. Rapikan baris kosong berulang
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Proposed action (pending user confirmation)
# ---------------------------------------------------------------------------

class PendingAction:
    """Menyimpan usulan aksi yang menunggu konfirmasi user."""

    def __init__(self, action_id: str, action_type: str, params: dict, description: str):
        self.action_id   = action_id
        self.action_type = action_type   # "place_order" | "close_position" | "pause" | "resume"
        self.params      = params
        self.description = description
        self.created_at  = datetime.now(timezone.utc)
        self.expires_at  = self.created_at + timedelta(seconds=90)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "params": self.params,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingAction":
        obj = cls(
            action_id=d["action_id"],
            action_type=d["action_type"],
            params=d.get("params", {}),
            description=d.get("description", ""),
        )
        if "created_at" in d and d["created_at"]:
            try:
                obj.created_at = datetime.fromisoformat(d["created_at"])
            except Exception:
                pass
        if "expires_at" in d and d["expires_at"]:
            try:
                obj.expires_at = datetime.fromisoformat(d["expires_at"])
            except Exception:
                pass
        return obj


# ---------------------------------------------------------------------------
# Chat Agent
# ---------------------------------------------------------------------------

class ChatAgent:
    """
    Mengelola sesi percakapan dengan AI untuk user Telegram tertentu.
    Satu instance per user (disimpan di bot.py).
    """

    def __init__(self, settings: dict, user_id: int | str, is_admin: bool = False):
        self.settings = settings
        self.user_id = user_id
        self.is_admin = is_admin
        
        # Tier 1 (Lite): untuk query data cepat/sederhana
        self._client_lite = get_client_for_task("chat_telegram", settings)
        
        # Tier 2 (Medium): untuk query menengah/eksekusi
        self._client_medium = get_client_for_task("chat_telegram_medium", settings)
        
        # Tier 3 (Deep): untuk analisis mendalam/kompleks
        self._client_deep = get_client_for_task("chat_telegram_complex", settings)

        # Tier 4 (Deep Research): untuk ad-hoc deep research dan market intelligence
        self._client_research = get_client_for_task("deep_research", settings)

        # Client for quick intent tier routing
        self._client_intent = self._client_lite

        # Backward compatibility aliases
        self._gemini_lite = self._client_lite
        self._groq_medium = self._client_medium
        self._claude_sonnet = self._client_deep
        
        self._pending_actions: dict[str, PendingAction] = {}
        self._pending_charts: list[Any] = []
        self.last_active: Optional[datetime] = None
        self._tool_router = ChatToolRouter(TELEGRAM_TOOLS)

        from analysis.tools.tool_guardrails import ToolGuardrailController
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

    def set_tool_event_listener(self, listener: Optional[Any]):
        """Register a callback for tool events ('start' and 'result')."""
        self.tool_event_listener = listener

    def _instrument_executor(self, executor: Any):
        """Wrap ToolExecutor.execute to notify tool_event_listener if set."""
        if not self.tool_event_listener:
            return
        orig_exec = executor.execute
        listener = self.tool_event_listener

        async def _wrapped_exec(tool_name: str, tool_input: dict) -> Any:
            try:
                cb = listener("start", {"tool": tool_name, "input": tool_input})
                if asyncio.iscoroutine(cb):
                    await cb
            except Exception as e:
                logger.debug(f"[ChatAgent] Error in tool listener start: {e}")

            res = await orig_exec(tool_name, tool_input)

            try:
                summary = str(res)
                if len(summary) > 120:
                    summary = summary[:120] + "..."
                cb = listener("result", {"tool": tool_name, "summary": summary, "result": res})
                if asyncio.iscoroutine(cb):
                    await cb
            except Exception as e:
                logger.debug(f"[ChatAgent] Error in tool listener result: {e}")

            return res

        executor.execute = _wrapped_exec

    def is_symbol_session_approved(self, symbol: str) -> bool:
        """Periksa apakah simbol memiliki izin approval aktif pada level sesi."""
        if not symbol:
            return False
        sym_clean = symbol.strip().upper().replace("/", "")
        expiry = self._session_approvals.get(sym_clean)
        if expiry is None:
            return False
        if datetime.now(timezone.utc) > expiry:
            del self._session_approvals[sym_clean]
            return False
        return True

    def add_session_approval(self, symbol: str) -> datetime:
        """Berikan izin sesi berdurasi 4 jam untuk simbol tertentu."""
        sym_clean = symbol.strip().upper().replace("/", "")
        expiry = datetime.now(timezone.utc) + timedelta(hours=self.SESSION_APPROVAL_TTL_HOURS)
        self._session_approvals[sym_clean] = expiry
        logger.info(
            f"[ChatAgent] Session approval granted for {sym_clean} "
            f"until {expiry.isoformat()} (TTL: {self.SESSION_APPROVAL_TTL_HOURS}h)"
        )
        return expiry

    async def _persist_pending_action(self, action: PendingAction):
        """Save pending action to SystemConfig table in DB."""
        try:
            from database.models import SystemConfig
            async with get_session() as session:
                await SystemConfig.upsert(
                    session,
                    key=f"pending_action:{action.action_id}",
                    value=json.dumps(action.to_dict()),
                    description=f"Telegram pending action: {action.action_type}"
                )
                await session.commit()
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not persist pending action {action.action_id}: {e}")

    async def _delete_persisted_pending_action(self, action_id: str):
        """Remove persisted pending action from SystemConfig table."""
        try:
            from database.models import SystemConfig
            from sqlalchemy import delete
            async with get_session() as session:
                await session.execute(
                    delete(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}")
                )
                await session.commit()
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not delete persisted pending action {action_id}: {e}")

    async def get_pending_action(self, action_id: str) -> Optional[PendingAction]:
        """Fetch pending action from memory or restore from DB."""
        action = self._pending_actions.get(action_id)
        if action:
            return action
        try:
            from database.models import SystemConfig
            from sqlalchemy import select, delete
            async with get_session() as session:
                cfg = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}")
                )).scalar_one_or_none()
                if cfg and cfg.value:
                    data = json.loads(cfg.value)
                    restored = PendingAction.from_dict(data)
                    if not restored.is_expired():
                        self._pending_actions[action_id] = restored
                        return restored
                    else:
                        await session.execute(
                            delete(SystemConfig).where(SystemConfig.key == f"pending_action:{action_id}")
                        )
                        await session.commit()
        except Exception as e:
            logger.debug(f"[ChatAgent] Could not restore pending action {action_id}: {e}")
        return None

    async def approve_for_session(self, action_id: str) -> tuple[bool, str]:
        """Eksekusi aksi dan aktifkan approval berdurasi 4 jam untuk simbol yang diajukan."""
        action = await self.get_pending_action(action_id)
        if not action:
            return False, "Action not found or already processed."
        symbol = str(action.params.get("symbol") or "")
        if symbol:
            self.add_session_approval(symbol)
        success, msg = await self.confirm_action(action_id)
        if success and symbol:
            msg += (
                f"\n\n🔐 *Izin Sesi Aktif*: Proposal trading untuk `{symbol.upper()}` "
                f"diizinkan otomatis selama {self.SESSION_APPROVAL_TTL_HOURS} jam ke depan."
            )
        return success, msg

    def is_proposals_paused(self) -> bool:
        """Check if trading action proposals are currently paused by denial circuit breaker."""
        return self._proposals_paused

    def is_busy(self) -> bool:
        """Check if chat agent is currently processing a turn."""
        return self._active_task is not None and not self._active_task.done()

    def record_denial(self) -> tuple[bool, str]:
        """Record a denial; if consecutive denials reach threshold, trip circuit breaker."""
        self._consecutive_denials += 1
        if self._consecutive_denials >= self.DENIAL_BREAKER_THRESHOLD:
            self._proposals_paused = True
            return True, "Circuit breaker triggered: 3 consecutive denials. Auto-proposals paused."
        return False, f"Denial recorded ({self._consecutive_denials}/{self.DENIAL_BREAKER_THRESHOLD})."

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

    def resume_proposals(self) -> str:
        """Reset denial circuit breaker and re-enable action proposals."""
        self._consecutive_denials = 0
        self._proposals_paused = False
        return "Auto-proposals resumed. Agent may propose trading actions again."


    def pop_pending_charts(self) -> list[Any]:
        """Ambil dan bersihkan chart PNG buffer yang tertunda dikirim."""
        charts = list(self._pending_charts)
        self._pending_charts.clear()
        return charts

    def _detect_model_preference(self, msg: str) -> str:
        """Returns: 'tier_lite', 'tier_medium', 'tier_deep', 'deep_research', atau 'auto'"""
        import re
        msg_lower = msg.lower().strip()
        
        # Manual override via prefix
        if re.match(r'^/research\b', msg_lower):
            return 'deep_research'
        if re.match(r'^/(fast|quick)\b', msg_lower):
            return 'tier_lite'
        if re.match(r'^/(medium|mid)\b', msg_lower):
            return 'groq_medium'
        if re.match(r'^/(analyze|analisis)\b', msg_lower):
            return 'claude_sonnet'
        
        return 'auto'

    def _is_macro_event_query(self, text: str) -> bool:
        """Deteksi apakah kueri memerlukan analisis mendalam probabilitas event makro/bank sentral."""
        if not text or not isinstance(text, str):
            return False
        import re
        msg_lower = text.lower().strip()

        # Compound self-sufficient triggers that inherently signify macro event / probability analysis
        compound_triggers = (
            r'\b(market\s*surprise|kejutan\s*pasar|keputusan\s*(?:suku\s*)?bunga|rate\s*decision)\b'
        )
        if re.search(compound_triggers, msg_lower):
            return True

        # Macro event entities and central bank concepts
        macro_event_patterns = (
            r'\b(fedwatch|cme\s*fedwatch|cme|fomc|(?:the\s+)?fed\b|'
            r'fed\s*(?:hike|cut|hold|pause|pivot|decision)|'
            r'suku\s*bunga|interest\s*rate|'
            r'rate\s*(?:hike|cut|hold|decision)|keputusan\s*(?:bunga|rate|suku\s*bunga)|'
            r'bank\s*sentral|central\s*bank|press\s*conference|presser|konferensi\s*pers|'
            r'dot\s*plot|sep\b|kebijakan\s*moneter|monetary\s*policy|'
            r'greenspan|alan\s*greenspan|bernanke|ben\s*bernanke|yellen|janet\s*yellen|'
            r'warsh|kevin\s*warsh|powell|jerome\s*powell|lagarde|ueda|bailey|ecb|boj|boe|'
            r'taper|tapering|no-taper|quantitative\s*easing|qe\b|'
            r'kejutan\s*pasar|market\s*surprise|searah\s*dengan\s*harapan|mengecoh\s*pasar)\b'
        )
        # Macro analytical / probability intent
        macro_intent_patterns = (
            r'\b(peluang|kemungkinan|probabilitas|probability|odds|prospek|proyeksi|'
            r'prediksi|outlook|preview|forecast|skenario|scenario|analisis|analisa|analysis|'
            r'komprehensif|comprehensive|hawkish|dovish|hike|cut|hold|history|historis|'
            r'precedent|preseden|dampak|impact|reaksi|reaction|'
            r'surprise|kejutan|keputusan|decision)\b'
        )
        return bool(re.search(macro_event_patterns, msg_lower) and re.search(macro_intent_patterns, msg_lower))

    def _inject_macro_playbooks(self, system_prompt: Union[str, tuple[str, str]]) -> Union[str, tuple[str, str]]:
        """Inject event_probability_playbook and market_dynamics_framework into system prompt."""
        from skills.loader import load_skill

        playbook_sections: list[str] = []
        try:
            event_playbook = load_skill("event_probability_playbook")
            if event_playbook:
                playbook_sections.append(f"## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK\n{event_playbook}")
        except Exception as e:
            logger.warning(f"[ChatAgent] Failed to load event_probability_playbook: {e}")

        try:
            cb_framework = load_skill("central_banks_framework")
            if cb_framework:
                playbook_sections.append(f"## AUTHORITATIVE CENTRAL BANKS FRAMEWORK\n{cb_framework}")
        except Exception as e:
            logger.warning(f"[ChatAgent] Failed to load central_banks_framework: {e}")

        try:
            market_dynamics = load_skill("market_dynamics_framework")
            if market_dynamics:
                playbook_sections.append(f"## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK\n{market_dynamics}")
        except Exception as e:
            logger.warning(f"[ChatAgent] Failed to load market_dynamics_framework: {e}")

        if not playbook_sections:
            return system_prompt

        injected_block = "\n\n---\n\n" + "\n\n---\n\n".join(playbook_sections)

        if isinstance(system_prompt, tuple):
            static_prompt, dynamic_snapshot = system_prompt
            if "AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in static_prompt:
                return system_prompt
            return (f"{static_prompt}{injected_block}", dynamic_snapshot)

        if "AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in system_prompt:
            return system_prompt
        return f"{system_prompt}{injected_block}"

    async def _classify_query_complexity(self, msg: str) -> str:
        """Use heuristics to classify query complexity reliably."""
        if not msg or not isinstance(msg, str) or not msg.strip():
            return 'simple'

        import re
        msg_lower = msg.lower().strip()

        # Ad-hoc Deep Research & Market Intelligence patterns (highest priority)
        RESEARCH_PATTERNS = r'\b(deep-research|deep\s*research|riset\s*mendalam|investigasi\s*pasar|konsensus|whisper|saturasi\s*posisi|skenario\s*hit/miss|pre-event|bedah\s*peristiwa)\b'
        if re.search(RESEARCH_PATTERNS, msg_lower):
            return 'deep_research'

        # Macro Event & Central Bank Probability patterns (Deep Research)
        if self._is_macro_event_query(msg_lower):
            return 'deep_research'

        # Action verbs always require complex / medium deep reasoning
        ACTION_VERBS = r'\b(close|tutup|modify|ubah|override|batalkan|cancel|adjust|geser)\b'
        if re.search(ACTION_VERBS, msg_lower):
            return 'complex'

        # Super short greetings/thanks
        if len(msg) < 15 and any(w in msg_lower for w in ['halo', 'hai', 'hi', 'hello', 'tes', 'ping', 'makasih', 'terima kasih', 'thanks', 'ok', 'siap']):
            return 'simple'
            
        # Exact match or starts with a simple command (even if > 200 chars)
        if re.match(r'^(status|posisi|positions|vix|balance|equity|pnl|drawdown|stats|performa|triggers?|history|riwayat|health|kesehatan|biaya|token)\b', msg_lower):
            return 'simple'

        if len(msg) > 300:
            return 'complex'

        # Jev System One Intent & Model Tier Routing
        try:
            from utils.typesafe.jev_primitives import build_telegram_intent_questions
            jev_client = getattr(self, "_client_intent", None) or self._client_lite
            if hasattr(jev_client, "classify_json"):
                jev_res = await jev_client.classify_json(
                    prompt="",
                    state={"user_message": msg[:500]},
                    jev_questions=build_telegram_intent_questions(),
                    timeout=2.0
                )
                if jev_res and isinstance(jev_res, dict):
                    tier = jev_res.get("model_tier")
                    choice_val = tier.get("choice") if isinstance(tier, dict) else tier
                    tier_str = str(choice_val or "").lower()
                    if tier_str in ("none", "light"):
                        return "simple"
                    elif tier_str == "medium":
                        return "medium"
                    elif tier_str == "heavy":
                        return "complex"
        except Exception as jev_intent_err:
            logger.debug(f"[ChatAgent] Jev intent routing fallback to heuristics: {jev_intent_err}")

        if len(msg) > 150:
            return 'medium'
        
        # Common simple patterns
        if re.search(r'\b(berapa|cek|tampilkan|lihat|ada apa)\b.*\b(saldo|vix|pnl|profit|loss|posisi|positions?|paper|win rate|triggers?|kesehatan|health|biaya|tokens?|histori|riwayat|chart|grafik)\b', msg_lower):
            return 'simple'
            
        # Common complex patterns
        if re.search(r'\b(kenapa|mengapa|analisa|evaluasi|analisis|review|bagaimana|setup|entry|prediksi|prospek)\b', msg_lower):
            return 'complex'
            
        # Common medium patterns
        if re.search(r'\b(berita|news|ringkasan|summary|apa|kapan|jadwal)\b', msg_lower):
            return 'medium'
        
        return 'medium'

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
        **kwargs: Any,
    ) -> tuple[str, Optional[PendingAction]]:
        """Memproses pesan dari user dengan dukungan active turn interruption, topic isolation, dan token streaming."""
        self._active_task = asyncio.current_task()
        try:
            effective_update = update
            if not isinstance(user_message, str):
                effective_update = user_message
                text = override_text or (
                    effective_update.message.text
                    if hasattr(effective_update, "message") and effective_update.message and effective_update.message.text
                    else ""
                )
            else:
                text = override_text if override_text is not None else user_message

            # Stream response if requested and update is available, provided it is not an action query requiring ToolExecutor and interactive cards
            is_action_query = bool(re.search(r'\b(close|tutup|modify|ubah|override|batalkan|cancel|adjust|geser|buy|beli|sell|jual|trade|eksekusi)\b', text, re.IGNORECASE))
            if stream and not is_action_query and effective_update and (hasattr(effective_update, "message") or hasattr(effective_update, "reply_text")):
                return await self._handle_streaming(
                    update=effective_update,
                    context=context,
                    user_message=text,
                    session_id=session_id,
                    typing_callback=typing_callback,
                    status_callback=status_callback,
                )

            return await self._handle_internal(
                user_message=text,
                typing_callback=typing_callback,
                status_callback=status_callback,
                session_id=session_id,
            )
        except asyncio.CancelledError:
            interrupt_note = self._interrupt_message or "Turn was interrupted."
            self._interrupt_message = None
            logger.info(f"[ChatAgent] Turn interrupted for user {self.user_id}: {interrupt_note}")
            return f"⚠️ {interrupt_note}", None
        finally:
            self._active_task = None

    async def _handle_streaming(
        self,
        update: Any,
        context: Any,
        user_message: str,
        session_id: Optional[str] = None,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Handle chat turn with real-time token streaming via edit_message_text."""
        async with get_session() as session:
            history = await self._load_history(session, session_id=session_id)
            await self._save_message(session, "user", user_message, session_id=session_id)
            system_prompt = await self._build_system_prompt(session)

            preference = self._detect_model_preference(user_message)
            clean_message = user_message
            if preference == 'deep_research':
                clean_message = re.sub(r'^/research\s*', '', user_message, flags=re.IGNORECASE)
            elif preference in ('tier_lite', 'gemini_lite'):
                preference = 'tier_lite'
                clean_message = re.sub(r'^/(fast|quick)\s+', '', user_message, flags=re.IGNORECASE)
            elif preference in ('tier_medium', 'groq_medium'):
                preference = 'tier_medium'
                clean_message = re.sub(r'^/(medium|mid)\s+', '', user_message, flags=re.IGNORECASE)
            elif preference in ('tier_deep', 'claude_sonnet'):
                preference = 'tier_deep'
                clean_message = re.sub(r'^/(analyze|analisis)\s+', '', user_message, flags=re.IGNORECASE)

            if preference == 'auto':
                complexity = await self._classify_query_complexity(clean_message)
                if complexity == 'deep_research':
                    preference = 'deep_research'
                elif complexity == 'complex':
                    preference = 'tier_deep'
                else:
                    preference = 'tier_lite'

            if preference == 'deep_research':
                return await self._handle_internal(
                    user_message=clean_message,
                    session_id=session_id,
                    typing_callback=typing_callback,
                    status_callback=status_callback,
                )

            if self._is_macro_event_query(clean_message):
                system_prompt = self._inject_macro_playbooks(system_prompt)

            if preference in ("tier_deep", "claude_sonnet"):
                generator = await self._run_with_claude(
                    system_prompt, history, clean_message, stream=True
                )
            else:
                generator = await self._run_with_gemini(
                    system_prompt, history, clean_message, stream=True
                )

            final_text = await self._stream_response(update, context, generator)
            await self._save_message(session, "assistant", final_text, session_id=session_id)
            return final_text, None

    async def _stream_response(
        self,
        update: Any,
        context: Any,
        response_generator: Any,
    ) -> str:
        """Stream LLM tokens via Telegram edit_message_text.
 
        Enforces prefix-stability (frame N is strict prefix of N+1).
        Throttle edits to max 1 every 500ms to respect Telegram rate limits.
        Final message removes streaming cursor and applies full HTML sanitization.
        """
        import time
        from telegram_bot.sanitizer import sanitize_telegram_html

        message = None
        if hasattr(update, "message") and update.message:
            message = await update.message.reply_text("⏳ Thinking...")
        elif hasattr(update, "reply_text"):
            message = await update.reply_text("⏳ Thinking...")

        buffer = ""
        last_edit = 0.0

        async for delta in response_generator:
            text_chunk = delta if isinstance(delta, str) else getattr(delta, "text", str(delta))
            buffer += text_chunk
            now = time.monotonic()
            if now - last_edit >= 0.5 and len(buffer) > 20:
                if message:
                    try:
                        cursor_text = _sanitize_telegram_format(buffer) + " ▌"
                        display = sanitize_telegram_html(cursor_text)
                        if len(display) <= 4096:
                            await message.edit_text(display, parse_mode="HTML")
                            last_edit = now
                    except RetryAfter as e:
                        await asyncio.sleep(getattr(e, "retry_after", 1.0))
                    except BadRequest:
                        pass
                    except Exception as e:
                        logger.debug(f"[ChatAgent] Stream edit error: {e}")

        # Final message: remove cursor, apply full HTML sanitization
        final_clean = _sanitize_telegram_format(buffer)
        if not final_clean.strip():
            final_clean = "⚠️ Tidak ada respons yang dihasilkan."

        final = sanitize_telegram_html(final_clean)
        if message:
            if len(final) <= 4096:
                try:
                    await message.edit_text(final, parse_mode="HTML")
                except Exception:
                    try:
                        await message.edit_text(final_clean)
                    except Exception as e:
                        logger.debug(f"[ChatAgent] Final stream edit error: {e}")
            else:
                chunks = [final_clean[i:i + 4000] for i in range(0, len(final_clean), 4000)]
                first_chunk = chunks[0] if chunks else final_clean[:4000]
                first_html = sanitize_telegram_html(first_chunk)
                try:
                    await message.edit_text(first_html, parse_mode="HTML")
                except Exception:
                    await message.edit_text(first_chunk)

                if len(chunks) > 1 and hasattr(update, "message") and update.message:
                    for rem_chunk in chunks[1:]:
                        rem_html = sanitize_telegram_html(rem_chunk)
                        try:
                            await update.message.reply_text(rem_html, parse_mode="HTML")
                        except Exception:
                            await update.message.reply_text(rem_chunk)

        return buffer

    async def _handle_internal(
        self,
        user_message: str,
        typing_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Logika internal pemrosesan pesan dari user."""
        import re
        from analysis.tools.tool_executor import ToolExecutor
        
        # Tentukan model
        preference = self._detect_model_preference(user_message)
        
        # Strip prefix jika ada manual override
        clean_message = user_message
        if preference == 'deep_research':
            clean_message = re.sub(r'^/research\s*', '', user_message, flags=re.IGNORECASE)
        elif preference in ('tier_lite', 'gemini_lite'):
            preference = 'tier_lite'
            clean_message = re.sub(r'^/(fast|quick)\s+', '', user_message, flags=re.IGNORECASE)
        elif preference in ('tier_medium', 'groq_medium'):
            preference = 'tier_medium'
            clean_message = re.sub(r'^/(medium|mid)\s+', '', user_message, flags=re.IGNORECASE)
        elif preference in ('tier_deep', 'claude_sonnet'):
            preference = 'tier_deep'
            clean_message = re.sub(r'^/(analyze|analisis)\s+', '', user_message, flags=re.IGNORECASE)

        # Check hard cancel state
        if self._hard_cancelled:
            self._hard_cancelled = False
            return "⚠️ Sesi sebelumnya dibatalkan secara penuh (Hard Cancel).", None

        # Check and inject steer guidance if present
        if self._steer_queue:
            guidance_text = "\n".join(f"- {g}" for g in self._steer_queue)
            self._steer_queue.clear()
            clean_message = f"[OPERATOR STEERING GUIDANCE]:\n{guidance_text}\n\n{clean_message}"
        
        # Auto-detect jika tidak ada manual preference
        if preference == 'auto':
            # HIGH-1 & HIGH-8: Check for ad-hoc single-asset LangGraph pipeline trigger
            adhoc_match = re.search(
                r'\b(?:analisis|analisa|analyze|bedah|setup)\s+([A-Za-z]{3,6}(?:/[A-Za-z]{3})?)\b',
                clean_message,
                re.IGNORECASE,
            )
            if adhoc_match:
                candidate_sym = adhoc_match.group(1).upper().replace('/', '')
                configured_syms = set(
                    s.upper().replace('/', '') for s in self.settings.get("trading", {}).get("symbols", [])
                )
                KNOWN_ASSETS = {
                    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
                    "USDCAD", "USDCHF", "NZDUSD", "BTCUSD", "ETHUSD",
                    "XTIUSD", "XBRUSD", "SOLUSD"
                } | configured_syms
                if candidate_sym in KNOWN_ASSETS:
                    from agent.agent_loop import SystemAgentLoop
                    agent_loop = SystemAgentLoop(settings=self.settings)
                    if status_callback:
                        try:
                            res = status_callback(f"🔬 Menjalankan ad-hoc LangGraph pipeline untuk {candidate_sym}...")
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
                    adhoc_res = await agent_loop.execute_ad_hoc_analysis(
                        candidate_sym,
                        progress_callback=status_callback,
                        custom_context=clean_message,
                    )
                    reply_text = adhoc_res.get("formatted_summary") or f"Analisis ad-hoc untuk {candidate_sym} selesai."
                    try:
                        async with get_session() as session:
                            await self._save_message(session, "user", clean_message, session_id=session_id)
                            await self._save_message(session, "assistant", reply_text, session_id=session_id)
                    except Exception as save_err:
                        logger.debug(f"[ChatAgent] Failed to save ad-hoc message to DB: {save_err}")
                    return f"{reply_text}\n\n_[SystemAgentLoop | LangGraph Isolated Pipeline]_", None

            complexity = await self._classify_query_complexity(clean_message)
            if complexity == 'deep_research':
                preference = 'deep_research'
            elif complexity == 'simple':
                preference = 'tier_lite'
            elif complexity == 'medium':
                preference = 'tier_medium'
            else:
                preference = 'tier_deep'
        
        client = (
            self._client_research if preference == 'deep_research'
            else (self._client_lite if preference == 'tier_lite'
            else (self._client_medium if preference == 'tier_medium' else self._client_deep))
        )
        model_name = getattr(client, 'model_name', None) or getattr(client, 'model', 'AI')
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

        if preference == 'deep_research' and status_callback:
            try:
                res = status_callback("🔍 Memulai riset mendalam...")
                if asyncio.iscoroutine(res):
                    await res
            except Exception as _st_err:
                logger.debug(f"Failed to send deep research status: {_st_err}")

        try:
            async with get_session() as session:
                history = await self._load_history(session, session_id=session_id)
                await self._save_message(session, "user", clean_message, session_id=session_id)
                system_prompt = await self._build_system_prompt(session)
                executor = ToolExecutor(session, settings=self.settings)
                executor.is_admin = getattr(self, "is_admin", False)
                self._instrument_executor(executor)
                
                if preference == 'deep_research':
                    response = await self._run_tier_deep_research(system_prompt, history, clean_message, tool_executor=executor, status_callback=status_callback)
                elif preference == 'tier_lite':
                    response = await self._run_tier_lite(system_prompt, history, clean_message, tool_executor=executor)
                elif preference == 'tier_medium':
                    response = await self._run_tier_medium(system_prompt, history, clean_message, tool_executor=executor)
                else:
                    response = await self._run_tier_deep(system_prompt, history, clean_message, tool_executor=executor)

                if getattr(executor, '_pending_charts', None):
                    self._pending_charts.extend(executor._pending_charts.values())
                    executor._pending_charts.clear()
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

        reply_text    = response.get("reply", "Maaf, saya tidak dapat memproses permintaan ini.")
        reply_text    = _sanitize_telegram_format(reply_text)
        pending       = None
        proposed_call = response.get("proposed_action")
        
        def _reply_makes_unfounded_price_claim(reply_text: str, tool_calls_made: int) -> bool:
            if tool_calls_made > 0:
                return False
            price_pattern = r'\b\d{1,3}(?:,\d{3})*(?:\.\d{1,5})?\b'
            keyword_pattern = (
                r'\b(SL|TP|entry|stop\s*loss|take\s*profit|harga|price|resistance|support|'
                r'pnl|p&l|profit|loss|lot|balance|equity|saldo|untung|rugi|margin)\b'
            )
            matches = re.findall(price_pattern, reply_text)
            has_meaningful_number = any(len(m.replace(',', '').replace('.', '')) >= 3 for m in matches)
            return has_meaningful_number and bool(re.search(keyword_pattern, reply_text, re.IGNORECASE))

        if _reply_makes_unfounded_price_claim(reply_text, response.get('tool_calls_made', 0)):
            logger.warning('[ChatAgent] Unfounded price/PnL/status claim terdeteksi dengan 0 tool calls — memaksa retry grounded.')
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
                if preference == 'deep_research':
                    retry_response = await self._run_tier_deep_research(system_prompt, history, forced_prompt, tool_executor=retry_executor)
                elif preference == 'tier_lite':
                    retry_response = await self._run_tier_lite(system_prompt, history, forced_prompt, tool_executor=retry_executor)
                elif preference == 'tier_medium':
                    retry_response = await self._run_tier_medium(system_prompt, history, forced_prompt, tool_executor=retry_executor)
                else:
                    retry_response = await self._run_tier_deep(system_prompt, history, forced_prompt, tool_executor=retry_executor)

                if getattr(retry_executor, '_pending_charts', None):
                    self._pending_charts.extend(retry_executor._pending_charts.values())
                    retry_executor._pending_charts.clear()

            if retry_response.get('tool_calls_made', 0) > 0:
                response = retry_response
                reply_text = _sanitize_telegram_format(response.get('reply', reply_text))
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
            if pending:
                action_sym = str(pending.params.get("symbol") or "")
                if action_sym and self.is_symbol_session_approved(action_sym):
                    logger.info(f"[ChatAgent] Auto-executing action #{pending.action_id} for session-approved symbol {action_sym}")
                    try:
                        auto_res = await self._execute_action(pending)
                        display_text += f"\n\n⚡ *Auto-Executed (Session Approval Active for {action_sym.upper()})*:\n{auto_res}"
                        try:
                            async with get_session() as session:
                                session.add(ActivityLog(
                                    category="trading",
                                    description=f"Telegram user {self.user_id} AUTO-EXECUTED (Session Approved): {pending.description} → {auto_res}",
                                    actor="telegram_chat_agent",
                                ))
                                await session.commit()
                        except Exception as log_err:
                            logger.debug(f"[ChatAgent] Failed to log auto-execution to ActivityLog: {log_err}")
                    except Exception as exec_err:
                        logger.error(f"[ChatAgent] Auto-execution failed for #{pending.action_id}: {exec_err}")
                        display_text += f"\n\n❌ *Auto-Execution Failed (Session Approval Active)*: {exec_err}"
                    pending = None
                else:
                    self._pending_actions[pending.action_id] = pending
                    try:
                        asyncio.create_task(self._persist_pending_action(pending))
                    except Exception:
                        pass

        return display_text, pending

    async def _run_tier_deep_research(self, system_prompt, history, message, tool_executor=None, status_callback=None) -> dict:
        """
        SOTA 2026 Coordinator-Worker Dynamic Deep Research:
        1. Decomposes query dynamically into domain-specific specialist subagents via DynamicSubagentPool.
        2. Spawns specialist workers concurrently with isolated context sandboxes & execution timeouts.
        3. Synthesizes all specialist intelligence reports into an authoritative Executive Brief.
        """
        from analysis.subagent_spawner import DynamicSubagentPool

        if self._is_macro_event_query(message):
            system_prompt = self._inject_macro_playbooks(system_prompt)

        all_mapped = {t.get("name"): t for t in TELEGRAM_TOOLS if t.get("name")}
        all_tools = list(all_mapped.values())

        async def _notify_progress(text: str):
            if status_callback:
                try:
                    cb = status_callback(text)
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception:
                    pass

        pool = DynamicSubagentPool(
            settings=self.settings,
            max_concurrency=4,
            default_timeout=75.0,
        )

        prompt_for_subagents = (
            f"{system_prompt[0]}\n\n{system_prompt[1]}"
            if isinstance(system_prompt, tuple) and system_prompt[1]
            else (system_prompt[0] if isinstance(system_prompt, tuple) else system_prompt)
        )

        specs = pool.decompose_research_query(
            query=message,
            base_system_prompt=prompt_for_subagents,
            available_tools=all_tools,
            tool_executor=tool_executor,
        )

        roles_list = ", ".join(s.role for s in specs)
        logger.info(f"[DeepResearch] DynamicSubagentPool spawned {len(specs)} specialists: {roles_list}")
        await _notify_progress(f"🔍 Menjalankan riset paralel ({len(specs)} spesialis: {roles_list})...")

        worker_client = self._client_research or self._client_deep

        results = await pool.run_parallel(
            specs=specs,
            client=worker_client,
            progress_callback=_notify_progress,
        )

        # Build dynamic synthesis prompt from all subagent outputs
        logger.info("[DeepResearch] All specialists completed. Synthesizing Executive Intelligence Brief...")
        await _notify_progress("📑 Mensintesis Ringkasan Eksekutif Terkonsolidasi...")

        sections = []
        total_in = 0
        total_out = 0
        total_tools = 0

        for idx, res in enumerate(results, 1):
            total_in += res.input_tokens
            total_out += res.output_tokens
            total_tools += res.tool_calls_made
            content = res.content if res.success else f"[{res.role} mengalami kendala: {res.error}]"
            sections.append(f"=== {idx}. {res.role.upper()} REPORT ===\n{content}")

        synthesis_input = (
            f"User Query: {message}\n\n"
            + "\n\n".join(sections)
            + "\n\nProduce the final consolidated executive intelligence brief."
        )

        synthesizer_sys = (
            f"{prompt_for_subagents}\n\n"
            "[SYNTHESIZER ROLE]: You are the Chief Market Strategist & Synthesizer Agent. "
            f"{len(results)} specialist research subagents have investigated the user's query in parallel across "
            "multiple market domains. "
            "Synthesize their findings into an authoritative, cohesive Executive Intelligence Brief in clean Bahasa Indonesia. "
            "Structure your report clearly answering the specific questions asked (mirroring the depth of institutional macro notes):\n"
            "1. Snapshot Data Terkini & Trajektori Ekspektasi Pasar\n"
            "2. Analisis Kepastian & Derajat Pemfaktoran Pasar (Priced-In vs Asimetri Risiko)\n"
            "3. Preseden Historis: Kejutan Bank Sentral & Mekanisme Kegagalan Pasar\n"
            "4. Komparasi Kontekstual Saat Ini vs Sejarah\n"
            "5. Prediksi Press Conference & Sinyal Forward Guidance (Hawkish vs Dovish, Proyeksi Dot Plot SEP)\n"
            "6. Ringkasan Transmisi Makro (DXY, Yields, Gold, Valas Utama, Kripto/Aset Risiko)\n\n"
            "IMPORTANT TRADING PLAN DIRECTIVE: If the user did NOT explicitly ask for a technical trading plan (SL/TP/entry levels), "
            "do NOT invent or force a technical trading plan with entry/SL/TP levels in this chat response. Focus 100% on the rigorous analytical "
            "and probabilistic reasoning requested. The system will automatically persist your synthesized intelligence in the background to "
            "user_market_intel so that downstream Stage 1 (Macro) and Stage 2 (Per-Asset Trading Plan) cycles in LangGraph can utilize it."
        )

        synth_client = self._client_research or self._client_deep
        synth_tools = [PROPOSE_ACTION, SAVE_MARKET_INTELLIGENCE]
        synth_response = await synth_client.run_chat_loop(
            system_prompt=synthesizer_sys,
            conversation_history=history,
            new_user_message=synthesis_input,
            tools=synth_tools,
            tool_executor=tool_executor,
        )

        total_in += synth_response.get("input_tokens", 0)
        total_out += synth_response.get("output_tokens", 0)
        total_tools += synth_response.get("tool_calls_made", 0)

        # Background persistence: automatically persist synthesized research into user_market_intel
        # so Stage 1 (Macro) and Stage 2 (Per-Asset Trading Plan) in LangGraph absorb it seamlessly
        # without polluting the chat turn with unprompted action confirmation buttons.
        if self._is_macro_event_query(message):
            try:
                from database.models import UserMarketIntel
                clean_title = message.strip().replace("\n", " ")[:120]
                reply_raw = synth_response.get("reply", "")
                summary_text = reply_raw[:600] if len(reply_raw) > 600 else reply_raw
                async with get_session() as intel_session:
                    intel_record = UserMarketIntel(
                        telegram_user_id=str(self.user_id),
                        intel_type="deep_research",
                        title=f"Macro Event Analysis: {clean_title}",
                        summary=summary_text,
                        full_content=reply_raw,
                        affected_symbols="ALL",
                        directive="scenario_watch",
                        target_cycle="next_cycle_only",
                        expires_in_hours=24,
                    )
                    intel_session.add(intel_record)
                    await intel_session.commit()
                    logger.info(f"[DeepResearch] Background auto-saved research to user_market_intel #{intel_record.id}")
            except Exception as persist_err:
                logger.debug(f"[DeepResearch] Background persistence error: {persist_err}")

        reply_final = synth_response.get("reply", "Riset selesai namun sintesis tidak menghasilkan output.")
        if self._is_macro_event_query(message):
            reply_final += (
                "\n\nℹ️ _Hasil riset telah disimpan otomatis ke memori sistem (user_market_intel) "
                "sebagai bahan pertimbangan siklus Analisis Makro (Stage 1) dan Pembuatan Trading Plan (Stage 2) berikutnya._"
            )

        return {
            "reply": reply_final,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "tool_calls_made": total_tools,
            "proposed_action": synth_response.get("proposed_action"),
        }

    def _prepare_cache_invariant_prompt(self, system_prompt: Any, message: str) -> tuple[str, str]:
        """Separate static prefix system prompt from volatile session data, injecting volatile snapshot to user message."""
        if isinstance(system_prompt, tuple):
            static_sys, dynamic_sys = system_prompt
            user_msg = f"<volatile_overlay>\n{dynamic_sys}\n</volatile_overlay>\n\n{message}" if dynamic_sys else message
            return static_sys, user_msg
        return system_prompt, message

    async def _run_tier_lite(self, system_prompt, history, message, tool_executor=None) -> dict:
        """Lite tier path untuk query sederhana."""
        selected_tools = self._tool_router.route_tools_for_query(message)
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        response = await self._client_lite.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=user_msg,
            tools=selected_tools,
            tool_executor=tool_executor
        )
        return response

    async def _run_tier_medium(self, system_prompt, history, message, tool_executor=None) -> dict:
        """Medium tier path untuk query menengah."""
        selected_tools = self._tool_router.route_tools_for_query(message)
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        response = await self._client_medium.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=user_msg,
            tools=selected_tools,
            tool_executor=tool_executor
        )
        return response

    async def _run_tier_deep(self, system_prompt, history, message, tool_executor=None) -> dict:
        """Deep tier path untuk analisis mendalam."""
        if self._is_macro_event_query(message):
            system_prompt = self._inject_macro_playbooks(system_prompt)
        selected_tools = self._tool_router.route_tools_for_query(message)
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        response = await self._client_deep.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=user_msg,
            tools=selected_tools,
            tool_executor=tool_executor
        )
        return response

    async def _run_with_gemini(self, system_prompt, history, message, tool_executor=None, stream: bool = False):
        """Run with Gemini provider (tier_lite); yields tokens if stream=True."""
        if stream:
            async def _generator():
                client = self._client_lite
                gen_stream = getattr(client, "generate_stream", None)
                if callable(getattr(client, "generate_content_stream", None)):
                    async for chunk in client.generate_content_stream(
                        system_prompt=system_prompt, user_message=message, conversation_history=history
                    ):
                        yield chunk if isinstance(chunk, str) else getattr(chunk, "text", str(chunk))
                elif callable(gen_stream):
                    stream_call: Any = gen_stream
                    async for chunk in stream_call(message, system=system_prompt):
                        yield chunk
                else:
                    resp = await self._run_tier_lite(system_prompt, history, message, tool_executor=tool_executor)
                    reply = resp.get("reply", "")
                    chunk_size = 20
                    for i in range(0, len(reply), chunk_size):
                        yield reply[i:i + chunk_size]
                        await asyncio.sleep(0.01)
            return _generator()
        return await self._run_tier_lite(system_prompt, history, message, tool_executor=tool_executor)

    async def _run_with_claude(self, system_prompt, history, message, tool_executor=None, stream: bool = False):
        """Run with Claude provider (tier_deep); yields tokens if stream=True."""
        if stream:
            async def _generator():
                client = self._client_deep
                gen_stream = getattr(client, "generate_stream", None)
                if callable(getattr(client, "generate_content_stream", None)):
                    async for chunk in client.generate_content_stream(
                        system_prompt=system_prompt, user_message=message, conversation_history=history
                    ):
                        yield chunk if isinstance(chunk, str) else getattr(chunk, "text", str(chunk))
                elif callable(gen_stream):
                    stream_call: Any = gen_stream
                    async for chunk in stream_call(message, system=system_prompt):
                        yield chunk
                else:
                    resp = await self._run_tier_deep(system_prompt, history, message, tool_executor=tool_executor)
                    reply = resp.get("reply", "")
                    chunk_size = 20
                    for i in range(0, len(reply), chunk_size):
                        yield reply[i:i + chunk_size]
                        await asyncio.sleep(0.01)
            return _generator()
        return await self._run_tier_deep(system_prompt, history, message, tool_executor=tool_executor)

    _run_with_groq = _run_tier_medium

    # ------------------------------------------------------------------
    # Action confirmation/rejection
    # ------------------------------------------------------------------

    async def confirm_action(self, action_id: str) -> tuple[bool, str]:
        """
        Mengeksekusi usulan aksi setelah user konfirmasi.
        Returns: (success, message)
        """
        action = await self.get_pending_action(action_id)
        if not action:
            return False, "Action not found or already processed."
        if action.is_expired():
            self._pending_actions.pop(action_id, None)
            await self._delete_persisted_pending_action(action_id)
            return False, "Action expired (5-minute timeout). Please request again."

        self._pending_actions.pop(action_id, None)
        await self._delete_persisted_pending_action(action_id)
        self._consecutive_denials = 0  # Reset on approval

        try:
            result_msg = await self._execute_action(action)
            async with get_session() as session:
                session.add(ActivityLog(
                    category="trading",
                    description=f"Telegram user {self.user_id} CONFIRMED: {action.description} → {result_msg}",
                    actor="telegram_chat_agent",
                ))
                await session.commit()
            return True, result_msg
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False, f"Execution failed: {e}"

    async def reject_action(self, action_id: str) -> str:
        """Menghapus usulan aksi setelah user menolak."""
        action = await self.get_pending_action(action_id)
        if not action:
            return "Action not found."

        self._pending_actions.pop(action_id, None)
        await self._delete_persisted_pending_action(action_id)

        self._consecutive_denials += 1
        if self._consecutive_denials >= self.DENIAL_BREAKER_THRESHOLD:
            self._proposals_paused = True
            notice = (
                f"Action rejected: {action.description}\n\n"
                "⚠️ Circuit breaker tripped: 3 consecutive denials. "
                "Auto-proposals paused. Use /resume_proposals to re-enable."
            )
        else:
            notice = f"Action rejected: {action.description}"

        async with get_session() as session:
            session.add(ActivityLog(
                category="trading",
                description=f"Telegram user {self.user_id} REJECTED: {action.description} (consecutive_denials={self._consecutive_denials})",
                actor="telegram_chat_agent",
            ))
            await session.commit()
        return notice

    # ------------------------------------------------------------------
    # Action execution dispatcher
    # ------------------------------------------------------------------

    async def _execute_action(self, action: PendingAction) -> str:
        """Meneruskan aksi yang dikonfirmasi ke ExecutionService."""
        from execution.execution_service import ExecutionService
        from config.settings import load_settings

        svc = ExecutionService(self.settings)
        params = action.params

        if action.action_type == "place_order":
            # Build a minimal AssetAnalysis-like object for ExecutionService
            symbol = str(params.get("symbol") or "")
            direction = str(params.get("direction") or "")
            if not symbol or not direction:
                return "❌ Order ditolak: parameter 'symbol' dan 'direction' wajib diisi."

            async with get_session() as session:
                from analysis.tools.tool_executor import ToolExecutor
                from database.models import AssetAnalysis, FundamentalBrief

                executor = ToolExecutor(session, settings=self.settings)
                self._instrument_executor(executor)
                val_errs = await executor._validate_manual_order_structural(
                    symbol=symbol,
                    direction=direction,
                    entry_price=params.get("entry_price"),
                    stop_loss=params.get("stop_loss"),
                    take_profit=params.get("take_profit"),
                )
                if val_errs:
                    return f"❌ Order ditolak oleh validasi struktural (ADR-band/R:R/SL-TP alignment):\n" + "\n".join(f"• {err}" for err in val_errs)

                # Slippage validation against current market price & ATR
                curr_price, is_stale, _ = await svc._get_current_price(symbol, direction)
                proposed_entry = params.get("entry_price")
                if curr_price and proposed_entry:
                    atr_res = await executor.execute("get_atr", {"symbol": symbol, "timeframe": "H1"})
                    atr = (atr_res.get("atr_14") if isinstance(atr_res, dict) else None) or (curr_price * 0.005)
                    max_allowed_slippage = atr * 0.5
                    price_drift = abs(curr_price - proposed_entry)
                    if price_drift > max_allowed_slippage:
                        return f"❌ Order kedaluwarsa karena harga bergerak melebihi batas toleransi slippage (0.5 ATR / {price_drift:.5f} vs max {max_allowed_slippage:.5f}). Silakan ajukan ulang."

                brief = (await session.execute(
                    select(FundamentalBrief)
                    .order_by(FundamentalBrief.generated_at.desc())
                    .limit(1)
                )).scalar_one_or_none()

                analysis = AssetAnalysis(
                    symbol=symbol,
                    generated_at=datetime.now(timezone.utc),
                    brief_id=brief.id if brief else None,
                    decision=direction,
                    confidence=params.get("confidence", 0.7),
                    entry_zone=json.dumps({
                        "type": params.get("order_type", "market"),
                        "price": params.get("entry_price"),
                    }),
                    stop_loss=params.get("stop_loss"),
                    take_profit=params.get("take_profit"),
                    rationale=params.get("rationale", "Proposed via Telegram chat (Structural Validation Passed)"),
                    reevaluation_trigger=json.dumps({"type": "time", "detail": "Re-evaluate in 6h"}),
                )
                session.add(analysis)
                await session.flush()

                result = await svc.execute_analysis(
                    session, analysis,
                    account_equity=params.get("account_equity"),
                )

            if result.executed:
                return (
                    f"✅ Order placed!\n"
                    f"Symbol: {result.symbol}\n"
                    f"Direction: {result.decision.upper()}\n"
                    f"Lots: {result.executed_lots}\n"
                    f"Price: {result.executed_price}\n"
                    f"Ticket: {result.mt5_ticket}"
                )
            else:
                reasons = "; ".join(result.risk_rejection_reasons) or result.mt5_error or "Unknown"
                return f"❌ Order blocked: {reasons}"

        elif action.action_type == "close_position":
            raw_ticket = params.get("ticket")
            if raw_ticket is None:
                return "[ERROR] Ticket number missing for close_position."
            try:
                ticket = int(raw_ticket)
            except ValueError:
                return f"[ERROR] Invalid ticket format: {raw_ticket}"
            result = await svc.close_position_by_ticket(
                ticket, requested_by="telegram_user", reason=params.get("reason", "")
            )
            if result.get("success"):
                return f"[OK] Position #{ticket} closed. Profit: {result.get('profit', 'N/A')}"
            return f"[ERROR] Close failed: {result.get('error')}"

        elif action.action_type == "close_paper_trade":
            from utils.analytics.paper_tracker import PaperTracker
            from database.models import PaperTradeRecord, PriceOHLCV
            import utils.clock as clock
            trade_id = params.get("trade_id") or params.get("ticket") or params.get("id")
            symbol = params.get("symbol")
            async with get_session() as session:
                q = select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
                if trade_id:
                    try:
                        q = q.where(PaperTradeRecord.id == int(trade_id))
                    except ValueError:
                        pass
                elif symbol:
                    q = q.where(PaperTradeRecord.symbol == symbol.upper().replace('/', ''))
                trade = (await session.execute(q)).scalars().first()
                if not trade:
                    return f"[ERROR] Open paper trade not found for id={trade_id} / symbol={symbol}."

                last_bar = (await session.execute(
                    select(PriceOHLCV).where(PriceOHLCV.symbol == trade.symbol).order_by(PriceOHLCV.timestamp.desc()).limit(1)
                )).scalar_one_or_none()
                exit_p = last_bar.close if last_bar else trade.entry_price

                pnl_pct = 0.0
                if trade.entry_price and exit_p:
                    if trade.direction == 'buy':
                        pnl_pct = ((exit_p - trade.entry_price) / trade.entry_price) * 100.0
                    else:
                        pnl_pct = ((trade.entry_price - exit_p) / trade.entry_price) * 100.0

                closed_at = clock.now()
                trade.status = 'closed'
                trade.exit_price = exit_p
                trade.exit_reason = 'manual_chat_close'
                trade.closed_at = closed_at
                trade.pnl_pct = round(pnl_pct, 4)
                if trade.opened_at:
                    trade.holding_hours = round((closed_at - trade.opened_at).total_seconds() / 3600.0, 2)

                tracker = PaperTracker(self.settings)
                await tracker._close_linked_position(session, trade)
                await session.commit()
                return f"[OK] Paper trade #{trade.id} ({trade.symbol}) closed manually @ {exit_p:.5f}. Realized PnL: {pnl_pct:+.2f}%"

        elif action.action_type == "modify_paper_sl_tp":
            from database.models import PaperTradeRecord
            trade_id = params.get("trade_id") or params.get("id")
            symbol = params.get("symbol")
            sl = params.get("sl")
            tp = params.get("tp")
            async with get_session() as session:
                q = select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
                if trade_id:
                    try:
                        q = q.where(PaperTradeRecord.id == int(trade_id))
                    except ValueError:
                        pass
                elif symbol:
                    q = q.where(PaperTradeRecord.symbol == symbol.upper().replace('/', ''))
                trade = (await session.execute(q)).scalars().first()
                if not trade:
                    return f"[ERROR] Open paper trade not found."
                if sl is not None:
                    trade.stop_loss = float(sl)
                if tp is not None:
                    trade.take_profit = float(tp)
                await session.commit()
                return f"[OK] Paper trade #{trade.id} ({trade.symbol}) modified: SL={trade.stop_loss}, TP={trade.take_profit}"

        elif action.action_type == "cancel_trigger":
            from database.models import TradeTrigger
            trigger_id = params.get("trigger_id") or params.get("id")
            if not trigger_id:
                return "[ERROR] Trigger ID required."
            try:
                trig_id_int = int(trigger_id)
            except ValueError:
                return f"[ERROR] Invalid trigger ID format: {trigger_id}"
            async with get_session() as session:
                trigger = (await session.execute(
                    select(TradeTrigger).where(TradeTrigger.id == trig_id_int)
                )).scalar_one_or_none()
                if not trigger:
                    return f"[ERROR] Trigger #{trigger_id} not found."
                trigger.status = "cancelled"
                await session.commit()
                return f"[OK] Trigger #{trigger.id} cancelled."

        elif action.action_type == "pause_trading":
            from risk.risk_gate import RiskGate
            async with get_session() as session:
                gate = RiskGate(self.settings)
                await gate.pause_trading(session, params.get("reason", "Paused via Telegram chat"))
            return "[PAUSED] Trading paused."

        elif action.action_type == "resume_trading":
            from risk.risk_gate import RiskGate
            async with get_session() as session:
                gate = RiskGate(self.settings)
                await gate.resume_trading(session)
            return "[RESUMED] Trading resumed."

        elif action.action_type == "modify_sl_tp":
            raw_ticket = params.get("ticket")
            if raw_ticket is None:
                return "[ERROR] Ticket number missing for modify_sl_tp."
            try:
                ticket = int(raw_ticket)
            except ValueError:
                return f"[ERROR] Invalid ticket format: {raw_ticket}"
            sl = params.get("sl")
            tp = params.get("tp")
            result = await svc.modify_position_sl_tp(ticket, sl=sl, tp=tp, requested_by="telegram_chat")
            if result.get("success"):
                return f"[OK] Position #{ticket} modified: SL={sl}, TP={tp}"
            return f"[ERROR] Modify failed: {result.get('error')}"

        elif action.action_type == "save_market_intelligence":
            from analysis.tools.tool_executor import ToolExecutor
            async with get_session() as session:
                executor = ToolExecutor(session, settings=self.settings)
                self._instrument_executor(executor)
                res = await executor._tool_save_market_intelligence(params)
                if res.get("status") == "success":
                    return f"✅ Market Intelligence berhasil disimpan!\nID: #{res.get('intel_id')}\nJudul: {res.get('title')}\nDirective: {res.get('directive')}"
                else:
                    return f"❌ Gagal menyimpan Market Intelligence: {res.get('error')}"

        elif action.action_type == "db_mutation":
            return await self._execute_db_mutation(params)

        return f"Unknown action type: {action.action_type}"

    async def _execute_db_mutation(self, params: dict) -> str:
        """Eksekusi mutasi database terverifikasi (insert, update, delete) oleh Admin."""
        if not getattr(self, "is_admin", False):
            return "❌ Eksekusi ditolak: Hanya Admin yang dapat memodifikasi database."

        from analysis.tools.handlers.db_tools import get_table_model_map
        from analysis.tools.tool_guardrails import DATABASE_IMMUTABLE_TABLES
        from database.models import ActivityLog
        from sqlalchemy import inspect as sqla_inspect, Integer, BigInteger
        from datetime import date

        table_name = str(params.get("table_name", "")).strip().lower()
        operation = str(params.get("operation", "")).strip().lower()
        target_id = params.get("target_id")
        data = params.get("data") or {}

        if table_name in DATABASE_IMMUTABLE_TABLES:
            return f"❌ Eksekusi dibatalkan: Tabel '{table_name}' bersifat audit-trail imutabel dan tidak boleh diubah/dihapus."

        table_map = get_table_model_map()
        if table_name not in table_map:
            return f"❌ Tabel '{table_name}' tidak ditemukan dalam skema database."

        model_cls = table_map[table_name]

        async with get_session() as session:
            try:
                # 1. Update operation
                if operation == "update":
                    if not target_id:
                        return "❌ Target ID wajib diisi untuk operasi UPDATE."

                    pk_cols = list(sqla_inspect(model_cls).primary_key)
                    if pk_cols and isinstance(pk_cols[0].type, (Integer, BigInteger)):
                        try:
                            target_id = int(target_id)
                        except (ValueError, TypeError):
                            pass

                    row = await session.get(model_cls, target_id)
                    if not row:
                        return f"❌ Rekaman ID #{target_id} tidak ditemukan di tabel '{table_name}'."

                    pre_state = {}
                    updated_fields = {}
                    for k, v in data.items():
                        if hasattr(model_cls, k):
                            pre_state[k] = getattr(row, k, None)
                            setattr(row, k, v)
                            updated_fields[k] = v

                    await session.commit()

                    session.add(ActivityLog(
                        category="database",
                        description=f"Telegram Admin {self.user_id} UPDATED {table_name} #{target_id}: {pre_state} -> {updated_fields}",
                        actor="telegram_admin",
                    ))
                    await session.commit()
                    return (
                        f"✅ Berhasil mengupdate tabel *{table_name}* (ID: #{target_id})!\n"
                        f"• Perubahan: `{json.dumps(updated_fields)}`"
                    )

                # 2. Insert operation
                elif operation == "insert":
                    if not isinstance(data, dict) or not data:
                        return "❌ Data dictionary wajib diisi untuk operasi INSERT."

                    valid_fields = {k: v for k, v in data.items() if hasattr(model_cls, k)}
                    new_row = model_cls(**valid_fields)
                    session.add(new_row)
                    await session.commit()
                    await session.refresh(new_row)

                    new_id = getattr(new_row, "id", None) or getattr(new_row, "key", "OK")
                    session.add(ActivityLog(
                        category="database",
                        description=f"Telegram Admin {self.user_id} INSERTED into {table_name} (ID: #{new_id}): {valid_fields}",
                        actor="telegram_admin",
                    ))
                    await session.commit()
                    return (
                        f"✅ Berhasil menambahkan rekaman baru ke tabel *{table_name}* (ID: #{new_id})!\n"
                        f"• Data: `{json.dumps(valid_fields)}`"
                    )

                # 3. Delete operation
                elif operation == "delete":
                    if not target_id:
                        return "❌ Target ID wajib diisi untuk operasi DELETE."

                    pk_cols = list(sqla_inspect(model_cls).primary_key)
                    if pk_cols and isinstance(pk_cols[0].type, (Integer, BigInteger)):
                        try:
                            target_id = int(target_id)
                        except (ValueError, TypeError):
                            pass

                    row = await session.get(model_cls, target_id)
                    if not row:
                        return f"❌ Rekaman ID #{target_id} tidak ditemukan di tabel '{table_name}'."

                    pre_state = {}
                    for col in sqla_inspect(model_cls).columns:
                        val = getattr(row, col.name, None)
                        if isinstance(val, (datetime, date)):
                            val = val.isoformat()
                        pre_state[col.name] = val

                    await session.delete(row)
                    await session.commit()

                    session.add(ActivityLog(
                        category="database",
                        description=f"Telegram Admin {self.user_id} DELETED from {table_name} #{target_id}: {pre_state}",
                        actor="telegram_admin",
                    ))
                    await session.commit()
                    return f"🗑️ Berhasil menghapus rekaman #{target_id} dari tabel *{table_name}*."

                else:
                    return f"❌ Operasi database '{operation}' tidak didukung. Pilihan: insert, update, delete."

            except Exception as e:
                await session.rollback()
                logger.error(f"[ChatAgent] Database mutation failed: {e}", exc_info=True)
                return f"❌ Gagal memodifikasi database: {str(e)}"

    # ------------------------------------------------------------------
    # Pending action factory
    # ------------------------------------------------------------------

    def _create_pending_action(self, proposed: dict) -> Optional[PendingAction]:
        """Ubah call PROPOSE_ACTION dari AI menjadi objek PendingAction."""
        if self._proposals_paused:
            logger.warning("[ChatAgent] Action proposal suppressed: denial circuit breaker is tripped.")
            return None

        action_type = proposed.get("action_type")
        params      = proposed.get("params", {})
        description = proposed.get("description", str(proposed))

        if action_type not in (
            "place_order",
            "close_position",
            "close_paper_trade",
            "pause_trading",
            "resume_trading",
            "modify_sl_tp",
            "modify_paper_sl_tp",
            "cancel_trigger",
            "save_market_intelligence",
            "db_mutation",
        ):
            logger.warning(f"Unknown proposed action type: {action_type}")
            return None

        if action_type == "db_mutation":
            tbl = params.get("table_name", "unknown")
            op = str(params.get("operation", "unknown")).upper()
            tid = params.get("target_id", "N/A")
            rsn = proposed.get("reason") or params.get("reason", "")
            description = (
                f"Modifikasi Database:\n"
                f"• Tabel: {tbl}\n"
                f"• Operasi: {op} (ID: {tid})\n"
                f"• Data: {json.dumps(params.get('data', {}))}\n"
                f"• Alasan: {rsn}"
            )

        # HIGH-2: Tool Guardrail validation
        verdict = self.guardrail_controller.validate_tool_call(
            tool_name="propose_action",
            args={"action_type": action_type, "params": params},
            context={"trading_paused": self._proposals_paused, "is_admin": getattr(self, "is_admin", False)},
        )
        if not verdict.allowed:
            logger.warning(f"[ChatAgent] Action proposal blocked by guardrail ({verdict.guard_name}): {verdict.reason}")
            return None

        action_id = str(uuid.uuid4())[:8]
        return PendingAction(
            action_id=action_id,
            action_type=action_type,
            params=params,
            description=description,
        )

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    async def _build_system_prompt(self, session: AsyncSession) -> str | tuple[str, str]:
        """Construct complete system prompt with immutable static prefix for optimal KV-cache hits."""
        from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
        anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
        lines = [
            anchor,
            "",
            "You are Monika, an autonomous MT5 Trading Agent assistant.",
            "",
            "## Your Role",
            "You assist the system operator in understanding market conditions, analyzing positions, and answering queries.",
            "You CAN access real-time data using the available tools.",
            "You CAN inspect the full database schema via inspect_database_schema and query table records via read_database_records (Admin only).",
            "You CAN propose trading actions and database mutations (insert, update, delete) via the PROPOSE_ACTION tool.",
            "You CANNOT directly execute orders or database changes — all actions require explicit operator confirmation.",
            "",
            "## Tool Usage Policy",
            "Perform all tool interactions, calculations, and internal analytical reasoning in English.",
            "Always ground analytical answers in fresh data from tools rather than assumptions.",
            "",
            "## STRICT TELEGRAM FORMATTING RULES (MANDATORY)",
            "- ALWAYS communicate with the human user in fluent, polite, and professional Bahasa Indonesia unless requested otherwise in English.",
            "- ZERO EMOJI POLICY: NEVER use emojis, icons, or decorative symbols (no rockets, lightning, brains, charts, flags, etc.). Keep all text completely clean.",
            "- NO MARKDOWN HEADINGS: NEVER use '#', '##', or '###' heading syntax. Telegram does not render '#' tags properly. Use '*Bold Heading*' on a separate line instead.",
            "- NO PIPE TABLES: NEVER use markdown tables with '|' characters. Format structured data as bulleted key-value lists (e.g. '• *Metric*: Value') or monospace code blocks.",
            "- TOPIC ISOLATION: Answer ONLY the specific question asked by the user in the current turn. Do NOT re-answer, combine, or synthesize previous unrelated topics unless explicitly asked.",
            "- For standard conversational turns, keep response length concise (<= 3000 characters). For deep research, comprehensive macro event probability analyses, or complex strategic investigations, provide exhaustive institutional-grade briefs without arbitrary character limits, utilizing multi-chunk message delivery.",
            "",
            "## Anti-Hallucination Rules (MANDATORY)",
            "- When asked about past trade rationale/decisions, you MUST call get_asset_analysis or get_fundamental_brief to fetch the ORIGINAL recorded rationale before answering. Never reconstruct from generic memory.",
            "- When asked about PnL, paper trading performance, trade history, active triggers, open positions, account balance, win rate, or statistical edge, you MUST call the appropriate tool (get_paper_trading_performance, get_trade_history, get_open_positions, get_account_info, get_active_triggers, get_edge_tracker_status) before answering. Never guess numbers or claim that tools are unavailable.",
            "- If a tool returns an error or empty data, state transparently to the user that data is unavailable. Never guess numbers.",
            "",
            "Language Reminder: Reason internally in English, present final response to operator in Bahasa Indonesia.",
        ]

        # Append trading persona skill (immutable communication style)
        try:
            from skills.loader import load_skill
            persona = load_skill("telegram_persona")
            lines.append("\n---\n")
            lines.append(persona)
        except Exception:
            pass

        if self.settings.get("trading", {}).get("caveman_mode", False):
            lines.append('\n---\n')
            lines.append('# CAVEMAN MODE — SCOPE-LIMITED COMPRESSION')
            lines.append('Padatkan HANYA prosa bebas non-analitis (basa-basi, filler, hedging '
                          'percakapan). JANGAN padatkan: angka harga/level SL/TP, penjelasan '
                          'rationale trading, kutipan data dari tool, atau argumen analitis apa '
                          'pun. Jika ragu apakah suatu kalimat analitis, anggap analitis dan '
                          'tulis lengkap — salah menulis singkat pada konten analitis jauh lebih '
                          'mahal daripada salah menulis lengkap pada basa-basi.')

        # DYNAMIC TAIL: Current portfolio & time snapshot placed strictly in separate block to preserve static prefix cache
        dynamic_lines = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        dynamic_lines.append(f"## Current Session Snapshot ({now})")

        try:
            open_pos = (await session.execute(
                select(Position).where(Position.status == "open")
            )).scalars().all()
            if open_pos:
                dynamic_lines.append("## Current Open Live Positions (MT5)")
                for p in open_pos:
                    dynamic_lines.append(
                        f"- {p.symbol} {p.direction.upper()} {p.volume}lots "
                        f"@ {p.entry_price} | SL={p.sl} | TP={p.tp} | ticket={p.mt5_ticket}"
                    )
            else:
                dynamic_lines.append("## Current Open Live Positions (MT5): None.")

            # Paper Trading status snapshot
            from utils.analytics.paper_tracker import PaperTracker
            from database.models import PaperTradeRecord, TradeTrigger
            tracker = PaperTracker(self.settings)
            p_stats = await tracker.get_statistics(session)
            open_paper = (await session.execute(
                select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
            )).scalars().all()

            dynamic_lines.append("\n## Paper Trading & Portfolio Snapshot")
            mode_label = 'PAPER / DRY-RUN' if self.settings.get('paper_trading', {}).get('enabled', True) else 'LIVE MT5'
            dynamic_lines.append(f"- Mode: {mode_label}")
            dynamic_lines.append(f"- Total Paper Trades: {p_stats.get('total_trades', 0)} | Win Rate: {p_stats.get('win_rate_pct', 0):.1f}% | Total PnL: {p_stats.get('total_pnl_pct', 0):+.2f}%")
            if open_paper:
                dynamic_lines.append(f"- Active Open Paper Trades ({len(open_paper)}):")
                for op in open_paper:
                    dynamic_lines.append(f"  * #{op.id} {op.symbol} {op.direction.upper()} @ {op.entry_price} | SL={op.stop_loss} | TP={op.take_profit}")
            else:
                dynamic_lines.append("- Active Open Paper Trades: None")

            # Pending triggers
            pending_triggers = (await session.execute(
                select(TradeTrigger).where(TradeTrigger.status == "pending")
            )).scalars().all()
            dynamic_lines.append(f"- Pending Market Triggers: {len(pending_triggers)} active")

            # Risk state
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            risk = (await session.execute(
                select(RiskState)
                .where(RiskState.date >= today_start)
                .order_by(RiskState.date.desc())
                .limit(1)
            )).scalar_one_or_none()
            if risk:
                status = "PAUSED" if risk.trading_paused else "ACTIVE"
                dynamic_lines.append(f"\n## Risk State: {status} | Daily PnL: ${risk.daily_pnl:.2f} | Drawdown: ${risk.current_drawdown:.2f}")

            # Active Market Chronicle (ongoing macro/geopolitical events)
            try:
                from analysis.memory.chronicle_writer import ChronicleWriter
                c_writer = ChronicleWriter(self.settings)
                c_ctx = await c_writer.get_chronicle_context(session, days_back=30, limit=4)
                if c_ctx:
                    dynamic_lines.append(f"\n{c_ctx}")
            except Exception as e:
                logger.debug(f"Chronicle context injection in Telegram Chat failed: {e}")

        except Exception as e:
            logger.debug(f"System prompt dynamic tail enrichment failed: {e}")

        static_prompt = "\n".join(lines)
        dynamic_snapshot = "\n".join(dynamic_lines) if dynamic_lines else ""
        return (static_prompt, dynamic_snapshot) if dynamic_snapshot else static_prompt

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _save_message(
        self, session: AsyncSession, role: str, message: str, session_id: Optional[str] = None
    ) -> None:
        """Simpan obrolan ke DB."""
        try:
            uid_str = str(session_id) if session_id else str(self.user_id)
            session.add(TelegramConversation(
                telegram_user_id=uid_str,  # DB field is String
                role=role,
                message=message[:4000],
            ))
            await session.commit()
        except Exception as e:
            logger.debug(f"Save message failed (non-fatal): {e}")

    async def _load_history(self, session: AsyncSession, session_id: Optional[str] = None) -> list[dict]:
        """Muat obrolan terakhir dalam format message list dengan session timeout dan truncation terbaru."""
        from sqlalchemy import String, cast
        uid_str = str(session_id) if session_id else str(self.user_id)
        rows = (await session.execute(
            select(TelegramConversation)
            .filter(TelegramConversation.telegram_user_id == cast(uid_str, String))
            .order_by(TelegramConversation.timestamp.desc())
            .limit(HISTORY_WINDOW)
        )).scalars().all()

        if not rows:
            return []

        # Filter time decay: jika ada jeda waktu > SESSION_TIMEOUT_HOURS antar pesan berurutan, putus history
        valid_rows = []
        now = datetime.now(timezone.utc)
        last_ts = now

        for r in rows:
            r_ts = r.timestamp
            if r_ts is not None:
                if r_ts.tzinfo is None:
                    r_ts = r_ts.replace(tzinfo=timezone.utc)
                diff_hours = (last_ts - r_ts).total_seconds() / 3600.0
                if diff_hours > SESSION_TIMEOUT_HOURS:
                    break
                last_ts = r_ts
            valid_rows.append(r)

        # Akumulasi karakter dari pesan terbaru ke pesan lama
        selected_rows = []
        total_chars = 0
        for row in valid_rows:
            content = row.message or ""
            # Bersihkan footer model lama dari teks riwayat
            cleaned_content = re.sub(r'(\n\n_?\[?[\w\.\-:]+\s*\|\s*\d+\s*in,\s*\d+\s*out\]?_?|\n\n_?\[?[\w\.\-:]+\]?_?)$', '', content).strip()
            if not cleaned_content:
                continue
            if total_chars + len(cleaned_content) > MAX_HISTORY_CHARS:
                break
            selected_rows.append((row.role, cleaned_content))
            total_chars += len(cleaned_content)

        # Balik ke urutan kronologis (oldest -> newest)
        selected_rows = list(reversed(selected_rows))

        messages = [{"role": role, "content": content} for role, content in selected_rows]
        from telegram_bot.chat_compaction import ChatMicroCompactor
        compactor = ChatMicroCompactor(max_history_tokens=12000)
        messages = compactor.compact_history(messages)
        return messages
