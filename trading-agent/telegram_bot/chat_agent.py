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
    RetryAfter = _FallbackRetryAfter
    BadRequest = _FallbackBadRequest

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
SESSION_TIMEOUT_HOURS = 24    # Jeda >24 jam memutus rantai riwayat sesi lama


def _sanitize_telegram_format(text: str) -> str:
    """
    Sanitasi respon teks agar 100% bebas dari emoticon dan kompatibel dengan Telegram/Web Markdown:
    1. Konversi heading markdown (#, ##, ###, ####) menjadi *Judul* (Bold) untuk Telegram fallback.
    2. Hapus 100% seluruh karakter emoji Unicode dan ASCII emoticons.
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
    
    # 1. Hapus emoji Unicode dan text emoticons secara mutlak
    try:
        from telegram_bot.sanitizer import strip_emojis_and_emoticons
        text = strip_emojis_and_emoticons(text)
    except Exception:
        pass

    # 2. Konversi heading markdown (#, ##, ###) menjadi *Judul* (Bold)
    text = re.sub(r"(?m)^#{1,6}\s*(.+?)\s*$", r"*\1*", text)

    # 3. Bersihkan tag model yang mungkin dihalusinasikan oleh LLM di akhir teks
    text = re.sub(
        r'(?m)^\s*\[?_?(?:gemini|claude|deepseek|qwen|gpt|llama|groq|minimax|glm)[-\w\.:]*(?:\s*\|\s*\d+\s*in,\s*\d+\s*out)?_?\]?\s*$',
        '',
        text
    )
    
    # 3. Rapikan baris kosong berulang
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
        self._last_turn_streamed: bool = False
        self._last_intercepted_pending: Optional[PendingAction] = None

    @property
    def was_last_turn_streamed(self) -> bool:
        """Returns True if the most recent turn was successfully rendered via live streaming."""
        return getattr(self, "_last_turn_streamed", False)

    @was_last_turn_streamed.setter
    def was_last_turn_streamed(self, value: bool) -> None:
        self._last_turn_streamed = bool(value)

    def set_tool_event_listener(self, listener: Optional[Any]):
        """Register a callback for tool events ('start' and 'result')."""
        self.tool_event_listener = listener

    def _instrument_executor(self, executor: Any):
        """Wrap ToolExecutor.execute to notify tool_event_listener if set and enforce Safety Fortress gating."""
        orig_exec = executor.execute
        listener = self.tool_event_listener

        MUTATING_ACTIONS_MAP = {
            "place_order": "place_order",
            "close_position": "close_position",
            "close_positions_batch": "close_all_positions",
            "set_trailing_stop": "set_trailing_stop",
            "cancel_stale_pending_orders": "cancel_stale_pending_orders",
            "modify_sl_tp": "modify_sl_tp",
            "bulk_breakeven": "bulk_breakeven",
            "secure_positions": "secure_positions",
            "cancel_order": "cancel_order",
            "close_paper_trade": "close_paper_trade",
            "modify_paper_sl_tp": "modify_paper_sl_tp",
        }

        async def _wrapped_exec(tool_name: str, tool_input: dict) -> Any:
            # Safety Fortress Gate: Intercept direct mutating calls from chat LLM
            if tool_name in MUTATING_ACTIONS_MAP:
                action_type = MUTATING_ACTIONS_MAP[tool_name]
                pending = self._create_pending_action({
                    "action_type": action_type,
                    "params": tool_input or {},
                    "description": f"Mutasi {tool_name} ({action_type})"
                })
                if pending:
                    self._last_intercepted_pending = pending
                    logger.info(f"[SafetyFortress] Intercepted mutating tool '{tool_name}' -> Created PendingAction #{pending.action_id}")
                    return {
                        "status": "pending_operator_approval",
                        "action_id": pending.action_id,
                        "action_type": action_type,
                        "message": (
                            f"Action '{tool_name}' involves capital mutation and cannot be executed directly. "
                            f"Proposal #{pending.action_id} has been generated and presented to the operator for confirmation."
                        ),
                    }

            # Safety Fortress Gate: Intercept mutating terminal execution
            if tool_name == "terminal":
                cmd = str((tool_input or {}).get("command", "")).strip()
                read_only_starters = (
                    "git status", "git log", "git diff", "git branch", "uptime", "tasklist",
                    "dir", "ls", "ps", "cat", "head", "tail", "whoami", "date", "hostname", "echo"
                )
                is_read_only = any(cmd.lower().startswith(starter) for starter in read_only_starters)
                destructive_chars = [";", "&", "|", ">"]
                if not (is_read_only and not any(ch in cmd for ch in destructive_chars)):
                    action_type = "execute_terminal_command"
                    pending = self._create_pending_action({
                        "action_type": action_type,
                        "params": tool_input or {},
                        "description": f"Eksekusi Shell Command:\n• Command: `{cmd}`"
                    })
                    if pending:
                        self._last_intercepted_pending = pending
                        logger.info(f"[SafetyFortress] Intercepted terminal command '{cmd}' -> PendingAction #{pending.action_id}")
                        return {
                            "status": "pending_operator_approval",
                            "action_id": pending.action_id,
                            "action_type": action_type,
                            "message": (
                                f"Terminal command '{cmd}' requires operator authorization. "
                                f"Proposal #{pending.action_id} generated for operator confirmation."
                            ),
                        }

            # Safety Fortress Gate: Intercept interactive computer_use GUI actions
            if tool_name == "computer_use":
                gui_action = str((tool_input or {}).get("action", "")).lower().strip()
                if gui_action != "screenshot":
                    action_type = "desktop_gui_action"
                    coord = (tool_input or {}).get("coordinate")
                    txt = (tool_input or {}).get("text")
                    key = (tool_input or {}).get("key")
                    detail = f"• Aksi: {gui_action}"
                    if coord:
                        detail += f"\n• Koordinat: {coord}"
                    if txt:
                        detail += f"\n• Input Teks: {txt}"
                    if key:
                        detail += f"\n• Tombol Key: {key}"
                    pending = self._create_pending_action({
                        "action_type": action_type,
                        "params": tool_input or {},
                        "description": f"Desktop GUI Interaction:\n{detail}"
                    })
                    if pending:
                        self._last_intercepted_pending = pending
                        logger.info(f"[SafetyFortress] Intercepted GUI action '{gui_action}' -> PendingAction #{pending.action_id}")
                        return {
                            "status": "pending_operator_approval",
                            "action_id": pending.action_id,
                            "action_type": action_type,
                            "message": (
                                f"Desktop GUI action '{gui_action}' requires operator authorization. "
                                f"Proposal #{pending.action_id} generated for operator confirmation."
                            ),
                        }

            if listener:
                try:
                    cb = listener("start", {"tool": tool_name, "input": tool_input})
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception as e:
                    logger.debug(f"[ChatAgent] Error in tool listener start: {e}")

            res = await orig_exec(tool_name, tool_input)

            if listener:
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

    async def _ensure_mcp_tools_synced(self):
        """Ensure active MCP servers are initialized and bridged tools are added to _tool_router."""
        if getattr(self, "_mcp_synced", False):
            return
        try:
            from analysis.mcp.client import McpClientManager
            from analysis.tools.unified_registry import unified_tool_registry
            mgr = McpClientManager.get_instance(self.settings)
            await mgr.initialize_servers()
            mcp_tool_defs = []
            for name, entry in unified_tool_registry._tools.items():
                if name.startswith("mcp_"):
                    mcp_tool_defs.append(entry.get_anthropic_schema())
            if mcp_tool_defs:
                self._tool_router.update_tools(mcp_tool_defs)
            self._mcp_synced = True
            logger.info(f"[ChatAgent] Synchronized {len(mcp_tool_defs)} MCP tools into ChatToolRouter.")
        except Exception as e:
            logger.warning(f"[ChatAgent] MCP tools sync non-fatal error: {e}")

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
                f"\n\n *Izin Sesi Aktif*: Proposal trading untuk `{symbol.upper()}` "
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

    def pop_pending_files(self) -> list[tuple[str, Any]]:
        """Ambil dan bersihkan file/dokumen yang tertunda dikirim ke user."""
        files = list(self._pending_files)
        self._pending_files.clear()
        return files

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
            r'\b(market\s*surprise|kejutan\s*pasar|keputusan\s*(?:suku\s*)?bunga|rate\s*decision|'
            r'probabilitas\s*(?:hike|cut|hold)|probabilitasnya\s*sebelum|odds\s*(?:hike|cut|hold))\b'
        )
        if re.search(compound_triggers, msg_lower):
            return True

        # Macro event entities and central bank concepts
        macro_event_patterns = (
            r'\b(fedwatch|cme\s*fedwatch|cme|fomc|(?:the\s+)?fed\b|'
            r'fed\s*(?:hike|cut|hold|pause|pivot|decision)|'
            r'suku\s*bunga|interest\s*rate|'
            r'(?:rate\s*)?(?:hike|cut|hold)|decision|keputusan\s*(?:bunga|rate|suku\s*bunga)|'
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

    def _inject_macro_playbooks(self, system_prompt: Union[str, tuple[str, str]], user_query: str = "") -> Union[str, tuple[str, str]]:
        """Inject macro playbooks and dynamic matched skills into system prompt."""
        from skills.loader import load_skill

        playbook_sections: list[str] = []

        # 1. Macro playbooks for macro-relevant queries
        if not user_query or self._is_macro_event_query(user_query):
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

        # 2. Dynamic skill matching for domain-specific user requests (up to 3 skills)
        if user_query:
            try:
                from skills.unified_runtime import get_skills_runtime
                runtime = get_skills_runtime()
                matched = runtime.match_skills_for_prompt(user_query)
                for s_name in matched[:3]:
                    if s_name in ("event_probability_playbook", "central_banks_framework", "market_dynamics_framework", "telegram_persona", "intent-resolution"):
                        continue
                    try:
                        instr = runtime.load_skill_instructions(s_name)
                        if instr:
                            playbook_sections.append(f"## ACTIVATED SPECIALIZATION SKILL: {s_name.upper()}\n{instr}")
                    except Exception as s_err:
                        logger.debug(f"[ChatAgent] Could not load matched skill '{s_name}': {s_err}")
            except Exception as match_err:
                logger.debug(f"[ChatAgent] Dynamic skill matching failed: {match_err}")

        if not playbook_sections:
            return system_prompt

        injected_block = "\n\n---\n\n" + "\n\n---\n\n".join(playbook_sections)

        if isinstance(system_prompt, tuple):
            static_prompt, dynamic_snapshot = system_prompt
            if "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in static_prompt and not user_query:
                return system_prompt
            return (f"{static_prompt}{injected_block}", dynamic_snapshot)

        if "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in system_prompt and not user_query:
            return system_prompt
        return f"{system_prompt}{injected_block}"

    async def _classify_query_complexity(self, msg: str) -> str:
        """Use heuristics to classify query complexity reliably."""
        if not msg or not isinstance(msg, str) or not msg.strip():
            return 'simple'

        import re
        msg_lower = msg.lower().strip()

        # Ad-hoc Deep Research & Market Intelligence patterns (highest priority)
        RESEARCH_PATTERNS = r'\b(deep-research|deep\s*research|riset\s*mendalam|investigasi\s*pasar|konsensus|whisper|saturasi\s*posisi|skenario\s*hit/miss|pre-event|bedah\s*peristiwa|analisis\s*mendalam|bedah\s*makro)\b'
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
                    if hasattr(effective_update, "message") and effective_update.message and effective_update.message.text
                    else ""
                )
            else:
                text = override_text if override_text is not None else user_message

            # Stream response if requested and update is available, provided it is not an action query requiring ToolExecutor and interactive cards
            is_action_query = bool(re.search(r'\b(close|tutup|modify|ubah|override|batalkan|cancel|adjust|geser|buy|beli|sell|jual|trade|eksekusi|pause|jeda|hentikan|stop|resume|lanjutkan|emergency|panic)\b', text, re.IGNORECASE))
            if stream and not is_action_query and not image_bytes and effective_update and (hasattr(effective_update, "message") or hasattr(effective_update, "reply_text")):
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
                image_bytes=image_bytes,
            )
        except asyncio.CancelledError:
            interrupt_note = self._interrupt_message or "Turn was interrupted."
            self._interrupt_message = None
            logger.info(f"[ChatAgent] Turn interrupted for user {self.user_id}: {interrupt_note}")
            await self._close_durable_failed_turn(session_id=session_id, reason=interrupt_note)
            return f"[PERINGATAN] {interrupt_note}", None
        except Exception as unhandled_exc:
            from agent.error_classifier import classify_api_error
            classified = classify_api_error(unhandled_exc)
            err_msg = f"Maaf, terjadi kendala teknis: {classified.reason.value}. {classified.message}"
            logger.error(f"[ChatAgent] Unhandled turn exception: {unhandled_exc}", exc_info=True)
            await self._close_durable_failed_turn(session_id=session_id, reason=f"Error: {classified.reason.value}")
            return f"[PERINGATAN] {err_msg}", None
        finally:
            self._active_task = None

    async def _close_durable_failed_turn(
        self, session_id: Optional[str] = None, reason: str = "Turn aborted before completion"
    ) -> None:
        """Appends a synthetic assistant boundary to session messages in DB if the last message was from user, preserving role alternation."""
        try:
            async with get_session() as session:
                history = await self._load_history(session, session_id=session_id)
                if history and history[-1].get("role") == "user":
                    notice = f"[System Notice: {reason}]"
                    await self._save_message(session, "assistant", notice, session_id=session_id)
                    logger.debug(f"[ChatAgent] Sealed durable failed turn with synthetic assistant boundary for session: {session_id}")
        except Exception as e:
            logger.warning(f"[ChatAgent] Failed to close durable failed turn: {e}")

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

            system_prompt = self._inject_macro_playbooks(system_prompt, user_query=clean_message)

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
            self._last_turn_streamed = True
            self.was_last_turn_streamed = True
            return final_text, None

    async def _stream_response(
        self,
        update: Any,
        context: Any,
        response_generator: Any,
    ) -> str:
        """Stream LLM tokens via Telegram edit_message_text.
 
        Enforces prefix-stability (frame N is strict prefix of N+1).
        Throttle edits to max 1 every 1200ms to respect Telegram rate limits.
        Final message removes streaming cursor and applies full HTML sanitization.
        """
        import time
        from telegram_bot.sanitizer import sanitize_telegram_html

        message = None
        if hasattr(update, "message") and update.message:
            message = await update.message.reply_text("[PROSES] Thinking...")
        elif hasattr(update, "reply_text"):
            message = await update.reply_text("[PROSES] Thinking...")

        buffer = ""
        last_edit = 0.0

        async for delta in response_generator:
            text_chunk = delta if isinstance(delta, str) else getattr(delta, "text", str(delta))
            buffer += text_chunk
            now = time.monotonic()
            if now - last_edit >= 1.2 and len(buffer) > 20:
                if message:
                    try:
                        cursor_text = _sanitize_telegram_format(buffer) + " ▌"
                        display = sanitize_telegram_html(cursor_text)
                        if len(display) <= 4096:
                            await message.edit_text(display, parse_mode="HTML")
                            last_edit = now
                    except RetryAfter as e:
                        val = getattr(e, "retry_after", 1.2)
                        retry_delay = float(val.total_seconds()) if hasattr(val, "total_seconds") else float(val)
                        await asyncio.sleep(retry_delay)
                        last_edit = time.monotonic()
                    except BadRequest:
                        pass
                    except Exception as e:
                        logger.debug(f"[ChatAgent] Stream edit error: {e}")

        # Final message: remove cursor, apply full HTML sanitization
        final_clean = _sanitize_telegram_format(buffer)
        if not final_clean.strip():
            final_clean = "[PERINGATAN] Tidak ada respons yang dihasilkan."

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
                from telegram_bot.bot import TelegramBot
                chunks = TelegramBot._chunk_text(final_clean, max_len=4000)
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
        image_bytes: Optional[bytes] = None,
    ) -> tuple[str, Optional[PendingAction]]:
        """Logika internal pemrosesan pesan dari user."""
        self._last_turn_streamed = False
        import re
        from analysis.tools.tool_executor import ToolExecutor

        # Synchronize active MCP tools into ChatToolRouter
        await self._ensure_mcp_tools_synced()
        
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
            return "[PERINGATAN] Sesi sebelumnya dibatalkan secara penuh (Hard Cancel).", None

        # Check and inject steer guidance if present
        if self._steer_queue:
            guidance_text = "\n".join(f"- {g}" for g in self._steer_queue)
            self._steer_queue.clear()
            clean_message = f"[OPERATOR STEERING GUIDANCE]:\n{guidance_text}\n\n{clean_message}"
        
        # Auto-detect jika tidak ada manual preference
        if preference == 'auto':
            # Check for direct conversational pause / resume command
            pause_match = re.search(r'\b(?:pause|jeda|hentikan\s+trading|stop\s+trading)\b', clean_message, re.IGNORECASE)
            resume_match = re.search(r'\b(?:resume|lanjutkan\s+trading|start\s+trading)\b', clean_message, re.IGNORECASE)
            if pause_match:
                pending = self._create_pending_action({
                    "action_type": "pause_trading",
                    "params": {"reason": "User requested pause via Telegram chat"},
                    "description": "Jeda (Pause) seluruh aktivitas trading dan order baru"
                })
                reply_text = "[PERINGATAN] *Konfirmasi Jeda Trading*\n\nApakah Anda yakin ingin menjeda (pause) seluruh aktivitas trading dan eksekusi order otomatis?"
                return reply_text, pending
            elif resume_match:
                pending = self._create_pending_action({
                    "action_type": "resume_trading",
                    "params": {},
                    "description": "Lanjutkan (Resume) aktivitas trading dan eksekusi order"
                })
                reply_text = "▶ *Konfirmasi Lanjutkan Trading*\n\nApakah Anda ingin melanjutkan (resume) aktivitas trading?"
                return reply_text, pending

            # HIGH-1 & P5.1 (Q36): Check for ad-hoc / debate re-evaluation LangGraph pipeline trigger
            adhoc_match = re.search(
                r'\b(?:analisis|analisa|analyze|bedah|setup|debat\s*ulang|ulangi\s*debat|re-?debate|evaluasi\s*ulang\s*debat|bandingkan|komparasi|bull\s*vs\s*bear)\s+([A-Za-z0-9,/_\s]{3,100})\b',
                clean_message,
                re.IGNORECASE,
            )
            if adhoc_match:
                candidate_str = adhoc_match.group(1).strip()
                import re as _re
                raw_syms = [_re.sub(r'[^A-Z0-9]', '', s.upper()) for s in _re.split(r'[,;\s]+', candidate_str) if s.strip()]
                configured_syms = set(
                    s.upper().replace('/', '') for s in self.settings.get("trading", {}).get("symbols", [])
                )
                KNOWN_ASSETS = {
                    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
                    "USDCAD", "USDCHF", "NZDUSD", "BTCUSD", "ETHUSD",
                    "XTIUSD", "XBRUSD", "SOLUSD"
                } | configured_syms
                valid_syms = [s for s in raw_syms if s in KNOWN_ASSETS]
                if valid_syms:
                    is_debate_rerun = bool(re.search(r'\b(debat\s*ulang|ulangi\s*debat|re-?debate|evaluasi\s*ulang\s*debat|bandingkan|komparasi|bull\s*vs\s*bear)\b', clean_message, re.IGNORECASE))
                    from agent.agent_loop import SystemAgentLoop
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
                res = status_callback(" Memulai riset mendalam...")
                if asyncio.iscoroutine(res):
                    await res
            except Exception as _st_err:
                logger.debug(f"Failed to send deep research status: {_st_err}")

        try:
            async with get_session() as session:
                history = await self._load_history(session, session_id=session_id)
                await self._save_message(session, "user", clean_message, session_id=session_id)
                system_prompt = await self._build_system_prompt(session)
                system_prompt = self._inject_macro_playbooks(system_prompt, user_query=clean_message)
                executor = ToolExecutor(session, settings=self.settings)
                executor.is_admin = getattr(self, "is_admin", False)
                self._instrument_executor(executor)
                
                if preference == 'deep_research':
                    response = await self._run_tier_deep_research(system_prompt, history, clean_message, tool_executor=executor, status_callback=status_callback)
                elif preference == 'tier_lite':
                    response = await self._run_tier_lite(system_prompt, history, clean_message, tool_executor=executor, image_bytes=image_bytes)
                elif preference == 'tier_medium':
                    response = await self._run_tier_medium(system_prompt, history, clean_message, tool_executor=executor, image_bytes=image_bytes)
                else:
                    response = await self._run_tier_deep(system_prompt, history, clean_message, tool_executor=executor, image_bytes=image_bytes)

                if getattr(executor, '_pending_charts', None):
                    self._pending_charts.extend(executor._pending_charts.values())
                    executor._pending_charts.clear()
                if hasattr(executor, 'pop_pending_files'):
                    self._pending_files.extend(executor.pop_pending_files())
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
            # Educational/glossary/hypothetical exemption
            edu_pattern = r'\b(contoh|misal|misalkan|ilustrasi|definisi|adalah|yaitu|kontrak standar|rumus|cara hitung|pengertian|maksudnya|sebagai acuan|standard lot|micro lot|cent)\b'
            if re.search(edu_pattern, reply_text, re.IGNORECASE) and not re.search(r'\b(live|posisi terbuka|saat ini|sekarang|running pnl|floating|real account)\b', reply_text, re.IGNORECASE):
                return False

            # Require specific symbol context or live claim to flag price claims
            symbol_pattern = r'\b(XAUUSD|EURUSD|GBPUSD|USDJPY|BTCUSD|AUDUSD|USDCAD|USDCHF|NZDUSD|XTIUSD|XBRUSD|USTEC|NAS100|US30)\b'
            has_symbol = bool(re.search(symbol_pattern, reply_text, re.IGNORECASE))

            live_claim_pattern = r'\b(saldo|equity|balance|floating|current price|harga sekarang|harga saat ini|posisi saya|open position)\b'
            has_live_claim = bool(re.search(live_claim_pattern, reply_text, re.IGNORECASE))

            if not (has_symbol or has_live_claim):
                # Pure conceptual explanation without concrete live market claim
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
                if hasattr(retry_executor, 'pop_pending_files'):
                    self._pending_files.extend(retry_executor.pop_pending_files())

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
        elif getattr(self, "_last_intercepted_pending", None):
            pending = self._last_intercepted_pending
            self._last_intercepted_pending = None

        if pending:
                action_sym = str(pending.params.get("symbol") or "")
                if action_sym and self.is_symbol_session_approved(action_sym):
                    logger.info(f"[ChatAgent] Auto-executing action #{pending.action_id} for session-approved symbol {action_sym}")
                    try:
                        auto_res = await self._execute_action(pending)
                        display_text += f"\n\n[BERHASIL] *Auto-Executed (Session Approval Active for {action_sym.upper()})*:\n{auto_res}"
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
                        display_text += f"\n\n[GAGAL] *Auto-Execution Failed (Session Approval Active)*: {exec_err}"
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

        system_prompt = self._inject_macro_playbooks(system_prompt, user_query=message)

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
        await _notify_progress(f" Menjalankan riset paralel ({len(specs)} spesialis: {roles_list})...")

        worker_client = self._client_research or self._client_deep

        results = await pool.run_parallel(
            specs=specs,
            client=worker_client,
            progress_callback=_notify_progress,
        )

        # Build dynamic synthesis prompt from all subagent outputs
        logger.info("[DeepResearch] All specialists completed. Synthesizing Executive Intelligence Brief...")
        await _notify_progress(" Mensintesis Ringkasan Eksekutif Terkonsolidasi...")

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
            "Synthesize their findings into an authoritative, cohesive Executive Intelligence Brief matching the user's language (Indonesian or English).\n\n"
            "CRITICAL DIRECTIVE ON DIRECT ANSWER:\n"
            "In your opening paragraph, deliver a direct, concise, and definitive answer to the user's specific question "
            "(especially exact figures, probabilities, pre vs post news deltas, or direct yes/no conclusions). "
            "Never omit or bury the direct answer beneath generic institutional commentary.\n\n"
            "Structure your report clearly answering the specific questions asked (mirroring the depth of institutional macro notes):\n"
            "1. Current Data Snapshot & Market Expectation Trajectory\n"
            "2. Certainty Analysis & Degree of Market Pricing (Priced-In Score vs Risk Asymmetry)\n"
            "3. Historical Precedents: Central Bank Surprises & Market Failure Mechanisms\n"
            "4. Contextual Comparison: Current Setup vs Historical Analogues\n"
            "5. Press Conference Predictions & Forward Guidance Signals (Hawkish vs Dovish, Dot Plot / SEP Projections)\n"
            "6. Multi-Asset Macro Transmission Summary (DXY, Yields, Gold, Major FX, Crypto/Risk Assets)\n\n"
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
                from datetime import datetime, timezone, timedelta
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
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                    )
                    intel_session.add(intel_record)
                    await intel_session.commit()
                    logger.info(f"[DeepResearch] Background auto-saved research to user_market_intel #{intel_record.id}")
            except Exception as persist_err:
                logger.debug(f"[DeepResearch] Background persistence error: {persist_err}")

        reply_final = synth_response.get("reply", "Riset selesai namun sintesis tidak menghasilkan output.")
        if self._is_macro_event_query(message):
            reply_final += (
                "\n\n[INFO] _Hasil riset telah disimpan otomatis ke memori sistem (user_market_intel) "
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

    def _format_user_message_payload(self, user_msg: str, image_bytes: Optional[bytes] = None) -> Any:
        if not image_bytes:
            return user_msg
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return [
            {"type": "text", "text": user_msg},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        ]

    async def _run_tier_lite(self, system_prompt, history, message, tool_executor=None, image_bytes: Optional[bytes] = None) -> dict:
        """Lite tier path untuk query sederhana."""
        selected_tools = self._tool_router.route_tools_for_query(message)
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        payload = self._format_user_message_payload(user_msg, image_bytes)
        response = await self._client_lite.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=payload,
            tools=selected_tools,
            tool_executor=tool_executor
        )
        return response

    async def _run_tier_medium(self, system_prompt, history, message, tool_executor=None, image_bytes: Optional[bytes] = None) -> dict:
        """Medium tier path untuk query menengah."""
        selected_tools = self._tool_router.route_tools_for_query(message)
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        payload = self._format_user_message_payload(user_msg, image_bytes)
        response = await self._client_medium.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=payload,
            tools=selected_tools,
            tool_executor=tool_executor
        )
        return response

    async def _run_tier_deep(self, system_prompt, history, message, tool_executor=None, image_bytes: Optional[bytes] = None) -> dict:
        """Deep tier path untuk analisis mendalam."""
        system_prompt = self._inject_macro_playbooks(system_prompt, user_query=message)
        selected_tools = self._tool_router.route_tools_for_query(message)
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        payload = self._format_user_message_payload(user_msg, image_bytes)
        response = await self._client_deep.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=payload,
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
            return False, "Action expired (90-second timeout). Please request again."

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
                "[PERINGATAN] Circuit breaker tripped: 3 consecutive denials. "
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
                return "[GAGAL] Order ditolak: parameter 'symbol' dan 'direction' wajib diisi."

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
                    return f"[GAGAL] Order ditolak oleh validasi struktural (ADR-band/R:R/SL-TP alignment):\n" + "\n".join(f"• {err}" for err in val_errs)

                # Slippage validation: Only apply price drift check to market orders. For limit/stop, validate entry side.
                order_type = str(params.get("order_type", "market")).lower()
                curr_price, is_stale, _ = await svc._get_current_price(symbol, direction)
                proposed_entry = params.get("entry_price")
                if order_type == "market" and curr_price and proposed_entry:
                    atr_res = await executor.execute("get_atr", {"symbol": symbol, "timeframe": "H1"})
                    atr = (atr_res.get("atr_14") if isinstance(atr_res, dict) else None) or (curr_price * 0.005)
                    max_allowed_slippage = atr * 0.5
                    price_drift = abs(curr_price - proposed_entry)
                    if price_drift > max_allowed_slippage:
                        return f"[GAGAL] Order kedaluwarsa karena harga bergerak melebihi batas toleransi slippage (0.5 ATR / {price_drift:.5f} vs max {max_allowed_slippage:.5f}). Silakan ajukan ulang."
                elif order_type in ("limit", "buy_limit", "sell_limit") and curr_price and proposed_entry:
                    if direction == "buy" and proposed_entry >= curr_price:
                        return f"[GAGAL] Buy Limit entry ({proposed_entry:.5f}) harus berada di bawah harga pasar saat ini ({curr_price:.5f})."
                    elif direction == "sell" and proposed_entry <= curr_price:
                        return f"[GAGAL] Sell Limit entry ({proposed_entry:.5f}) harus berada di atas harga pasar saat ini ({curr_price:.5f})."

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
                msg = (
                    f"[OK] Order placed!\n"
                    f"Symbol: {result.symbol}\n"
                    f"Direction: {result.decision.upper()}\n"
                    f"Lots: {result.executed_lots}\n"
                    f"Price: {result.executed_price}\n"
                    f"Ticket: {result.mt5_ticket}"
                )
                try:
                    from utils.workspace.journal_helper import record_trade_to_workspace
                    j_res = record_trade_to_workspace(self.settings, {
                        "symbol": result.symbol,
                        "action": result.decision.upper(),
                        "volume": result.executed_lots,
                        "price": result.executed_price,
                        "ticket": result.mt5_ticket,
                        "stop_loss": params.get("stop_loss"),
                        "take_profit": params.get("take_profit"),
                        "thesis": params.get("rationale", "Executed via Telegram confirmation"),
                        "status": "OPEN",
                    })
                    if j_res.get("obsidian_path"):
                        msg += f"\n Obsidian: `{j_res['obsidian_path']}`"
                    if j_res.get("excel_path"):
                        msg += f"\n[LAPORAN] Spreadsheet: `{j_res['excel_path']}`"
                except Exception as je:
                    logger.debug(f"[WorkspaceJournal] auto-journal failed: {je}")
                return msg
            else:
                reasons = "; ".join(result.risk_rejection_reasons) or result.mt5_error or "Unknown"
                return f"[GAGAL] Order blocked: {reasons}"

        elif action.action_type == "close_position":
            raw_ticket = params.get("ticket")
            if raw_ticket is None:
                return "[ERROR] Ticket number missing for close_position."
            try:
                ticket = int(raw_ticket)
            except ValueError:
                return f"[ERROR] Invalid ticket format: {raw_ticket}"
            vol_val = params.get("volume") or params.get("lots")
            vol_f = float(vol_val) if vol_val is not None else None
            result = await svc.close_position_by_ticket(
                ticket, requested_by="telegram_user", reason=params.get("reason", ""), volume=vol_f
            )
            if result.get("success"):
                msg = f"[OK] Position #{ticket} closed. Profit: {result.get('profit', 'N/A')}"
                try:
                    from utils.workspace.journal_helper import record_trade_to_workspace
                    j_res = record_trade_to_workspace(self.settings, {
                        "symbol": params.get("symbol", "POSITION"),
                        "action": "CLOSE",
                        "ticket": ticket,
                        "exit_price": result.get("price"),
                        "profit": result.get("profit"),
                        "status": "CLOSED",
                        "thesis": params.get("reason", "Manual close via Telegram"),
                    })
                    if j_res.get("obsidian_path"):
                        msg += f"\n Obsidian: `{j_res['obsidian_path']}`"
                    if j_res.get("excel_path"):
                        msg += f"\n[LAPORAN] Spreadsheet: `{j_res['excel_path']}`"
                except Exception as je:
                    logger.debug(f"[WorkspaceJournal] auto-journal failed: {je}")
                return msg
            return f"[ERROR] Close failed: {result.get('error')}"

        elif action.action_type == "close_all_positions":
            reason = params.get("reason", "Close all positions requested via Chat")
            filter_type = params.get("filter_type") or params.get("filter") or "all"
            if filter_type == "profit":
                filter_type = "profit_only"
            elif filter_type == "loss":
                filter_type = "loss_only"
            try:
                if hasattr(svc, "close_positions_batch"):
                    res = await svc.close_positions_batch(filter_type=filter_type, requested_by="chat_user", reason=reason)
                    closed_cnt = res.get("closed_count", 0)
                    failed_cnt = res.get("failed_count", 0)
                    return f"[OK] Closed {closed_cnt} positions (filter={filter_type}, failed={failed_cnt}). Summary: {res.get('closed_tickets')}"
                else:
                    res = await svc.kill_switch(reason=reason)
                    return f"[STOP] [OK] Closed all positions via kill switch. Summary: {res}"
            except Exception as e:
                return f"[ERROR] Failed to execute close positions: {e}"

        elif action.action_type == "cancel_order":
            raw_ticket = params.get("ticket") or params.get("order_id") or params.get("id")
            if raw_ticket is None:
                return "[ERROR] Order ticket number missing for cancel_order."
            try:
                ticket = int(raw_ticket)
            except ValueError:
                return f"[ERROR] Invalid ticket format: {raw_ticket}"
            if getattr(svc, "mt5", None):
                try:
                    success = await svc.mt5.cancel_order(ticket)
                    if success:
                        return f"[OK] [OK] Pending order #{ticket} successfully cancelled."
                    return f"[GAGAL] [ERROR] Failed to cancel pending order #{ticket} on MT5 terminal."
                except Exception as e:
                    return f"[ERROR] Error cancelling order #{ticket}: {e}"
            return "[ERROR] MT5 execution client unavailable."

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
                msg = f"[OK] Paper trade #{trade.id} ({trade.symbol}) closed manually @ {exit_p:.5f}. Realized PnL: {pnl_pct:+.2f}%"
                try:
                    from utils.workspace.journal_helper import record_trade_to_workspace
                    record_trade_to_workspace(self.settings, {
                        "symbol": trade.symbol,
                        "action": f"CLOSE_{trade.direction.upper()}",
                        "ticket": f"PAPER-{trade.id}",
                        "volume": getattr(trade, 'lots', 0.01),
                        "entry_price": trade.entry_price,
                        "price": exit_p,
                        "pnl_pct": pnl_pct,
                        "status": "CLOSED",
                        "thesis": f"Paper trade closed manually. Realized PnL: {pnl_pct:+.2f}%",
                    })
                except Exception as je:
                    logger.debug(f"[WorkspaceJournal] paper auto-journal failed: {je}")
                return msg

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
            dur_raw = params.get("duration") or params.get("duration_hours") or params.get("duration_str")
            duration_hours = None
            if dur_raw:
                import re
                s = str(dur_raw).lower().strip()
                m = re.match(r"^(\d+(?:\.\d+)?)\s*(m|min|mins|menit|minutes?|h|hr|hrs|jam|hours?|d|hari|days?)$", s)
                if m:
                    val = float(m.group(1))
                    unit = m.group(2)
                    if unit.startswith("m"):
                        duration_hours = val / 60.0
                    elif unit.startswith("d") or unit == "hari":
                        duration_hours = val * 24.0
                    else:
                        duration_hours = val
                else:
                    try:
                        duration_hours = float(s)
                    except ValueError:
                        pass
            elif "besok" in str(params.get("reason", "")).lower():
                duration_hours = 12.0

            reason = params.get("reason", "Paused via Telegram chat")
            async with get_session() as session:
                gate = RiskGate(self.settings)
                await gate.pause_trading(session, reason, duration_hours=duration_hours)
            if duration_hours:
                return f"[PAUSED] Trading paused for {duration_hours:g} hours. Auto-unpause scheduled."
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
                    return f"[OK] Market Intelligence berhasil disimpan!\nID: #{res.get('intel_id')}\nJudul: {res.get('title')}\nDirective: {res.get('directive')}"
                else:
                    return f"[GAGAL] Gagal menyimpan Market Intelligence: {res.get('error')}"

        elif action.action_type in ("secure_positions", "bulk_breakeven"):
            only_profit = params.get("only_profit", True)
            symbol = params.get("symbol")
            if hasattr(svc, "apply_immediate_breakeven"):
                res = await svc.apply_immediate_breakeven(only_profit=only_profit, symbol=symbol, requested_by="telegram_chat")
                return f"[KEAMANAN] [OK] {res.get('message', 'Positions secured to Breakeven.')}\nUpdated: {res.get('updated_count', 0)}, Skipped: {res.get('skipped_count', 0)}"
            return "[ERROR] Execution service does not support bulk breakeven."

        elif action.action_type == "cancel_stale_pending_orders":
            from analysis.tools.handlers.trade_intel import handle_cancel_stale_pending_orders
            max_age = float(params.get("max_age_hours", 24))
            res = await handle_cancel_stale_pending_orders({"max_age_hours": max_age})
            if res.get("status") == "success":
                return f"[OK] Stale orders cancelled: {res.get('canceled_count', 0)} cancelled, {res.get('failed_count', 0)} failed."
            return f"[ERROR] Failed to cancel stale orders: {res.get('error')}"

        elif action.action_type == "set_trailing_stop":
            from analysis.tools.handlers.position_mgmt import handle_set_trailing_stop
            async with get_session() as session:
                res = await handle_set_trailing_stop(params, session=session, settings=self.settings)
                if res.get("success"):
                    return f"[OK] Trailing stop configured: updated {res.get('updated_count', 0)} positions ({res.get('updated_tickets', [])})."
                return f"[ERROR] Failed to set trailing stop: {res.get('error') or res.get('message')}"

        elif action.action_type == "update_config":
            from database.models import SystemConfig
            key = params.get("key") or params.get("parameter")
            value = params.get("value")
            if not key or value is None:
                return "[ERROR] Parameter 'key' and 'value' required for update_config."
            async with get_session() as session:
                cfg = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == str(key))
                )).scalar_one_or_none()
                if cfg:
                    cfg.value = str(value)
                else:
                    session.add(SystemConfig(key=str(key), value=str(value)))
                await session.commit()
                try:
                    from risk.risk_gate import RiskGate
                    gate = RiskGate(self.settings)
                    gate.hot_reload_risk_parameters({str(key): value})
                except Exception:
                    pass
                return f"[OK] Configuration '{key}' updated to '{value}'."

        elif action.action_type == "update_user_preference":
            from database.models import UserPreference
            user_id = str(self.user_id)
            cat = str(params.get("category") or "general")
            key = str(params.get("key") or "preference")
            val = params.get("value")
            val_json = json.dumps(val) if not isinstance(val, str) else val
            async with get_session() as session:
                pref = (await session.execute(
                    select(UserPreference).where(
                        UserPreference.user_id == user_id,
                        UserPreference.category == cat,
                        UserPreference.key == key,
                    )
                )).scalar_one_or_none()
                if pref:
                    pref.value_json = val_json
                    pref.is_active = True
                else:
                    session.add(UserPreference(
                        user_id=user_id,
                        category=cat,
                        key=key,
                        value_json=val_json,
                        is_active=True,
                    ))
                await session.commit()
                return f"[OK] User preference updated: [{cat}] {key} = {val_json}"

        elif action.action_type == "db_mutation":
            return await self._execute_db_mutation(params)

        elif action.action_type == "execute_terminal_command":
            from analysis.tools.tool_executor import ToolExecutor
            async with get_session() as session:
                executor = ToolExecutor(session, settings=self.settings)
                res = await executor.execute("terminal", params)
                return f"[TERMINAL OUTPUT]\n{res}"

        elif action.action_type == "desktop_gui_action":
            from analysis.tools.tool_executor import ToolExecutor
            async with get_session() as session:
                executor = ToolExecutor(session, settings=self.settings)
                res = await executor.execute("computer_use", params)
                return f"[GUI ACTION RESULT]\n{res}"

        elif action.action_type == "partial_close_and_breakeven":
            from database.models import Position
            raw_ticket = params.get("ticket")
            if raw_ticket is None:
                return "[ERROR] Ticket number missing for partial_close_and_breakeven."
            try:
                ticket = int(raw_ticket)
            except ValueError:
                return f"[ERROR] Invalid ticket format: {raw_ticket}"
            vol_val = params.get("volume") or params.get("lots")
            if vol_val is None:
                return "[ERROR] Volume to close is required for partial_close_and_breakeven."
            vol_f = float(vol_val)

            close_res = await svc.close_position_by_ticket(
                ticket, requested_by="telegram_user", reason=params.get("reason", "Partial profit take"), volume=vol_f
            )
            if not close_res.get("success"):
                return f"[ERROR] Partial close failed: {close_res.get('error')}"

            entry_price = None
            async with get_session() as session:
                pos = (await session.execute(
                    select(Position).where(Position.mt5_ticket == ticket)
                )).scalar_one_or_none()
                if pos:
                    entry_price = getattr(pos, "entry_price", None) or getattr(pos, "price_open", None)
            if entry_price is None and hasattr(svc, "mt5") and svc.mt5:
                mt5_positions = await svc.mt5.get_open_positions()
                for p in mt5_positions:
                    if getattr(p, "ticket", None) == ticket:
                        entry_price = getattr(p, "price_open", None)
                        break

            if entry_price is not None:
                mod_res = await svc.modify_position_sl_tp(ticket, sl=entry_price, requested_by="telegram_chat")
                if mod_res.get("success"):
                    return f"[OK] Partial close of {vol_f} lots on #{ticket} succeeded (Profit: {close_res.get('profit', 'N/A')}), and SL moved to Breakeven ({entry_price})."
                else:
                    return f"[OK] Partial close of {vol_f} lots on #{ticket} succeeded, but moving SL to Breakeven returned: {mod_res.get('error')}"
            return f"[OK] Partial close of {vol_f} lots on #{ticket} succeeded (Profit: {close_res.get('profit', 'N/A')}), but open position not found to set BE."

        return f"Unknown action type: {action.action_type}"

    async def _execute_db_mutation(self, params: dict) -> str:
        """Eksekusi mutasi database terverifikasi (insert, update, delete) oleh Admin."""
        if not getattr(self, "is_admin", False):
            return "[GAGAL] Eksekusi ditolak: Hanya Admin yang dapat memodifikasi database."

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
            return f"[GAGAL] Eksekusi dibatalkan: Tabel '{table_name}' bersifat audit-trail imutabel dan tidak boleh diubah/dihapus."

        table_map = get_table_model_map()
        if table_name not in table_map:
            return f"[GAGAL] Tabel '{table_name}' tidak ditemukan dalam skema database."

        model_cls = table_map[table_name]

        async with get_session() as session:
            try:
                # 1. Update operation
                if operation == "update":
                    if not target_id:
                        return "[GAGAL] Target ID wajib diisi untuk operasi UPDATE."

                    pk_cols = list(sqla_inspect(model_cls).primary_key)
                    if pk_cols and isinstance(pk_cols[0].type, (Integer, BigInteger)):
                        try:
                            target_id = int(target_id)
                        except (ValueError, TypeError):
                            pass

                    row = await session.get(model_cls, target_id)
                    if not row:
                        return f"[GAGAL] Rekaman ID #{target_id} tidak ditemukan di tabel '{table_name}'."

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
                        f"[OK] Berhasil mengupdate tabel *{table_name}* (ID: #{target_id})!\n"
                        f"• Perubahan: `{json.dumps(updated_fields)}`"
                    )

                # 2. Insert operation
                elif operation == "insert":
                    if not isinstance(data, dict) or not data:
                        return "[GAGAL] Data dictionary wajib diisi untuk operasi INSERT."

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
                        f"[OK] Berhasil menambahkan rekaman baru ke tabel *{table_name}* (ID: #{new_id})!\n"
                        f"• Data: `{json.dumps(valid_fields)}`"
                    )

                # 3. Delete operation
                elif operation == "delete":
                    if not target_id:
                        return "[GAGAL] Target ID wajib diisi untuk operasi DELETE."

                    pk_cols = list(sqla_inspect(model_cls).primary_key)
                    if pk_cols and isinstance(pk_cols[0].type, (Integer, BigInteger)):
                        try:
                            target_id = int(target_id)
                        except (ValueError, TypeError):
                            pass

                    row = await session.get(model_cls, target_id)
                    if not row:
                        return f"[GAGAL] Rekaman ID #{target_id} tidak ditemukan di tabel '{table_name}'."

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
                    return f" Berhasil menghapus rekaman #{target_id} dari tabel *{table_name}*."

                else:
                    return f"[GAGAL] Operasi database '{operation}' tidak didukung. Pilihan: insert, update, delete."

            except Exception as e:
                await session.rollback()
                logger.error(f"[ChatAgent] Database mutation failed: {e}", exc_info=True)
                return f"[GAGAL] Gagal memodifikasi database: {str(e)}"

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
            "close_all_positions",
            "bulk_breakeven",
            "secure_positions",
            "cancel_order",
            "cancel_stale_pending_orders",
            "set_trailing_stop",
            "update_config",
            "update_user_preference",
            "execute_terminal_command",
            "desktop_gui_action",
            "partial_close_and_breakeven",
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
        elif action_type == "close_all_positions":
            flt = params.get("filter", "all")
            rsn = proposed.get("reason") or params.get("reason", "Permintaan penutupan posisi massal")
            description = f"Tutup Posisi Massal:\n• Filter: {flt}\n• Alasan: {rsn}"
        elif action_type in ("bulk_breakeven", "secure_positions"):
            sym = params.get("symbol", "SEMUA")
            op = params.get("only_profit", True)
            description = f"Amankan Posisi ke Breakeven:\n• Simbol: {sym}\n• Hanya Profit: {op}"
        elif action_type == "cancel_stale_pending_orders":
            max_age = params.get("max_age_hours", 24)
            description = f"Batalkan Stale Pending Order:\n• Usia Maksimal: {max_age} jam"
        elif action_type == "set_trailing_stop":
            target = params.get("symbol") or params.get("ticket") or "Semua posisi"
            tp = params.get("trailing_pips") or params.get("pips", "N/A")
            description = f"Set Trailing Stop:\n• Target: {target}\n• Trailing Pips: {tp}"
        elif action_type == "update_config":
            k = params.get("key") or params.get("parameter")
            v = params.get("value")
            description = f"Update Konfigurasi Sistem:\n• Parameter: {k}\n• Nilai Baru: {v}"
        elif action_type == "update_user_preference":
            c = params.get("category", "general")
            k = params.get("key", "preference")
            v = params.get("value")
            description = f"Update Preferensi User:\n• Kategori: {c}\n• Kunci: {k}\n• Nilai: {v}"
        elif action_type == "execute_terminal_command":
            cmd = params.get("command") or params.get("cmd") or "N/A"
            description = f"Eksekusi Shell Command:\n• Command: `{cmd}`"
        elif action_type == "desktop_gui_action":
            act = params.get("action", "unknown")
            description = f"Desktop GUI Interaction:\n• Aksi: {act}\n• Detail: {json.dumps(params)}"
        elif action_type == "partial_close_and_breakeven":
            tck = params.get("ticket")
            vol = params.get("volume") or params.get("lots")
            description = f"Partial Close & Geser Breakeven:\n• Tiket: #{tck}\n• Volume Ditutup: {vol} lot\n• SL Sisa: Geser ke BE (harga entri)"

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
            "## STRICT COMMUNICATION & FORMATTING RULES (MANDATORY)",
            "- FLEXIBLE BILINGUAL MATCHING: ALWAYS mirror the user's language dynamically. If the user communicates in Bahasa Indonesia, respond in articulate, natural, polite, and professional Bahasa Indonesia. If the user communicates in English, respond in articulate, natural, clear, and professional English.",
            "- NATURAL HUMAN TONE: Use conversational, human-like language that is pleasant and easy to read. Avoid stiff robotic phrasing, meaningless jargon, or raw unformatted data dumps.",
            "- ABSOLUTE ZERO EMOTICON POLICY: NEVER use any Unicode emojis (symbols, pictographs, charts, rockets, flags, etc.) or text-based ASCII emoticons (like :), :D, ;), ^^, -_-, <3, etc.). Keep 100% of all generated text pristine, clean, and elegant in all languages.",
            "- STRUCTURED VISUAL HIERARCHY: Organize answers with clear sections, airy paragraph spacing, crisp bullet points ('•'), bold emphasis for key numbers/assets, and clean data tables where comparison is helpful.",
            "- For standard conversational turns, keep response length concise (<= 3000 characters). For deep research, comprehensive macro event probability analyses, or complex strategic investigations, provide exhaustive institutional-grade briefs without arbitrary character limits, utilizing multi-chunk message delivery.",
            "",
            "## Anti-Hallucination Rules (MANDATORY)",
            "- When asked about past trade rationale/decisions, you MUST call get_asset_analysis or get_fundamental_brief to fetch the ORIGINAL recorded rationale before answering. Never reconstruct from generic memory.",
            "- When asked about PnL, paper trading performance, trade history, active triggers, open positions, account balance, win rate, or statistical edge, you MUST call the appropriate tool (get_paper_trading_performance, get_trade_history, get_open_positions, get_account_info, get_active_triggers, get_edge_tracker_status) before answering. Never guess numbers or claim that tools are unavailable.",
            "- If a tool returns an error or empty data, state transparently to the user that data is unavailable. Never guess numbers.",
            "",
            "## Workspace & Second-Brain Integration (Obsidian, Excel, Notion)",
            "- You have direct MCP tool access to user files, notes, and spreadsheets across local drives.",
            "- To inspect or read Obsidian notes, markdown documents, or trading plans: use 'mcp_filesystem_workspace_fs_read_file' or search notes via 'mcp_filesystem_workspace_fs_search_files'.",
            "- To create or update notes and trading journals in Obsidian: use 'mcp_filesystem_workspace_fs_write_file'. Format entries with YAML frontmatter compatible with Obsidian Dataview.",
            "- To inspect, read, or append to Excel (.xlsx) and CSV spreadsheets: use 'mcp_excel_tabular_excel_read_sheet', 'mcp_excel_tabular_excel_append_row', 'mcp_excel_tabular_excel_list_sheets'.",
            "",
            "Language Reminder: Reason internally in English, present final response to operator in the exact language used by the user (Bahasa Indonesia or English).",
            "",
            "## 6-Pillar SOP for Asset Inquiries (e.g. 'gold gimana?', 'eu bisa buy gak?')",
            "When the user asks short or ambiguous questions about an instrument, you MUST formulate a structured 6-pillar institutional briefing:",
            "1. Current Price & Market Session: Live quote (bid/ask/spread) and active session (Jakarta WIB / London / NY).",
            "2. Multi-Timeframe Trend Alignment: H4 & H1 trend alignment and market regime (trending/ranging).",
            "3. Key SMC & SnR Structure: Immediate Order Blocks, FVG zones, swing highs/lows, and liquidity pools.",
            "4. Macro & News Window Risk: Upcoming high-impact economic releases affecting the asset and risk window.",
            "5. Calibrated Bias: Clear directional bias (Bullish/Bearish/Neutral) with confluence rationale and confidence.",
            "6. Actionable Invalidation Level: Exact price level that invalidates the proposed setup or bias.",
            "",
            "## Available Slash Commands",
            "If the user inquires about direct operations or fast commands, guide them to:",
            "- /trade [symbol] [buy/sell] [lots] — Propose formal order execution with risk fortress validation.",
            "- /chart [symbol] [timeframe] — Render and deliver SMC overlaid candlestick chart to chat.",
            "- /positions — Show active open positions, entry, SL, TP, and current floating PnL.",
            "- /macro [currency] — Show economic calendar, central bank expectations, and surprise scores.",
            "- /status — System health check, MT5 connection status, and daily risk metrics.",
            "- /research [topic] — Run institutional multi-source web and academic market research.",
            "- /help — Show comprehensive help and operational guide.",
        ]

        # Append trading persona skill (immutable communication style)
        try:
            from skills.loader import load_skill
            persona = load_skill("telegram_persona")
            lines.append("\n---\n")
            lines.append(persona)
        except Exception:
            pass

        # Append intent-resolution skill (intent decomposition & anti-slop guidelines)
        try:
            from skills.loader import load_skill
            intent_res = load_skill("intent-resolution")
            if intent_res:
                lines.append("\n---\n")
                lines.append(intent_res)
        except Exception:
            pass

        # Append compact index of available specialization skills
        try:
            from skills.unified_runtime import get_skills_runtime
            runtime = get_skills_runtime()
            compact_index = runtime.get_compact_prompt_index(max_skills=15)
            if compact_index:
                lines.append("\n---\n")
                lines.append(compact_index)
        except Exception:
            pass

        if self.settings.get("trading", {}).get("caveman_mode", False):
            lines.append('\n---\n')
            lines.append('# CAVEMAN MODE — SCOPE-LIMITED COMPRESSION')
            lines.append('Compress ONLY non-analytical conversational prose (pleasantries, filler, conversational hedging). '
                         'NEVER compress: numerical price levels, SL/TP bounds, trading rationale, data quotations from tools, or analytical arguments. '
                         'If uncertain whether a sentence is analytical, treat it as analytical and write it in full — compressing analytical content is far more costly than writing conversational prose in full.')

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
            from database.models import PaperTradeRecord, TradeTrigger, UserPreference
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

            # Active Operator Preferences from UserPreference table
            try:
                prefs = (await session.execute(
                    select(UserPreference).where(UserPreference.is_active == True)
                )).scalars().all()
                if prefs:
                    dynamic_lines.append("\n## Active Operator Preferences & Constraints (MANDATORY)")
                    for pr in prefs:
                        dynamic_lines.append(f"- [{pr.category.upper()}] {pr.preference_key}: {pr.value_json}")
            except Exception as e:
                logger.debug(f"UserPreference injection failed: {e}")

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
        compactor = ChatMicroCompactor(max_history_tokens=MAX_HISTORY_CHARS // 4)
        messages = compactor.compact_history(messages)
        return messages
