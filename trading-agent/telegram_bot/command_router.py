# ==============================================================================
# File: telegram_bot/command_router.py
# ==============================================================================

"""
Command Router — Telegram Command and Interaction Routing.

Command Categories:
1. DIRECT COMMANDS (instant deterministic execution):
   /start, /status, /positions, /pause, /resume, /kill, etc.

2. CHAT MODE (conversational reasoning & interactive QA):
   Unstructured natural text routed to ChatAgent.
   Equipped with read-only tools and confirmation-gated mutation actions.

Security & Access Control:
- Whitelist authorization enforced via ALLOWED_USER_IDS.
- Unauthorized users silently dropped without disclosure.
- Critical operations restricted to ADMIN_CHAT_ID.
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger("TradingAgent.CommandRouter")


class CommandType(Enum):
    DIRECT = "direct"       # Instant rule-based response
    CHAT   = "chat"         # Dispatched to conversational AI agent
    ADMIN  = "admin"        # Restricted administrative command


@dataclass
class ParsedCommand:
    command:    str               # e.g., "status", "kill", "chat"
    args:       list[str]         # Arguments following the command name
    raw_text:   str               # Original raw message string
    command_type: CommandType
    requires_admin: bool = False


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

DIRECT_COMMANDS: dict[str, dict] = {
    "start":     {"type": CommandType.DIRECT, "admin_only": False},
    "help":      {"type": CommandType.DIRECT, "admin_only": False},
    "status":    {"type": CommandType.DIRECT, "admin_only": False},
    "positions": {"type": CommandType.DIRECT, "admin_only": False},
    "history":   {"type": CommandType.DIRECT, "admin_only": False},
    "brief":     {"type": CommandType.DIRECT, "admin_only": False},
    "risk":      {"type": CommandType.DIRECT, "admin_only": False},
    "vix":       {"type": CommandType.DIRECT, "admin_only": False},
    "tokens":    {"type": CommandType.DIRECT, "admin_only": False},
    # Perintah khusus admin
    "backtest":  {"type": CommandType.ADMIN,  "admin_only": True},
    "pause":     {"type": CommandType.ADMIN,  "admin_only": True},
    "resume":    {"type": CommandType.ADMIN,  "admin_only": True},
    "kill":      {"type": CommandType.ADMIN,  "admin_only": True},
    "close":     {"type": CommandType.ADMIN,  "admin_only": True},  # /close <ticket>
    "run":       {"type": CommandType.ADMIN,  "admin_only": True},  # /run — paksa siklus analisis manual
    "analysis":  {"type": CommandType.DIRECT, "admin_only": False},
    "approve":   {"type": CommandType.ADMIN,  "admin_only": True},
    "reject":    {"type": CommandType.ADMIN,  "admin_only": True},
    "report":    {"type": CommandType.DIRECT, "admin_only": False},
    "tearsheet": {"type": CommandType.DIRECT, "admin_only": False},
    "stats":     {"type": CommandType.DIRECT, "admin_only": False},
    "cost":      {"type": CommandType.DIRECT, "admin_only": False},
    "calibration": {"type": CommandType.DIRECT, "admin_only": False},
    "edge":      {"type": CommandType.DIRECT, "admin_only": False},
    "emergency": {"type": CommandType.ADMIN, "admin_only": True},
    "intel":     {"type": CommandType.DIRECT, "admin_only": False},
    "research":  {"type": CommandType.CHAT,   "admin_only": False},
    "archive_intel": {"type": CommandType.ADMIN, "admin_only": True},
    "unsuspend": {"type": CommandType.ADMIN,  "admin_only": True},
    "credits":   {"type": CommandType.DIRECT, "admin_only": False},
    "interrupt": {"type": CommandType.DIRECT, "admin_only": False},
    "resume_proposals": {"type": CommandType.DIRECT, "admin_only": False},
    "override":  {"type": CommandType.ADMIN,  "admin_only": True},
    "regime":    {"type": CommandType.DIRECT, "admin_only": False},
    "audit":     {"type": CommandType.DIRECT, "admin_only": False},
    "closeall":  {"type": CommandType.ADMIN,  "admin_only": True},
    "steer":     {"type": CommandType.ADMIN,  "admin_only": True},
    "calendar":  {"type": CommandType.DIRECT, "admin_only": False},
    "skills":    {"type": CommandType.DIRECT, "admin_only": False},
    "plugins":   {"type": CommandType.DIRECT, "admin_only": False},
    "memory":    {"type": CommandType.DIRECT, "admin_only": False},
    "strategies": {"type": CommandType.DIRECT, "admin_only": False},
    "fuzzy_suggest": {"type": CommandType.DIRECT, "admin_only": False},
    "risk_deep":  {"type": CommandType.DIRECT, "admin_only": False},
    "approvals":  {"type": CommandType.ADMIN,  "admin_only": True},
    "trailing":   {"type": CommandType.DIRECT, "admin_only": False},
    "reconcile":  {"type": CommandType.ADMIN,  "admin_only": True},
    "fedwatch":   {"type": CommandType.DIRECT, "admin_only": False},
    "yields":     {"type": CommandType.DIRECT, "admin_only": False},
    "fear_greed": {"type": CommandType.DIRECT, "admin_only": False},
    "cot":        {"type": CommandType.DIRECT, "admin_only": False},
    "playbooks":  {"type": CommandType.DIRECT, "admin_only": False},
    "rollback":   {"type": CommandType.ADMIN,  "admin_only": True},
    "crystallized": {"type": CommandType.DIRECT, "admin_only": False},
}

COMMAND_HELP: dict[str, str] = {
    "status":      "[Status] Tampilkan status agent, posisi aktif, dan state risiko",
    "positions":   "[Posisi] Daftar semua posisi terbuka beserta PnL",
    "brief":       "[Brief] Ringkasan fundamental terkini dari analisis AI",
    "analysis":    "[Analisis] Analisis terkini untuk simbol: /analysis <symbol>",
    "history":     "[Riwayat] 10 aktivitas terakhir",
    "risk":        "[Risiko] Status risiko terkini (PnL harian, drawdown)",
    "risk_deep":   "[Risk Deep] Evaluasi 22-point deterministic scorecard & token budget",
    "regime":      "[Rezim] Deteksi rezim makro dan volatilitas terkini",
    "override":    "[Override] Ubah parameter risiko (misal: /override max_risk 1.5)",
    "audit":       "[Audit] Jejak audit penalaran trade: /audit <ticket>",
    "closeall":    "[Close All] Tutup seluruh posisi aktif",
    "vix":         "[VIX] Data VIX terkini",
    "tokens":      "[Token] Penggunaan token API AI hari ini",
    "credits":     "[Credits] Cek status saldo dan sisa kredit OpenRouter / LLM",
    "intel":       "[Intel] Daftar intelijen pasar aktif yang disimpan operator",
    "research":    "[Research] Riset mendalam ad-hoc & intelijen pasar: /research <topik>",
    "archive_intel": "[Admin] Arsipkan intelijen pasar berdasarkan ID: /archive_intel <id>",
    "pause":       "[Admin] Pause eksekusi trading baru",
    "resume":      "[Admin] Resume eksekusi trading",
    "unsuspend":   "[Admin] Buka blokir aset tersuspensi: /unsuspend <symbol|all>",
    "kill":        "[Admin] DARURAT: Tutup semua posisi segera",
    "close":       "[Admin] Tutup posisi tertentu: /close <ticket>",
    "run":         "[Admin] Paksa eksekusi siklus analisis",
    "backtest":    "[Admin] Jalankan historical backtest: /backtest <days>",
    "approvals":   "[Admin] Daftar antrian trade & system approval proposal pending",
    "approve":     "[Admin] Eksekusi proposal trade: /approve <analysis_id>",
    "reject":      "[Admin] Tolak proposal trade: /reject <analysis_id>",
    "steer":       "[Admin] Pandu analisis in-flight secara real-time: /steer <symbol> <instruksi>",
    "trailing":    "[Trailing] Status trailing stop ATR & breakeven posisi aktif",
    "reconcile":   "[Admin] Rekonsiliasi sinkronisasi posisi MT5 vs Database",
    "report":      "[Laporan] Ringkasan mingguan PnL dan performa",
    "tearsheet":   "[Tearsheet] Institutional quant tearsheet & risk metrics: /tearsheet [days]",
    "stats":       "[Statistik] Statistik performa paper trading",
    "cost":        "[Biaya] Laporan biaya API dan proyeksi bulanan",
    "calibration": "[Kalibrasi] Status kalibrasi dan batas kepercayaan",
    "edge":        "[Edge] Metrik statistical edge dan scoring aset",
    "emergency":   "[Admin] Mode darurat dan evaluasi risiko sistem",
    "interrupt":   "[Interrupt] Hentikan eksekusi AI turn yang sedang berjalan",
    "resume_proposals": "[Proposals] Aktifkan kembali auto-proposals trade",
    "calendar":    "[Kalender] Event ekonomi makro mendatang: /calendar [currency]",
    "fedwatch":    "[FedWatch] Probabilitas keputusan suku bunga FOMC (CME FedWatch)",
    "yields":      "[Yields] Kurva yield US Treasury & 2s10s spread inversion",
    "fear_greed":  "[Fear & Greed] Sentimen pasar dan klasifikasi (Alternative.me)",
    "cot":         "[COT] Positioning institusional CFTC Commitments of Traders: /cot [market_code]",
    "skills":      "[Skills] Daftar autonomous skills & playbooks AI yang terdaftar",
    "plugins":     "[Plugins] Daftar plugin & ekstensi sistem yang terpasang",
    "memory":      "[Memory] Cari atau tampilkan refleksi & pelajaran trading: /memory [query]",
    "strategies":  "[Strategi] Daftar strategi trading & performa aturan playbook",
    "playbooks":   "[Playbooks] Status FSM, win rate, dan cooldown playbooks",
    "rollback":    "[Rollback] 1-click rollback playbook ke versi sebelumnya: /rollback <name>",
    "crystallized": "[Crystallized] Daftar skill procedural hasil closed-loop learning",
    "(any text)":  "[Chat] Diskusi dengan asisten AI terkait pasar dan trading",
}


class CommandRouter:
    """
    Parser dan router pesan Telegram.
    
    Penggunaan:
        router = CommandRouter(admin_chat_id=int, allowed_user_ids=set)
        parsed = router.parse(update)
        if not parsed:
            return  # unauthorized
    """

    def __init__(
        self,
        admin_chat_id: Optional[int] = None,
        allowed_user_ids: Optional[set[int]] = None,
    ):
        raw_admin = admin_chat_id or os.getenv("TELEGRAM_ADMIN_CHAT_ID")
        self.admin_chat_id: Optional[int] = int(raw_admin) if raw_admin else None

        raw_allowed = allowed_user_ids
        if raw_allowed is None:
            env_val = os.getenv("TELEGRAM_ALLOWED_USERS", "")
            if env_val.strip():
                raw_allowed = {int(x.strip()) for x in env_val.split(",") if x.strip()}
            else:
                raw_allowed = set()
        self.allowed_user_ids: set[int] = raw_allowed

        # If no whitelist set, default to admin only
        if self.admin_chat_id and not self.allowed_user_ids:
            self.allowed_user_ids = {self.admin_chat_id}

    def is_authorized(self, user_id: int) -> bool:
        """Cek apakah user diizinkan mengakses bot."""
        if not self.allowed_user_ids:
            # Jika whitelist kosong, tolak semua user untuk keamanan
            return False
        return user_id in self.allowed_user_ids

    def is_admin(self, user_id: int) -> bool:
        """Cek apakah user adalah admin."""
        return self.admin_chat_id is not None and user_id == self.admin_chat_id

    def parse(self, update: Update) -> Optional[ParsedCommand]:
        """
        Mengurai update Telegram menjadi objek ParsedCommand.
        Returns None jika user tidak terotorisasi.
        """
        if not update.message or not update.message.text:
            return None

        if not update.effective_user:
            return None

        user_id  = update.effective_user.id
        raw_text = update.message.text.strip()

        if not self.is_authorized(user_id):
            logger.warning(f"Unauthorized access attempt from user_id={user_id}")
            return None

        # Parsing command '/' (slash command)
        if raw_text.startswith("/"):
            parts = raw_text.lstrip("/").split()
            cmd   = parts[0].lower().split("@")[0]  # hapus suffix @BotName
            args  = parts[1:] if len(parts) > 1 else []

            info  = DIRECT_COMMANDS.get(cmd)
            if info is None:
                from telegram_bot.fuzzy_router import FuzzyCommandRouter
                fuzzy_router = FuzzyCommandRouter()
                matched_def, suggestions = fuzzy_router.resolve(cmd)
                if matched_def and matched_def.command in DIRECT_COMMANDS:
                    cmd = matched_def.command
                    info = DIRECT_COMMANDS[cmd]
                elif suggestions:
                    return ParsedCommand(
                        command="fuzzy_suggest",
                        args=suggestions,
                        raw_text=raw_text,
                        command_type=CommandType.DIRECT,
                    )
                else:
                    return ParsedCommand(
                        command="chat",
                        args=[],
                        raw_text=raw_text,
                        command_type=CommandType.CHAT,
                    )

            # Pengecekan khusus admin
            requires_admin = info.get("admin_only", False)
            if requires_admin and not self.is_admin(user_id):
                return ParsedCommand(
                    command="_unauthorized_admin",
                    args=[],
                    raw_text=raw_text,
                    command_type=CommandType.DIRECT,
                    requires_admin=True,
                )

            return ParsedCommand(
                command=cmd,
                args=args,
                raw_text=raw_text,
                command_type=info["type"],
                requires_admin=requires_admin,
            )

        # Teks biasa → obrolan asisten AI (chat)
        return ParsedCommand(
            command="chat",
            args=[],
            raw_text=raw_text,
            command_type=CommandType.CHAT,
        )

    @staticmethod
    def build_help_text() -> str:
        from telegram_bot.vintage_formatter import format_help_slip
        return format_help_slip(COMMAND_HELP)

    @staticmethod
    def build_confirm_keyboard(action_id: str) -> InlineKeyboardMarkup:
        """Create inline keyboard for AI action proposal confirmation (3-Tier Session Gate)."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Allow Once", callback_data=f"confirm:{action_id}"),
                InlineKeyboardButton("⏳ Allow for Session (4h)", callback_data=f"allow_session:{action_id}"),
            ],
            [
                InlineKeyboardButton("❌ Deny", callback_data=f"reject:{action_id}"),
            ]
        ])

    @staticmethod
    def build_close_keyboard(ticket: int) -> InlineKeyboardMarkup:
        """Create inline keyboard for position closure confirmation."""
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(f"[ CLOSE #{ticket} ]", callback_data=f"close:{ticket}"),
            InlineKeyboardButton("[ CANCEL ]",          callback_data="cancel"),
        ]])
