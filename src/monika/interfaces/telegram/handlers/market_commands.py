# ==============================================================================
# File: interfaces/telegram/handlers/market_commands.py
# ==============================================================================

"""
Market Intelligence & Quantitative Commands Group for Telegram Bot.
Defines descriptors, permissions, and handler dispatch mapping for market data and quant tools.
"""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from monika.interfaces.telegram.base import _TelegramBotMixinBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketCommandDescriptor:
    name: str
    admin_only: bool
    description: str
    usage: str


MARKET_COMMAND_DESCRIPTORS: Dict[str, MarketCommandDescriptor] = {
    "status": MarketCommandDescriptor(
        "status", False, "Status portofolio, agent state, dan risk invariants", "/status"
    ),
    "positions": MarketCommandDescriptor(
        "positions", False, "Daftar posisi aktif di MT5 dan unrealized PnL", "/positions"
    ),
    "brief": MarketCommandDescriptor("brief", False, "Fundamental brief makroekonomi terkini", "/brief"),
    "analysis": MarketCommandDescriptor(
        "analysis", False, "Analisis teknikal dan fundamental mendalam per simbol", "/analysis <simbol>"
    ),
    "pipeline": MarketCommandDescriptor("pipeline", False, "Status pipeline siklus LangGraph", "/pipeline"),
    "vix": MarketCommandDescriptor("vix", False, "Volatilitas pasar dan level VIX terkini", "/vix"),
    "fedwatch": MarketCommandDescriptor("fedwatch", False, "Probabilitas suku bunga FedWatch CME", "/fedwatch"),
    "yields": MarketCommandDescriptor("yields", False, "Kurva yield US Treasury dan spread 10Y-2Y", "/yields"),
    "macro_weekly": MarketCommandDescriptor(
        "macro_weekly", False, "Outlook makroekonomi mingguan terperinci", "/macro_weekly"
    ),
    "weekly_macro": MarketCommandDescriptor(
        "weekly_macro", False, "Alias untuk outlook makro mingguan", "/weekly_macro"
    ),
    "fear_greed": MarketCommandDescriptor("fear_greed", False, "Indeks Fear & Greed pasar global", "/fear_greed"),
    "cot": MarketCommandDescriptor("cot", False, "Laporan CFTC Commitments of Traders terkini", "/cot <simbol>"),
    "calendar": MarketCommandDescriptor("calendar", False, "Kalender rilis data ekonomi high-impact", "/calendar"),
    "smc": MarketCommandDescriptor("smc", False, "Zona Smart Money Concepts: Order Blocks dan FVG", "/smc <simbol>"),
    "factors": MarketCommandDescriptor(
        "factors", False, "Faktor konfluensi dan scoring multi-timeframe", "/factors <simbol>"
    ),
    "alpha": MarketCommandDescriptor("alpha", False, "Sinyal Alpha Zoo formula kuantitatif", "/alpha <simbol>"),
    "chart": MarketCommandDescriptor("chart", False, "Generate chart dan visualisasi harga", "/chart <simbol>"),
}


