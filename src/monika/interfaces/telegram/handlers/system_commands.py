# ==============================================================================
# File: interfaces/telegram/handlers/system_commands.py
# ==============================================================================

"""
System, Analytics, and Governance Commands Group for Telegram Bot.
Defines descriptors, permissions, and handler dispatch mapping for system diagnostics and administration.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.base import _TelegramBotMixinBase
from monika.interfaces.telegram.sanitizer import sanitize_telegram_html

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemCommandDescriptor:
    name: str
    admin_only: bool
    description: str
    usage: str


SYSTEM_COMMAND_DESCRIPTORS: Dict[str, SystemCommandDescriptor] = {
    "start": SystemCommandDescriptor("start", False, "Inisialisasi bot dan panduan awal", "/start"),
    "help": SystemCommandDescriptor("help", False, "Daftar panduan seluruh perintah bot", "/help"),
    "stats": SystemCommandDescriptor("stats", False, "Statistik performa trading dan metrik akurasi", "/stats"),
    "cost": SystemCommandDescriptor("cost", False, "Rincian biaya API token LLM", "/cost"),
    "credits": SystemCommandDescriptor("credits", False, "Sisa kuota dan billing provider LLM", "/credits"),
    "edge": SystemCommandDescriptor("edge", False, "Evaluasi edge kuantitatif dan expectancy R", "/edge"),
    "calibration": SystemCommandDescriptor(
        "calibration", False, "Kalibrasi probabilitas dan Brier score", "/calibration"
    ),
    "tokens": SystemCommandDescriptor("tokens", False, "Penggunaan token per provider dan model", "/tokens"),
    "report": SystemCommandDescriptor("report", False, "Laporan mingguan ringkas performa agent", "/report"),
    "tearsheet": SystemCommandDescriptor(
        "tearsheet", False, "Quant tearsheet institusional: Sharpe, Sortino, Calmar", "/tearsheet"
    ),
    "history": SystemCommandDescriptor("history", False, "Riwayat 10 transaksi dan aktivitas terakhir", "/history"),
    "risk": SystemCommandDescriptor("risk", False, "Ringkasan metrik risiko dan drawdown", "/risk"),
    "risk_deep": SystemCommandDescriptor(
        "risk_deep", False, "Audit risiko mendalam: VaR, CVaR, dan margin", "/risk_deep"
    ),
    "approvals": SystemCommandDescriptor(
        "approvals", True, "Daftar proposal trade yang memerlukan approval", "/approvals"
    ),
    "backtest": SystemCommandDescriptor(
        "backtest", True, "Jalankan simulasi backtest historis", "/backtest [simbol] [hari]"
    ),
    "pair": SystemCommandDescriptor("pair", False, "Otentikasi dan pairing akun Telegram dengan bot", "/pair [kode]"),
}


class TelegramSystemCommandsMixin(_TelegramBotMixinBase):
    """Mixin providing system diagnostics, stats, and governance command handlers for TelegramBot."""

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        user = update.effective_user
        name = (user.first_name if user else None) or "Trader"
        if not self._is_authorized(update):
            uid = user.id if user else "N/A"
            await update.message.reply_text(
                f"Halo *{name}*!\n\n"
                f"Selamat datang di *Monika Algorithmic Trading Desk*.\n"
                f"Akun Telegram Anda (`{uid}`) belum terhubung dengan akun trading.\n\n"
                f"Untuk menghubungkan akun, silakan kirimkan perintah:\n"
                f"`/pair` untuk membuat kode challenge atau `/pair <KODE_OTP>` untuk verifikasi.\n"
                f"Kode OTP dapat diperoleh dari konsol CLI atau web dashboard admin.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await update.message.reply_text(
            f"[SALAM] Halo *{name}*!\n\n"
            f"Halo! Saya *Monika* — MT5 Trading Agent otonom berbasis multi-agent LLM.\n\n"
            f"Gunakan /help untuk melihat semua perintah yang tersedia.\n"
            f"Atau ketik pertanyaan apa saja untuk berdiskusi langsung dengan asisten AI.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        from monika.interfaces.telegram.command_router import CommandRouter

        help_text = CommandRouter.build_help_text()
        if len(help_text) <= 3900:
            await update.message.reply_text(
                help_text,
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in help_text.splitlines(keepends=True):
            if current_len + len(line) > 3900:
                chunks.append("".join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += len(line)
        if current:
            chunks.append("".join(current))

        for chunk in chunks:
            if chunk.strip():
                await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_stats_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_cost(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            from monika.core.analytics.cost_tracker import CostTracker
            from monika.infrastructure.database.db import get_session

            async with get_session() as session:
                b_stat = await CostTracker.check_and_update_budget_status(session, self.settings)
                rolling = await CostTracker.get_rolling_7day_cost(session)
                budget = b_stat["monthly_budget"]
                daily_budget = b_stat["daily_budget"]

            text = (
                f"[SALDO] *API Cost Report*\n\n"
                f"• *Today Spend:* `${b_stat['daily_cost']:.4f}` / `${daily_budget:.2f}`\n"
                f"• *Month-to-Date:* `${b_stat['mtd_cost']:.4f}` / `${budget:.2f}` ({b_stat['usage_pct']:.1f}%)\n"
                f"• *Last 7 days:* `${rolling['cost_7d']:.4f}` ({rolling['cycles_7d']} cycles)\n"
                f"• *Avg/cycle:* `${rolling['avg_per_cycle']:.4f}`\n"
                f"• *Projected/month:* `${rolling['projected_monthly']:.2f}`\n"
                f"• *Budget Status:* `{'[BERHENTI] PAUSED' if b_stat['is_paused'] else '[BERHASIL] ACTIVE'}`\n"
            )
            if rolling["projected_monthly"] > budget:
                text += f"\n[PERINGATAN] *OVER BUDGET projection!* Consider reducing cycles or disabling escalation."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"[GAGAL] Error: {e}")

    async def _cmd_credits(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_credits_text()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_calibration(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            import json as _json

            from sqlalchemy import select

            from monika.core.analytics.agent_performance_monitor import get_currency_confidence_ceiling
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import SystemConfig

            async with get_session() as session:
                cal_cfg = (
                    await session.execute(
                        select(SystemConfig).where(SystemConfig.key == "news_tier_calibration_directives")
                    )
                ).scalar_one_or_none()

                lines = [f"[KONFIGURASI] *System Calibration States*"]
                if cal_cfg and cal_cfg.value:
                    cal_data = _json.loads(cal_cfg.value)
                    if cal_data:
                        lines.append("\n[BERITA] *News Directives:*")
                        for k, v in cal_data.items():
                            lines.append(f"• `{k}`: {v}")

                ceilings = await get_currency_confidence_ceiling(session, days_back=30)
                if ceilings:
                    lines.append("\n[TARGET] *Confidence Ceilings:*")
                    for cur, cap in ceilings.items():
                        lines.append(f"• `{cur}`: Max {cap}")

                from monika.application.protocol.enhanced_cds import get_cds_thresholds_async

                cds_thr = await get_cds_thresholds_async(session, self.settings)
                lines.append("\n[ANALISIS] *SSVP CDS Thresholds:*")
                for k, v in cds_thr.items():
                    lines.append(f"• `{k}`: {v}")

                from monika.core.analytics.specialist_tracker import compute_specialist_reliability

                spec_rel = await compute_specialist_reliability(session)
                if spec_rel.get("specialists"):
                    lines.append("\n[OPERATOR]‍[PORTOFOLIO] *Specialist Trust Weights:*")
                    for name, d in spec_rel["specialists"].items():
                        flag = " [PERINGATAN] CHRONIC" if d.get("chronically_unreliable") else ""
                        lines.append(
                            f"• `{name}`: {d['trust_weight']} (acc={d['accuracy_pct']}%, n={d['total']}){flag}"
                        )

                infl_cfg = (
                    await session.execute(
                        select(SystemConfig).where(SystemConfig.key == "score_inflation_correction_threshold")
                    )
                ).scalar_one_or_none()
                if infl_cfg and infl_cfg.value:
                    infl_data = _json.loads(infl_cfg.value)
                    lines.append(
                        f"\n[LAPORAN] *Score Inflation Correction:* threshold={infl_data.get('threshold')} (set {infl_data.get('set_at', '')[:10]})"
                    )

                try:
                    from monika.core.calibration.confidence_calibrator import compute_confidence_calibration

                    cal_rep = await compute_confidence_calibration(session)
                    brier = cal_rep.get("brier_score")
                    ece = cal_rep.get("ece")
                    if brier is not None:
                        ece_str = f", ECE={ece:.4f}" if ece is not None else ""
                        lines.append(f"\n[TARGET] *Confidence Calibration:* Brier={brier:.4f}{ece_str}")
                except Exception:
                    pass

            text = "\n".join(lines) if len(lines) > 1 else "No active calibration directives."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await update.message.reply_text(f"[GAGAL] Error: {e}")

    async def _cmd_edge(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        from monika.core.analytics.analysis_tracker import compute_factor_effectiveness, get_direction_accuracy_report
        from monika.core.analytics.paper_tracker import PaperTracker
        from monika.infrastructure.database.db import get_session

        await update.message.reply_text("[MEMPROSES] Menghitung edge assessment... (bisa memakan waktu beberapa detik)")

        async with get_session() as session:
            dir_acc = await get_direction_accuracy_report(session, 14)
            factors = await compute_factor_effectiveness(session, 30)
            tracker = PaperTracker()
            stats = await tracker.get_statistics(session)

        msg = "[LAPORAN] *EDGE ASSESSMENT*\n\n"
        msg += f"• *Win Rate (Paper):* {stats.get('win_rate_pct', 0)}% (Total: {stats.get('total_trades', 0)})\n"
        if not dir_acc.get("insufficient_data") and "overall_accuracy_4h_pct" in dir_acc:
            msg += f"• *Direction Accuracy (4H):* {dir_acc['overall_accuracy_4h_pct']}%\n\n"
        elif "direction_accuracy_4h" in dir_acc and dir_acc["direction_accuracy_4h"] is not None:
            msg += f"• *Direction Accuracy (4H):* {dir_acc['direction_accuracy_4h']}%\n\n"

        msg += "*Top Edge Factors:*\n"
        raw_factors = factors.get("factor_effectiveness", {}) if isinstance(factors, dict) else {}
        top_factors = sorted(
            raw_factors.items(), key=lambda x: x[1].get("win_rate", 0) if isinstance(x[1], dict) else 0, reverse=True
        )[:5]
        if top_factors:
            for factor, data in top_factors:
                if isinstance(data, dict):
                    msg += f"- {factor.upper()}: {data.get('win_rate', 0)}% WR ({data.get('wins', 0)}/{data.get('total', 0)})\n"
        else:
            msg += "- _Insufficient data for factor edge calculation_\n"

        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_status_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_positions(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import Position
        from monika.interfaces.telegram.message_formatter import format_positions_slip

        positions = []
        try:
            from monika.application.services.portfolio_service import PortfolioService

            async with get_session() as session:
                positions = await PortfolioService.get_open_positions(session)
        except Exception as e:
            await update.message.reply_text(f"[ GAGAL ] Error: {e}")
            return

        text = format_positions_slip(positions)
        reply_markup = None
        if positions and self._is_admin(update):
            keyboard = []
            for p in positions[:8]:
                ticket = getattr(p, "mt5_ticket", getattr(p, "ticket", None))
                if ticket:
                    keyboard.append(
                        [
                            InlineKeyboardButton(f"❌ Tutup #{ticket}", callback_data=f"close:{ticket}"),
                            InlineKeyboardButton(f"🛡️ Set BE #{ticket}", callback_data=f"be:{ticket}"),
                        ]
                    )
            if len(positions) > 1:
                keyboard.append(
                    [
                        InlineKeyboardButton("🛡️ Bulk BE (Semua Profit)", callback_data="bulk_be"),
                        InlineKeyboardButton("🚨 Tutup Semua Posisi", callback_data="closeall"),
                    ]
                )
            reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def _cmd_pipeline(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_pipeline_text()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_history_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_risk(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        text = await self._build_risk_text()
        await update.message.reply_text(sanitize_telegram_html(text), parse_mode=ParseMode.HTML)

    async def _cmd_risk_deep(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_risk_deep_text()
        await update.message.reply_text(sanitize_telegram_html(text), parse_mode=ParseMode.HTML)

    async def _cmd_tokens(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_tokens_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_account(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Menampilkan detail balance, equity, margin, free margin, margin level (/account)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        if not self.execution_service or not hasattr(self.execution_service, "mt5"):
            await update.message.reply_text("[PERINGATAN] MT5 Client tidak terhubung.")
            return

        try:
            acc = await self.execution_service.mt5.get_account_info()
            if not acc:
                await update.message.reply_text("[PERINGATAN] Gagal mengambil informasi akun MT5.")
                return

            login = acc.get("login", "-")
            server = acc.get("server", "-")
            currency = acc.get("currency", "USD")
            balance = acc.get("balance", 0.0)
            equity = acc.get("equity", 0.0)
            margin = acc.get("margin", 0.0)
            free_margin = acc.get("margin_free", 0.0)
            margin_level = acc.get("margin_level", 0.0)
            leverage = acc.get("leverage", 1)

            health = (
                "[AKTIF] SEHAT"
                if margin_level == 0 or margin_level >= 300
                else ("[WASPADA] PERHATIAN" if margin_level >= 200 else "[KRITIS] KRITIS")
            )

            text = (
                f"[BANK] *DETAIL AKUN MT5*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• *Login:* `{login}` ({server})\n"
                f"• *Currency:* `{currency}` | *Leverage:* `1:{leverage}`\n\n"
                f"• *Balance:* `${balance:,.2f}`\n"
                f"• *Equity:* `${equity:,.2f}`\n"
                f"• *Margin Terpakai:* `${margin:,.2f}`\n"
                f"• *Free Margin:* `${free_margin:,.2f}`\n"
                f"• *Margin Level:* `{margin_level:.1f}%` [{health}]\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error handling /account: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Error: {e}")

    async def _cmd_tasks(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Menampilkan tabel status background worker / monitors (/tasks)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            from monika.application.agent.task_registry import TaskRegistry

            table_md = TaskRegistry.get_formatted_status_table(getattr(self, "task_registry", None))
            await update.message.reply_text(table_md, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error handling /tasks: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Error mengambil status background tasks: {e}")

    async def _cmd_debate(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Memicu sesi ad-hoc Multi-Agent Debate Bull vs Bear (/debate <symbol>)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        symbol = ctx.args[0].upper().strip().replace("/", "") if ctx.args else "XAUUSD"
        await update.message.reply_text(
            f"[DEBAT] Memulai Multi-Agent Debate untuk *{symbol}*...\n_Bull Specialist vs Bear Specialist vs Investment Judge_",
            parse_mode=ParseMode.MARKDOWN,
        )

        from monika.application.analysis.debate.debate_orchestrator import DebateOrchestrator
        from monika.application.analysis.prefetch.pipeline import prefetch_pipeline
        from monika.infrastructure.database.db import get_session

        try:
            async with get_session() as session:
                market_data = await prefetch_pipeline.get_market_context(symbol, session=session)
                orchestrator = DebateOrchestrator(self.settings)
                result = await orchestrator.run_symbol_debate(symbol, market_data=market_data, session=session)

                decision = result.get("decision", "WAIT").upper()
                confidence = result.get("confidence", 0.0)
                rationale = result.get("rationale", "-")
                bull_arg = result.get("bull_summary", "-")
                bear_arg = result.get("bear_summary", "-")

                text = (
                    f"[DEBAT] *HASIL MULTI-AGENT DEBATE: {symbol}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"[HASIL] *Keputusan Judge:* `{decision}` (Conf: `{confidence:.1%}`)\n\n"
                    f"[BULL] *Bull Thesis:*\n_{bull_arg[:300]}_\n\n"
                    f"[BEAR] *Bear Thesis:*\n_{bear_arg[:300]}_\n\n"
                    f"[ARBITRASE] *Rationale:*\n{rationale[:400]}\n"
                    f"━━━━━━━━━━━━━━━━━━━━"
                )
                for chunk in self._chunk_text(text):
                    await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error handling /debate: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Error menjalankan debate: {e}")

    async def _cmd_audit(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Jejak audit penalaran trade dan event lifecycle."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        from sqlalchemy import desc, select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import AssetAnalysis, Position

        ticket_arg = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else None

        from monika.infrastructure.database.repositories import PositionRepository

        async with get_session() as session:
            pos_repo = PositionRepository(session)
            if ticket_arg:
                pos = await pos_repo.get_by_ticket(ticket_arg)

                if not pos:
                    await update.message.reply_text(f"[GAGAL] Posisi dengan ticket *#{ticket_arg}* tidak ditemukan.")
                    return

                analysis = None
                if pos.analysis_id:
                    analysis = await session.get(AssetAnalysis, pos.analysis_id)

                lines = [
                    f"[LOG] *Audit Trail — Ticket #{ticket_arg}*",
                    f"• Simbol: `{pos.symbol}` | Side: `{pos.direction}` | Lot: `{pos.volume}`",
                    f"• Entry: `{pos.entry_price}` | SL: `{pos.sl}` | TP: `{pos.tp}`",
                    f"• Status: `{pos.status}` | PnL: `${pos.pnl:,.2f}`"
                    if pos.pnl is not None
                    else f"• Status: `{pos.status}`",
                    f"• Waktu Buka: `{pos.opened_at.strftime('%Y-%m-%d %H:%M:%S UTC')}`" if pos.opened_at else "",
                ]
                if analysis:
                    lines.extend(
                        [
                            f"\n[KEYAKINAN] *AI Reasoning:*",
                            f"• Confluence Score: `{analysis.confluence_score}`",
                            f"• Confidence: `{analysis.confidence:.0%}`",
                            f"• Regime: `{analysis.market_regime_at_analysis or 'N/A'}`",
                            f"• Rasional: _{analysis.rationale[:250]}..._" if analysis.rationale else "",
                        ]
                    )
                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
            else:
                positions = await pos_repo.get_recent_positions(limit=5)

                if not positions:
                    await update.message.reply_text("[INFORMASI] Belum ada riwayat posisi untuk diaudit.")
                    return

                lines = ["[LOG] *Audit 5 Posisi Terakhir:*"]
                for p in positions:
                    pnl_str = f"+${p.pnl:,.2f}" if p.pnl and p.pnl >= 0 else f"-${abs(p.pnl or 0):,.2f}"
                    lines.append(
                        f"• `#{p.mt5_ticket or p.id}` {p.symbol} {p.direction} {p.volume}L — {p.status} ({pnl_str})"
                    )
                lines.append("\nKetik `/audit <ticket>` untuk detail lengkap satu posisi.")
                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_tearsheet(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        days = 30
        if ctx.args and len(ctx.args) > 0:
            try:
                days = max(1, int(ctx.args[0]))
            except ValueError:
                days = 30

        from sqlalchemy import select

        from monika.core.telemetry.reporting.tearsheet_generator import QuantTearsheetGenerator
        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import PaperTradeRecord, Position

        since = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            async with get_session() as session:
                trades = (
                    (
                        await session.execute(
                            select(PaperTradeRecord)
                            .where(PaperTradeRecord.status == "closed")
                            .where(PaperTradeRecord.closed_at >= since)
                        )
                    )
                    .scalars()
                    .all()
                )

                if not trades:
                    trades = (
                        (
                            await session.execute(
                                select(Position).where(Position.status == "closed").where(Position.closed_at >= since)
                            )
                        )
                        .scalars()
                        .all()
                    )

            if not trades:
                await update.message.reply_text(f"[INFORMASI] Belum ada trade closed dalam {days} hari terakhir.")
                return

            tearsheet = QuantTearsheetGenerator.generate_from_trades(trades)
            html_text = tearsheet.to_telegram_html()
            for chunk in self._chunk_text(html_text, is_html=True):
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)

            # Generate and send graphical equity curve snapshot
            try:
                from monika.core.analytics.chart_generator import generate_equity_curve_chart

                trade_records = []
                for t in trades:
                    t_time = getattr(t, "closed_at", getattr(t, "opened_at", None))
                    pnl_val = float(getattr(t, "pnl", getattr(t, "realized_pnl", 0.0)) or 0.0)
                    trade_records.append({"time": t_time, "pnl": pnl_val})
                if trade_records:
                    chart_buf, _ = generate_equity_curve_chart(
                        trade_records,
                        title=f"Portfolio Performance & Drawdown ({days}D)",
                        save_to_disk=False,
                    )
                    chart_buf.seek(0)
                    await update.message.reply_photo(
                        photo=chart_buf, caption=f"📈 Equity Curve & Drawdown Profile ({days}D)"
                    )
            except Exception as chart_err:
                logger.debug(f"Equity chart generation omitted: {chart_err}")
        except Exception as e:
            logger.error(f"Error executing /tearsheet: {e}")
            await update.message.reply_text(f"[GAGAL] Error generating tearsheet: {e}")

    async def _cmd_report(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_weekly_report()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)


__all__ = [
    "SystemCommandDescriptor",
    "SYSTEM_COMMAND_DESCRIPTORS",
    "TelegramSystemCommandsMixin",
]