class TelegramMarketCommandsMixin(_TelegramBotMixinBase):
    """Mixin providing market intelligence and quant command handlers for TelegramBot."""

    async def _cmd_brief(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_brief_text()
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_analysis(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        if not ctx.args:
            await update.message.reply_text("Usage: /analysis <symbol>")
            return

        symbol = ctx.args[0].upper()
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_analysis_text(symbol)
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_fedwatch(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_fedwatch_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_yields(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_yields_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_fear_greed(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        text = await self._build_fear_greed_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_cot(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        market_code = ctx.args[0] if ctx.args else None
        text = await self._build_cot_text(market_code)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_macro_weekly(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        days = 7
        curr = None
        args = ctx.args or []
        if args:
            first_arg = args[0].strip()
            if first_arg.isdigit():
                days = int(first_arg)
            else:
                curr = first_arg.upper()
            if len(args) > 1 and args[1].strip().isdigit():
                days = int(args[1].strip())

        from monika.application.analysis.tools.handlers.macro_tools import handle_get_weekly_macro_summary
        from monika.infrastructure.database.db import get_session

        async with get_session() as session:
            res = await handle_get_weekly_macro_summary(
                {"days_ahead": days, "currencies": curr},
                session=session,
                settings=self.settings,
            )
        text = res.get("formatted_summary") or "[ FAILED ] Tidak dapat menyusun ringkasan makro mingguan."
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_monte_carlo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        args = ctx.args or []
        symbol = args[0].upper() if args else None
        sims = 1000
        if len(args) > 1:
            try:
                sims = int(args[1])
            except ValueError:
                pass

        from monika.application.analysis.tools.handlers.trade_intel import handle_run_monte_carlo_simulation

        res = await handle_run_monte_carlo_simulation({"num_simulations": sims, "symbol": symbol})
        fe = res.get("final_equity_distribution", {})
        text = (
            f"[PELUANG] *Monte Carlo Stress Test Report*\n"
            f"• Sim Iterations: `{res.get('num_simulations')}` (`{res.get('sample_source')}`)\n"
            f"• Sample Trades: `{res.get('sample_trades_count')}` (Asset: `{res.get('symbol_filter')}`)\n"
            f"• *VaR 95% Max DD:* `{res.get('var_95_drawdown_pct')}%`\n"
            f"• *VaR 99% Max DD:* `{res.get('var_99_drawdown_pct')}%`\n"
            f"• *Median Max DD:* `{res.get('median_drawdown_pct')}%`\n"
            f"• *Ruin Probability:* `{res.get('ruin_probability_pct')}%`\n"
            f"• *Equity Outcomes ($10k base):*\n"
            f"  - Worst 5% (P5): `${fe.get('p5', 0):,.2f}`\n"
            f"  - Median (P50): `${fe.get('median_p50', 0):,.2f}`\n"
            f"  - Best 5% (P95): `${fe.get('p95', 0):,.2f}`"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_stress_test(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        import time

        from monika.application.evals.hostile_market_probe import HostileMarketProbe

        symbol = ctx.args[0].upper() if ctx.args else "EURUSD"
        probe = HostileMarketProbe(reference_price=1.0850, symbol=symbol)

        def risk_validator(tick):
            if tick["bid"] <= 0 or tick["ask"] <= 0:
                return False, "Corrupt or non-positive price"
            if tick["bid"] > tick["ask"] or tick["spread_pips"] < 0:
                return False, "Crossed book inversion (bid > ask)"
            if tick["spread_pips"] > 10.0:
                return False, f"Catastrophic spread spike ({tick['spread_pips']} pips)"
            if time.time() - tick["timestamp"] > 120.0:
                return False, "Stale feed: timestamp exceeds max drift threshold (120s)"
            if abs(tick["bid"] - 1.0850) / 1.0850 > 0.10:
                return False, "Flash crash tick: price drop > 10% trips circuit breaker"
            return True, "Valid tick"

        res = probe.verify_resilience(risk_validator)
        lines = [
            f"[PROTEKSI] *Hostile Market Feed Wire Probes ({symbol})*",
            f"• Battery Scenarios: `{res['total_tested']}`",
            f"• Fail-Closed Rejections: `{res['passed_count']}/{res['total_tested']}`\n",
        ]
        for d in res["details"]:
            st = "[BERHASIL] BLOCKED" if d["is_resilient"] else "[GAGAL] LEAKED"
            lines.append(f"• `{d['scenario']}`: {st}\n  _{d['reason']}_")

        if res["all_resilient"]:
            lines.append("\n[TARGET] *Status: 100% RESILIENT (Semua anomali ditolak fail-closed)*")
        else:
            lines.append("\n[PERINGATAN] *Status: VULNERABILITY DETECTED*")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_chart(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Render and send candlestick PNG chart (/chart <symbol> [timeframe])."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)

        args = ctx.args or []
        sym = args[0].strip().upper().replace("/", "") if args else "XAUUSD"
        tf = args[1].strip().upper() if len(args) > 1 else "H1"

        try:
            from sqlalchemy import select

            from monika.core.analytics.chart_generator import generate_candlestick_chart_async
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import PriceOHLCV

            rows = []
            async with get_session() as session:
                stmt = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == sym, PriceOHLCV.timeframe == tf)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(80)
                )
                db_rows = (await session.execute(stmt)).scalars().all()
                if db_rows:
                    rows = list(reversed(db_rows))

            if not rows and self.execution_service and hasattr(self.execution_service, "mt5_client"):
                client = self.execution_service.mt5_client
                if hasattr(client, "copy_rates_from_pos"):
                    raw_rates = client.copy_rates_from_pos(sym, tf, 0, 80)
                    if raw_rates:
                        rows = raw_rates

            if not rows or len(rows) < 2:
                await update.message.reply_text(
                    f"[PERINGATAN] Data OHLCV untuk <code>{sym}</code> ({tf}) belum tersedia di database atau broker MT5.",
                    parse_mode=ParseMode.HTML,
                )
                return

            ohlcv_data = [
                {
                    "timestamp": getattr(r, "timestamp", getattr(r, "time", None)),
                    "open": float(getattr(r, "open", 0.0)),
                    "high": float(getattr(r, "high", 0.0)),
                    "low": float(getattr(r, "low", 0.0)),
                    "close": float(getattr(r, "close", 0.0)),
                    "volume": float(getattr(r, "volume", getattr(r, "tick_volume", 0.0))),
                }
                for r in rows
            ]

            buf = await generate_candlestick_chart_async(ohlcv_data, symbol=sym, timeframe=tf)
            buf.seek(0)
            await update.message.reply_photo(
                photo=buf,
                caption=f"📊 <b>Candlestick Chart: {sym} ({tf})</b>\nTotal: {len(ohlcv_data)} candles | Moving Averages (20, 50)",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.error(f"Error generating /chart for {sym}: {exc}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal membuat grafik {sym}: {exc}", parse_mode=ParseMode.HTML)

    async def _cmd_smc(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Render and send Smart Money Concepts (SMC) overlay PNG chart (/smc <symbol> [timeframe])."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)

        args = ctx.args or []
        sym = args[0].strip().upper().replace("/", "") if args else "XAUUSD"
        tf = args[1].strip().upper() if len(args) > 1 else "H1"

        try:
            from sqlalchemy import select

            from monika.core.analytics.chart_generator import generate_smc_candlestick_chart
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import FVGZone, OrderBlock, PriceOHLCV

            rows = []
            fvg_list = []
            ob_list = []
            async with get_session() as session:
                stmt = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == sym, PriceOHLCV.timeframe == tf)
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(80)
                )
                db_rows = (await session.execute(stmt)).scalars().all()
                if db_rows:
                    rows = list(reversed(db_rows))

                # FVGs for requested timeframe
                fvg_stmt = (
                    select(FVGZone)
                    .where(FVGZone.symbol == sym, FVGZone.timeframe == tf)
                    .order_by(FVGZone.formed_at.desc())
                    .limit(10)
                )
                fvg_rows = (await session.execute(fvg_stmt)).scalars().all()
                for f in fvg_rows:
                    fvg_list.append({"top": float(f.gap_high), "bottom": float(f.gap_low), "type": f.direction})

                # Order Blocks for requested timeframe
                ob_stmt = (
                    select(OrderBlock)
                    .where(OrderBlock.symbol == sym, OrderBlock.timeframe == tf)
                    .order_by(OrderBlock.formed_at.desc())
                    .limit(10)
                )
                ob_rows = (await session.execute(ob_stmt)).scalars().all()
                for o in ob_rows:
                    ob_list.append({"high": float(o.price_high), "low": float(o.price_low), "type": o.direction})

            if not rows or len(rows) < 2:
                await update.message.reply_text(
                    f"[PERINGATAN] Data OHLCV untuk <code>{sym}</code> ({tf}) belum tersedia untuk pemetaan SMC.",
                    parse_mode=ParseMode.HTML,
                )
                return

            ohlcv_data = [
                {
                    "timestamp": getattr(r, "timestamp", getattr(r, "time", None)),
                    "open": float(getattr(r, "open", 0.0)),
                    "high": float(getattr(r, "high", 0.0)),
                    "low": float(getattr(r, "low", 0.0)),
                    "close": float(getattr(r, "close", 0.0)),
                    "volume": float(getattr(r, "volume", getattr(r, "tick_volume", 0.0))),
                }
                for r in rows
            ]

            buf, _ = await asyncio.to_thread(
                generate_smc_candlestick_chart,
                ohlcv_data,
                symbol=sym,
                timeframe=tf,
                fvg_list=fvg_list,
                order_blocks=ob_list,
                save_to_disk=False,
            )
            buf.seek(0)
            await update.message.reply_photo(
                photo=buf,
                caption=(
                    f"🏛️ <b>Smart Money Concepts (SMC): {sym} ({tf})</b>\n"
                    f"• Order Blocks Terdeteksi: {len(ob_list)}\n"
                    f"• Fair Value Gaps (FVG): {len(fvg_list)}\n"
                    f"<i>Kotak hijau: Demand/Bullish | Kotak merah: Supply/Bearish</i>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.error(f"Error generating /smc for {sym}: {exc}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal membuat grafik SMC {sym}: {exc}", parse_mode=ParseMode.HTML)

    async def _cmd_factors(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Inspect available Alpha Factor Zoo formulas (/factors)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        try:
            from monika.domain.indicators.micro_alpha_zoo import MicroAlphaZoo

            factors = MicroAlphaZoo.list_factors()
            if not factors:
                await update.message.reply_text(
                    "[ INFO ] Belum ada faktor terdaftar di MicroAlphaZoo.", parse_mode=ParseMode.HTML
                )
                return

            by_cat: dict[str, list[Any]] = {}
            for f in factors:
                by_cat.setdefault(f.category, []).append(f)

            lines = ["🧬 <b>MONIKA ALPHA FACTOR ZOO (20 Formulasi Kuantitatif)</b>\n"]
            for cat, flist in by_cat.items():
                lines.append(f"<b>📂 {cat.upper()} ({len(flist)} Faktor):</b>")
                for f in flist:
                    lines.append(
                        f"• <code>{f.name}</code> (Lookback: {f.lookback}b, {f.direction})\n  <i>{html.escape(f.description)}</i>"
                    )
                lines.append("")

            lines.append(
                "<b>Inspeksi Real-Time:</b>\n• <code>/alpha &lt;symbol&gt; &lt;factor_name&gt;</code> (Contoh: <code>/alpha XAUUSD alpha_001</code>)"
            )
            full_text = "\n".join(lines)
            for chunk in self._chunk_text(full_text, max_len=4000, is_html=True):
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.error(f"Error evaluating /factors: {exc}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal mengambil daftar faktor: {exc}", parse_mode=ParseMode.HTML)

    async def _cmd_alpha(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Calculate and inspect a quantitative alpha factor (/alpha <symbol> <factor>)."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        args = ctx.args or []
        if len(args) < 2:
            await update.message.reply_text(
                "Penggunaan: <code>/alpha &lt;symbol&gt; &lt;factor_name&gt;</code>\nContoh: <code>/alpha XAUUSD alpha_001</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        sym = args[0].strip().upper().replace("/", "")
        factor_name = args[1].strip().lower()

        try:
            import pandas as pd
            from sqlalchemy import select

            from monika.domain.indicators.micro_alpha_zoo import MicroAlphaZoo
            from monika.infrastructure.database.db import get_session
            from monika.infrastructure.database.models import PriceOHLCV

            async with get_session() as session:
                rows = (
                    (
                        await session.execute(
                            select(PriceOHLCV)
                            .where(PriceOHLCV.symbol == sym)
                            .order_by(PriceOHLCV.timestamp.desc())
                            .limit(100)
                        )
                    )
                    .scalars()
                    .all()
                )

            if not rows:
                await update.message.reply_text(
                    f"[GAGAL] Data OHLCV untuk <code>{sym}</code> tidak ditemukan di database.",
                    parse_mode=ParseMode.HTML,
                )
                return

            rows = list(reversed(rows))
            df = pd.DataFrame(
                [
                    {
                        "open": float(r.open),
                        "high": float(r.high),
                        "low": float(r.low),
                        "close": float(r.close),
                        "volume": float(r.volume or 0),
                    }
                    for r in rows
                ]
            )

            score_series = MicroAlphaZoo.compute_factor(factor_name, df)
            latest_val = float(score_series.iloc[-1]) if not score_series.empty else 0.0

            meta = next((m for m in MicroAlphaZoo.list_factors() if m.name == factor_name), None)
            desc = meta.description if meta else "Custom Alpha Factor"
            cat = meta.category if meta else "general"

            bias = "BULLISH" if latest_val > 0 else ("BEARISH" if latest_val < 0 else "NEUTRAL")
            color_dot = "🟢" if latest_val > 0 else ("🔴" if latest_val < 0 else "⚪")

            resp = (
                f"🧬 <b>Alpha Factor Evaluation: {factor_name.upper()}</b>\n\n"
                f"• Simbol: <code>{sym}</code>\n"
                f"• Kategori: <code>{cat}</code>\n"
                f"• Nilai Z-Score / Raw: <code>{latest_val:+.4f}</code>\n"
                f"• Implikasi: {color_dot} <b>{bias}</b>\n\n"
                f"<i>{html.escape(desc)}</i>"
            )
            await update.message.reply_text(resp, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.error(f"Error computing /alpha {factor_name} on {sym}: {exc}", exc_info=True)
            await update.message.reply_text(
                f"[ERROR] Gagal menghitung alpha <code>{factor_name}</code>: {html.escape(str(exc))}",
                parse_mode=ParseMode.HTML,
            )

    async def _cmd_pair(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Interactive DM pairing via out-of-band console OTP (/pair [code])."""
        if not update.message or not update.effective_user:
            return

        user_id = str(update.effective_user.id)
        username = update.effective_user.username
        args = ctx.args or []

        from monika.interfaces.gateway.pairing import get_pairing_manager

        mgr = get_pairing_manager()

        if mgr.is_user_paired("telegram", user_id):
            await update.message.reply_text("[BERHASIL] Akun Telegram Anda sudah terhubung (paired) dengan Monika.")
            return

        if not args:
            # Generate challenge and print to console
            user_msg, _ = mgr.create_pairing_request("telegram", user_id, username=username)
            await update.message.reply_text(user_msg, parse_mode=ParseMode.MARKDOWN)
            return

        # Attempt verification
        code_input = args[0].strip()
        success, reply_msg = mgr.verify_pairing_code("telegram", user_id, code_input)
        if success:
            if hasattr(self._router, "allowed_user_ids") and isinstance(self._router.allowed_user_ids, set):
                self._router.allowed_user_ids.add(int(user_id))
            await update.message.reply_text(
                f"[SELESAI] *Pairing Berhasil!*\n\n{reply_msg}\nAnda sekarang memiliki akses penuh ke Monika.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(reply_msg, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_vix(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        text = await self._build_vix_text()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_intel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        await update.message.chat.send_action(ChatAction.TYPING)

        from sqlalchemy import or_, select

        import monika.core.primitives.clock as clock
        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import UserMarketIntel

        now = clock.now()
        async with get_session() as session:
            stmt = (
                select(UserMarketIntel)
                .where(
                    UserMarketIntel.is_active == True,
                    or_(UserMarketIntel.expires_at.is_(None), UserMarketIntel.expires_at > now),
                )
                .order_by(UserMarketIntel.created_at.desc())
            )
            records = (await session.execute(stmt)).scalars().all()

        if not records:
            await update.message.reply_text(
                "[INFORMASI] *Tidak ada Market Intelligence aktif.*\nGunakan /research atau chat untuk melakukan riset dan menyimpan intel baru.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        lines = [f"[KEYAKINAN] *MARKET INTELLIGENCE AKTIF ({len(records)})*\n"]
        for r in records:
            symbols = (
                ", ".join(r.affected_symbols_list)
                if hasattr(r, "affected_symbols_list")
                else (r.affected_symbols or "ALL")
            )
            directive_str = f" | Directive: *{r.directive.upper()}*" if r.directive else ""
            target_cycle = f" | Target: {r.target_cycle}" if r.target_cycle else ""
            exp_str = r.expires_at.strftime("%Y-%m-%d %H:%M") if r.expires_at else "No expiry"

            lines.append(
                f"• *#{r.id}* [{r.intel_type.upper()}] *{r.title}*\n"
                f"  Aset: `{symbols}`{directive_str}{target_cycle}\n"
                f"  Exp: {exp_str}\n"
                f"  _{r.summary}_\n"
            )
        lines.append("_Gunakan `/archive_intel <id>` untuk menonaktifkan intel._")
        text = "\n".join(lines)
        for chunk in self._chunk_text(text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    async def _cmd_archive_intel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        if not ctx.args or not ctx.args[0].strip().isdigit():
            await update.message.reply_text(
                "Format: `/archive_intel <intel_id>`\nContoh: `/archive_intel 1`", parse_mode=ParseMode.MARKDOWN
            )
            return

        intel_id = int(ctx.args[0].strip())
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import ActivityLog, UserMarketIntel

        async with get_session() as session:
            stmt = select(UserMarketIntel).where(UserMarketIntel.id == intel_id)
            intel = (await session.execute(stmt)).scalar_one_or_none()
            if not intel:
                await update.message.reply_text(f"[GAGAL] Market Intelligence #{intel_id} tidak ditemukan.")
                return
            if not intel.is_active:
                await update.message.reply_text(f"[INFORMASI] Market Intelligence #{intel_id} sudah tidak aktif.")
                return

            intel.is_active = False
            user_id_str = str(update.effective_user.id) if update.effective_user else "unknown"
            session.add(
                ActivityLog(
                    category="intel",
                    description=f"Market Intelligence #{intel_id} deactivated via /archive_intel by user {user_id_str}",
                    actor="telegram_bot",
                )
            )
            await session.commit()

        await update.message.reply_text(
            f"[BERHASIL] Market Intelligence *#{intel_id}* berhasil dinonaktifkan.", parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_regime(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Deteksi rezim makro dan volatilitas terkini."""
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        symbol = ctx.args[0].upper().strip() if ctx.args else "XAUUSD"
        await update.message.reply_text(
            f"[TELUSURI] Menganalisis rezim pasar untuk *{symbol}*...", parse_mode=ParseMode.MARKDOWN
        )

        from sqlalchemy import desc, select

        from monika.application.analysis.calculators.regime_classifier import classify_market_regime
        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import FundamentalBrief, VIXData

        async with get_session() as session:
            try:
                regime_data = await classify_market_regime(session, symbol, settings=self.settings)
                final_regime = regime_data.get("regime", "UNKNOWN")
                quality = regime_data.get("composite_quality", 0.0)
                adx = regime_data.get("adx")
                vol_ratio = regime_data.get("vol_ratio")
            except Exception as e:
                final_regime = f"Calculated ({e})"
                quality = 0.0
                adx = None
                vol_ratio = None

            vix_row = (
                await session.execute(select(VIXData).order_by(desc(VIXData.date)).limit(1))
            ).scalar_one_or_none()
            vix_val = vix_row.close if vix_row else 15.0

            brief_row = (
                await session.execute(select(FundamentalBrief).order_by(desc(FundamentalBrief.generated_at)).limit(1))
            ).scalar_one_or_none()
            macro_sentiment = (brief_row.risk_sentiment or "neutral") if brief_row else "neutral"

        lines = [
            f"[LAPORAN] *Rezim Pasar & Volatilitas* — `{symbol}`",
            f"• *Rezim Komposit:* `{final_regime}`",
            f"• *Kualitas Sinyal:* `{quality:.2f}`",
            f"• *ADX Trend Strength:* `{adx if adx is not None else 'N/A'}`",
            f"• *Rasio Ekspansi Volatilitas:* `{vol_ratio:.2f}`" if vol_ratio else "• *Rasio Volatilitas:* `N/A`",
            f"• *VIX Indeks:* `{vix_val:.2f}`",
            f"• *Sentimen Makro Global:* `{macro_sentiment.upper()}`",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_backtest(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)
        if not self._is_admin(update):
            return await self._reject_non_admin(update)

        days = 30
        mode = "full"
        equity = 10000.0

        if ctx.args:
            try:
                days = int(ctx.args[0])
                if days <= 0 or days > 365:
                    await update.message.reply_text("[GAGAL] Parameter hari harus antara 1 dan 365.")
                    return
            except ValueError:
                await update.message.reply_text(
                    "[GAGAL] Format salah. Contoh: `/backtest 30 [mode] [equity]`", parse_mode=ParseMode.MARKDOWN
                )
                return

            if len(ctx.args) > 1:
                arg_mode = ctx.args[1].lower()
                if arg_mode in ("full", "replay", "walk_forward", "langgraph_parity"):
                    mode = arg_mode

            if len(ctx.args) > 2:
                try:
                    equity = float(ctx.args[2])
                except ValueError:
                    pass

        await update.message.reply_text(
            f"[MEMPROSES] *Memulai Point-in-Time Backtest ({days} hari)...*\n\n"
            f"Proses berjalan di background. Anda akan menerima notifikasi ringkasan setelah selesai.",
            parse_mode=ParseMode.MARKDOWN,
        )
        if mode == "full" and equity == 10000.0:
            asyncio.create_task(self._run_backtest_and_notify(update, days))
        else:
            asyncio.create_task(self._run_backtest_and_notify(update, days, mode=mode, initial_equity=equity))

    async def _run_backtest_and_notify(
        self, update: Update, days: int, mode: str = "full", initial_equity: float = 10000.0
    ) -> None:
        if not update.message:
            return
        try:
            from typing import cast

            from monika.application.backtest.point_in_time_engine import BacktestMode, PointInTimeBacktestEngine
            from monika.application.backtest.walk_forward_engine import WalkForwardEngine

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            if mode == "walk_forward":
                engine = WalkForwardEngine(
                    start_date=start_time,
                    end_date=end_time,
                    settings=self.settings,
                    mode="full",
                )
                result = await engine.run()
                msg = (
                    f"[BERHASIL] <b>Walk-Forward Optimization Selesai!</b>\n\n"
                    f"Overall WFE: <b>{result.overall_wfe:.2f}</b>\n"
                    f"IS Sharpe: {result.aggregate_is_sharpe:.2f}\n"
                    f"OOS Sharpe: {result.aggregate_oos_sharpe:.2f}\n"
                    f"OOS Trades: {result.total_oos_trades}\n"
                    f"Overfit: {'[PERINGATAN] YES' if result.is_overfit else '[BERHASIL] NO'}\n"
                )
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
                return

            bt_mode: BacktestMode = (
                cast(BacktestMode, mode) if mode in ("full", "replay", "langgraph_parity", "graph") else "full"
            )
            engine = PointInTimeBacktestEngine(
                start_time, end_time, self.settings, mode=bt_mode, initial_equity=initial_equity
            )
            run_record = await engine.run()

            # Calculate by_symbol aggregation manually
            by_symbol = {}
            for t in engine.trades:
                sym = t.symbol
                if sym not in by_symbol:
                    by_symbol[sym] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
                by_symbol[sym]["trades"] += 1
                if (t.pnl_pct or 0) > 0:
                    by_symbol[sym]["wins"] += 1
                by_symbol[sym]["total_pnl"] += t.pnl_pct or 0

            for sym, data in by_symbol.items():
                data["win_rate"] = round((data["wins"] / data["trades"]) * 100, 2)

            total_pnl_pct = 0.0
            if run_record.initial_equity and run_record.final_equity is not None and run_record.initial_equity > 0:
                total_pnl_pct = (
                    (run_record.final_equity - run_record.initial_equity) / run_record.initial_equity
                ) * 100

            msg = (
                f"[BERHASIL] <b>Backtest {days} hari Selesai!</b>\n\n"
                f"<b>[LAPORAN] PERFORMANCE REPORT:</b>\n"
                f"Total trades: {run_record.total_trades}\n"
                f"Win rate: {float(run_record.win_rate or 0.0):.2f}%\n"
            )
            if hasattr(run_record, "profit_factor") and isinstance(run_record.profit_factor, (int, float)):
                msg += f"Profit Factor: {run_record.profit_factor:.2f}\n"
            if hasattr(run_record, "sharpe_ratio") and isinstance(run_record.sharpe_ratio, (int, float)):
                msg += f"Sharpe (Ann): {run_record.sharpe_ratio:.2f}\n"
            if hasattr(run_record, "max_drawdown_pct") and isinstance(run_record.max_drawdown_pct, (int, float)):
                msg += f"Max Drawdown: {run_record.max_drawdown_pct:.2f}%\n"
            msg += f"Total PnL: {total_pnl_pct:+.2f}%\n\n"
            msg += "<b>By Symbol:</b>\n"
            for sym, data in by_symbol.items():
                msg += f"• {sym}: {data['trades']} trades, {data['win_rate']}% WR, {data['total_pnl']:+.2f}% PnL\n"

            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Backtest gagal: {e}")

    async def _cmd_calendar(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not self._is_authorized(update):
            return await self._reject_unauthorized(update)

        from sqlalchemy import select

        from monika.infrastructure.database.db import AsyncSessionLocal
        from monika.infrastructure.database.models import EconomicCalendar

        currency = ctx.args[0].upper() if ctx.args else None
        now = datetime.now(timezone.utc)
        until = now + timedelta(hours=36)

        try:
            async with AsyncSessionLocal() as session:
                q = select(EconomicCalendar).where(
                    EconomicCalendar.event_time >= now - timedelta(hours=2), EconomicCalendar.event_time <= until
                )
                if currency:
                    q = q.where(EconomicCalendar.currency.contains(currency))
                q = q.order_by(EconomicCalendar.event_time.asc()).limit(15)
                events = (await session.execute(q)).scalars().all()

                if not events:
                    filter_txt = f" untuk {currency}" if currency else ""
                    await update.message.reply_text(
                        f"[INFORMASI] Tidak ada event kalender signifikan dalam 36 jam ke depan{filter_txt}."
                    )
                    return

                lines = ["[KALENDER] <b>Jadwal Kalender Ekonomi Makro (Next 36h):</b>\n"]
                for e in events:
                    impact_emoji = (
                        "[KRITIS]"
                        if (e.impact or "").lower() == "high"
                        else "[WASPADA]"
                        if (e.impact or "").lower() == "medium"
                        else "[NONAKTIF]"
                    )
                    t_str = e.event_time.strftime("%d %b %H:%M UTC") if e.event_time else "TBD"
                    act = f" | Act: {e.actual}" if e.actual else ""
                    fcst = f" | Fct: {e.forecast}" if e.forecast else ""
                    lines.append(
                        f"{impact_emoji} <b>[{e.currency}]</b> {e.event_name}\n   [WAKTU] <code>{t_str}</code>{fcst}{act}"
                    )

                await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error fetching calendar: {e}", exc_info=True)
            await update.message.reply_text(f"[GAGAL] Gagal memuat kalender ekonomi: {e}")


__all__ = [
    "MarketCommandDescriptor",
    "MARKET_COMMAND_DESCRIPTORS",
    "TelegramMarketCommandsMixin",
]
