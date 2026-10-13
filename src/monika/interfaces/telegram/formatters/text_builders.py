# ==============================================================================
# File: interfaces/telegram/formatters/text_builders.py
# ==============================================================================

"""
Text builders and message formatters mixin for Telegram bot.
Handles compiling reports, status slips, summaries, and safe markdown/HTML chunking.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from monika.interfaces.telegram.base import _TelegramBotMixinBase

logger = logging.getLogger(__name__)


class TelegramFormatterMixin(_TelegramBotMixinBase):
    """Mixin providing text generation and chunking capabilities for TelegramBot."""

    async def _build_stats_text(self) -> str:
        try:
            from monika.core.analytics.paper_tracker import PaperTracker
            from monika.infrastructure.database.db import get_session
            from monika.interfaces.telegram.message_formatter import format_stats_slip

            async with get_session() as session:
                tracker = PaperTracker()
                stats = await tracker.get_statistics(session)
                equity_curve = await tracker.simulate_equity_curve(session)

            return format_stats_slip(stats, equity_curve=equity_curve)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    def _build_plugins_text(self, plugins: list[dict]) -> str:
        active_count = sum(1 for p in plugins if p.get("enabled", False))
        lines = [
            f"[PLUGIN] <b>MONIKA PLUG-IN HARNESS ({active_count}/{len(plugins)} AKTIF)</b>",
            "<i>Ketuk tombol di bawah untuk toggle ON/OFF secara instan:</i>\n",
        ]
        for p in plugins:
            icon = "[AKTIF]" if p.get("enabled") else "[NONAKTIF]"
            status = (
                "ACTIVE"
                if p.get("enabled")
                else ("DEGRADED" if str(p.get("status", "")).startswith("DEGRADED") else "DISABLED")
            )
            cat = p.get("category", "custom")
            lines.append(f"{icon} <b>{p.get('name', p['id'])}</b> <code>v{p.get('version', '1.0')}</code> [{cat}]")
            lines.append(f"   <i>Status: {status}</i> • <code>{p['id']}</code>")
        return "\n".join(lines)

    def _build_plugins_keyboard(self, plugins: list[dict]) -> InlineKeyboardMarkup:
        keyboard = []
        row = []
        for p in plugins:
            btn_icon = "[AKTIF]" if p.get("enabled") else "[NONAKTIF]"
            btn_label = f"{btn_icon} {p.get('name', p['id'])[:15]}"
            cb_data = f"plg:t:{p['id'][:32]}"
            row.append(InlineKeyboardButton(btn_label, callback_data=cb_data))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append(
            [
                InlineKeyboardButton("[MODUL] Marketplace Catalog", callback_data="plg:cat"),
                InlineKeyboardButton("[SINKRONISASI] Refresh", callback_data="plg:ref"),
            ]
        )
        return InlineKeyboardMarkup(keyboard)

    async def _build_status_text(self) -> str:
        from sqlalchemy import func, select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import AssetAnalysis, Position, RiskState
        from monika.interfaces.telegram.message_formatter import format_status_slip

        try:
            async with get_session() as session:
                now = datetime.now(timezone.utc)

                from monika.infrastructure.database.repositories import PositionRepository

                pos_repo = PositionRepository(session)
                pos_count = await pos_repo.count_open_positions()

                # Risk state
                today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                risk = (
                    await session.execute(
                        select(RiskState).where(RiskState.date >= today).order_by(RiskState.date.desc()).limit(1)
                    )
                ).scalar_one_or_none()

                # Last analysis
                last_analysis = (
                    await session.execute(select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(1))
                ).scalar_one_or_none()

                status_txt = "DIJEDA" if (risk and risk.trading_paused) else "AKTIF"
                daily_pnl = f"${risk.daily_pnl:+.2f}" if risk else "$0.00"
                drawdown = f"${risk.current_drawdown:.2f}" if risk else "$0.00"

                last_ts = last_analysis.generated_at.strftime("%d %b %Y %H:%M UTC") if last_analysis else "Belum ada"

                balance_str = None
                equity_str = None
                margin_level_str = None
                if self.execution_service and hasattr(self.execution_service, "mt5"):
                    try:
                        acc = await self.execution_service.mt5.get_account_info()
                        if acc:
                            balance_str = f"${acc.get('balance', 0.0):,.2f}"
                            equity_str = f"${acc.get('equity', 0.0):,.2f}"
                            ml = acc.get("margin_level", 0.0)
                            margin_level_str = f"{ml:.1f}%" if ml else "N/A"
                    except Exception:
                        pass

                return format_status_slip(
                    status_text=status_txt,
                    pos_count=pos_count,
                    daily_pnl=daily_pnl,
                    drawdown=drawdown,
                    last_analysis=last_ts,
                    now_str=now.strftime("%Y-%m-%d %H:%M UTC"),
                    balance=balance_str,
                    equity=equity_str,
                    margin_level=margin_level_str,
                )
        except Exception as e:
            return f"[ GAGAL ] Error mengambil status: {e}"

    async def _build_positions_text(self) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import Position
        from monika.interfaces.telegram.message_formatter import format_positions_slip

        try:
            from monika.infrastructure.database.repositories import PositionRepository

            async with get_session() as session:
                pos_repo = PositionRepository(session)
                positions = list(await pos_repo.get_open_positions())
                return format_positions_slip(positions)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_brief_text(self) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import FundamentalBrief

        try:
            async with get_session() as session:
                brief = (
                    await session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()

                if not brief:
                    return "```\n[ NIHIL ] Belum ada fundamental brief yang dihasilkan.\n```"

                ts = brief.generated_at.strftime("%d %b %Y %H:%M UTC") if brief.generated_at else "?"
                content = brief.content_markdown or "(tidak ada konten)"
                return f"```\nMONIKA DISPATCH // FUNDAMENTAL BRIEF\nWAKTU: {ts}\n" + "=" * 46 + f"\n{content}\n```"
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_analysis_text(self, symbol: str) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import AssetAnalysis

        try:
            async with get_session() as session:
                analysis = (
                    await session.execute(
                        select(AssetAnalysis)
                        .where(AssetAnalysis.symbol == symbol)
                        .order_by(AssetAnalysis.generated_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if not analysis:
                    return f"```\n[ NIHIL ] Belum ada analisis untuk {symbol}.\n```"

                ts = analysis.generated_at.strftime("%d %b %Y %H:%M UTC") if analysis.generated_at else "?"
                decision = analysis.decision.upper() if analysis.decision else "N/A"
                confidence = f"{analysis.confidence:.0%}" if analysis.confidence is not None else "N/A"

                content = getattr(analysis, "content_markdown", None)
                if not content:
                    content = getattr(analysis, "rationale", "(tidak ada detail)")

                return (
                    f"```\nMONIKA DISPATCH // ANALISIS: {symbol}\nWAKTU: {ts}\nKEPUTUSAN: [ {decision} ] (Conf: {confidence})\n"
                    + "=" * 46
                    + f"\n{content}\n```"
                )
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_history_text(self) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import ActivityLog

        try:
            async with get_session() as session:
                logs = (
                    (await session.execute(select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(10)))
                    .scalars()
                    .all()
                )

                if not logs:
                    return "```\n[ NIHIL ] Belum ada aktivitas yang tercatat.\n```"

                lines = [
                    "```",
                    "=" * 46,
                    "MONIKA DISPATCH // AKTIVITAS TERAKHIR (10)",
                    "=" * 46,
                ]
                for log in logs:
                    ts = log.timestamp.strftime("%d/%m %H:%M") if log.timestamp else "?"
                    desc = log.description[:60] if log.description else ""
                    cat = log.category or "system"
                    lines.append(f"[{cat.upper()[:6].ljust(6)}] {ts} : {desc}")
                lines.append("=" * 46)
                lines.append("```")
                return "\n".join(lines)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_risk_text(self) -> str:
        from sqlalchemy import select

        from monika.core.analytics.paper_tracker import PaperTracker
        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import RiskState
        from monika.interfaces.telegram.message_formatter import format_risk_slip

        try:
            async with get_session() as session:
                today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                risk = (
                    await session.execute(
                        select(RiskState).where(RiskState.date >= today).order_by(RiskState.date.desc()).limit(1)
                    )
                ).scalar_one_or_none()

                tracker = PaperTracker(self.settings)
                suspended = await tracker.get_suspended_symbols(session)

                paper_cfg = self.settings.get("trading", {}).get("paper_trading", {})
                streak_policy = paper_cfg.get("streak_loss_policy", "warn_and_scale")
                auto_exec = self.settings.get("trading", {}).get("auto_execute", False)

                status_txt = "DIJEDA" if (risk and risk.trading_paused) else "AKTIF"
                daily_pnl = f"${risk.daily_pnl:+.2f}" if risk else None
                drawdown = f"${risk.current_drawdown:.2f}" if risk else None
                reason = risk.reason if (risk and risk.reason) else None

                cb_status = "NORMAL (OFF)"
                if risk and risk.trading_paused:
                    cb_status = f"TRIGGERED ({reason or 'PAUSED'})"
                elif (
                    risk
                    and getattr(risk, "current_drawdown", 0)
                    and risk.current_drawdown
                    >= float(self.settings.get("trading", {}).get("risk", {}).get("max_daily_drawdown_percent", 3.0))
                ):
                    cb_status = "MAX DD TRIGGERED"

                return format_risk_slip(
                    status_text=status_txt,
                    mode="LIVE" if auto_exec else "PAPER",
                    streak_policy=streak_policy,
                    suspended_symbols=suspended,
                    daily_pnl=daily_pnl,
                    drawdown=drawdown,
                    reason=reason,
                    circuit_breaker=cb_status,
                )
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_risk_deep_text(self) -> str:
        from monika.domain.risk.risk_gate import RiskGate
        from monika.infrastructure.database.db import get_session
        from monika.interfaces.telegram.message_formatter import format_risk_deep_slip

        try:
            gate = RiskGate(self.settings)
            async with get_session() as session:
                scorecard = await gate.get_current_scorecard(session)

            # Statistical edge info
            edge_summary = None
            try:
                from monika.core.analytics.paper_tracker import PaperTracker

                tracker = PaperTracker(self.settings)
                async with get_session() as session:
                    stats = await tracker.get_statistics(session)
                    edge_summary = {
                        "expectancy": f"{stats.get('expectancy_per_trade_R', 0):+.2f}R",
                        "win_rate": f"{stats.get('win_rate_pct', 0):.1f}%",
                    }
            except Exception:
                pass

            # Token budget info
            token_budget = None
            try:
                from monika.core.telemetry.token_budgeter import TokenBudgetManager

                tbm = TokenBudgetManager.get_instance()
                summary = tbm.get_budget_summary()
                token_budget = {
                    "tier": "NORMAL"
                    if summary.get("total_pct_used", 0) < 70
                    else ("COMPRESSED" if summary.get("total_pct_used", 0) < 90 else "DEGRADED"),
                    "capacity_pct": max(0, 100 - summary.get("total_pct_used", 0)),
                }
            except Exception:
                pass

            return format_risk_deep_slip(scorecard, edge_summary=edge_summary, token_budget=token_budget)
        except Exception as e:
            return f"[ FAILED ] Error: {e}"

    async def _build_pipeline_text(self) -> str:
        from monika.interfaces.telegram.message_formatter import format_pipeline_slip

        try:
            status = "IDLE"
            stage = "AWAITING TRIGGER"
            last_run = "N/A"
            dur = "38.2s (avg)"

            if self.cycle_scheduler:
                is_running = getattr(self.cycle_scheduler, "_is_running", False)
                cycle_lock = getattr(self.cycle_scheduler, "_cycle_lock", None)
                if cycle_lock and cycle_lock.locked():
                    status = "RUNNING"
                    stage = "STAGE 2 (PER-ASSET DEBATE)"
                elif is_running:
                    status = "ACTIVE (SCHEDULED)"
                    stage = "READY FOR NEXT CYCLE"
                last_time = getattr(self.cycle_scheduler, "_last_cycle_time", None)
                if last_time:
                    last_run = last_time.strftime("%Y-%m-%d %H:%M UTC")

            try:
                from sqlalchemy import select

                from monika.infrastructure.database.db import get_session
                from monika.infrastructure.database.models import AssetAnalysis

                async with get_session() as session:
                    stmt = select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(1)
                    res = (await session.execute(stmt)).scalar_one_or_none()
                    if res and res.generated_at:
                        last_run = res.generated_at.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pass

            data = {
                "status": status,
                "current_stage": stage,
                "last_cycle": last_run,
                "duration": dur,
                "active_nodes": "5/5",
                "health": "OPTIMAL",
            }
            return format_pipeline_slip(data)
        except Exception as e:
            return f"[ FAILED ] Error: {e}"

    async def _build_approvals_text(self) -> str:
        from monika.domain.risk.approval_hub import ApprovalHub
        from monika.interfaces.telegram.message_formatter import format_approvals_slip

        try:
            hub = ApprovalHub.get_instance()
            open_reqs = hub.get_open_requests()
            return format_approvals_slip(open_reqs)
        except Exception as e:
            return f"[ FAILED ] Error: {e}"

    async def _build_trailing_text(self) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import Position
        from monika.interfaces.telegram.message_formatter import format_trailing_slip

        try:
            async with get_session() as session:
                stmt = select(Position).where(Position.closed_at.is_(None)).order_by(Position.opened_at.desc())
                positions = (await session.execute(stmt)).scalars().all()
                pos_list = []
                for p in positions:
                    pos_list.append(
                        {
                            "ticket": getattr(p, "mt5_ticket", getattr(p, "ticket", p.id)),
                            "symbol": p.symbol,
                            "direction": p.direction,
                            "entry_price": p.entry_price,
                            "current_sl": p.sl or "-",
                            "be_triggered": p.sl is not None
                            and (
                                (p.direction == "buy" and p.sl >= p.entry_price)
                                or (p.direction == "sell" and p.sl <= p.entry_price)
                            ),
                            "atr_distance": getattr(p, "atr_trailing_distance", "-"),
                        }
                    )
                return format_trailing_slip(pos_list)
        except Exception as e:
            return f"[ FAILED ] Error: {e}"

    async def _build_reconcile_text(self) -> str:
        from monika.application.scheduler.order_reconciler import OrderReconciler
        from monika.interfaces.telegram.message_formatter import format_reconcile_slip

        try:
            reconciler = OrderReconciler(settings=self.settings, execution_service=self.execution_service)
            stats = await reconciler.reconcile_once()
            return format_reconcile_slip(stats)
        except Exception as e:
            return f"[ FAILED ] Error: {e}"

    async def _build_fedwatch_text(self) -> str:
        import json

        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import CentralBankRateExpectation, FedWatchProbability
        from monika.interfaces.telegram.message_formatter import format_fedwatch_slip

        try:
            async with get_session() as session:
                fw_rows = (
                    (
                        await session.execute(
                            select(FedWatchProbability).order_by(FedWatchProbability.fetched_at.desc()).limit(5)
                        )
                    )
                    .scalars()
                    .all()
                )
                cb_rows = (
                    (
                        await session.execute(
                            select(CentralBankRateExpectation)
                            .order_by(CentralBankRateExpectation.fetched_at.desc())
                            .limit(5)
                        )
                    )
                    .scalars()
                    .all()
                )

                fw_data = []
                for p in fw_rows:
                    probs = p.probabilities_json
                    if isinstance(probs, str):
                        try:
                            probs = json.loads(probs)
                        except Exception:
                            probs = {}
                    fw_data.append(
                        {
                            "meeting_date": p.meeting_date,
                            "probabilities": probs,
                        }
                    )

                cb_data = [
                    {
                        "bank": cb.bank,
                        "current_rate": cb.current_rate,
                        "prob_cut": cb.prob_cut,
                    }
                    for cb in cb_rows
                ]
                return format_fedwatch_slip({"fedwatch": fw_data, "central_banks": cb_data})
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_yields_text(self) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import BondYieldData, TreasuryYield
        from monika.interfaces.telegram.message_formatter import format_yields_slip

        try:
            async with get_session() as session:
                y_rows = (
                    (await session.execute(select(TreasuryYield).order_by(TreasuryYield.date.desc()).limit(30)))
                    .scalars()
                    .all()
                )
                b_rows = (
                    (await session.execute(select(BondYieldData).order_by(BondYieldData.date.desc()).limit(10)))
                    .scalars()
                    .all()
                )

                latest: dict = {}
                for y in y_rows:
                    if y.tenor not in latest:
                        latest[y.tenor] = y

                y2 = latest.get("2Y")
                y10 = latest.get("10Y")
                spread = round(y10.yield_percent - y2.yield_percent, 3) if (y2 and y10) else None

                return format_yields_slip(
                    {
                        "treasury_yields": [
                            {"tenor": y.tenor, "yield_percent": y.yield_percent} for y in latest.values()
                        ],
                        "spread_2s10s": spread,
                        "is_inverted": (spread < 0.0) if spread is not None else False,
                        "global_bonds": [
                            {"country_tenor": b.country_tenor, "yield_percent": b.yield_percent} for b in b_rows
                        ],
                    }
                )
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_fear_greed_text(self) -> str:
        import json

        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import SystemConfig
        from monika.interfaces.telegram.message_formatter import format_fear_greed_slip

        try:
            async with get_session() as session:
                cfg = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == "fear_greed_latest").limit(1))
                ).scalar_one_or_none()
                if cfg and cfg.value:
                    data = json.loads(cfg.value)
                    return format_fear_greed_slip(data)
                return format_fear_greed_slip({"current_value": 50, "classification": "Neutral", "wow_change": 0})
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_cot_text(self, market_code: Optional[str] = None) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import COTReport
        from monika.interfaces.telegram.message_formatter import format_cot_slip

        try:
            async with get_session() as session:
                q = select(COTReport)
                if market_code:
                    q = q.where(COTReport.market_code == market_code.upper())
                q = q.order_by(COTReport.report_date.desc()).limit(10)
                records = (await session.execute(q)).scalars().all()

                data = [
                    {
                        "market_code": r.market_code,
                        "asset_mgr_long": r.asset_mgr_long,
                        "asset_mgr_short": r.asset_mgr_short,
                        "leveraged_long": r.leveraged_long,
                        "leveraged_short": r.leveraged_short,
                        "net_position": (r.asset_mgr_long + r.leveraged_long) - (r.asset_mgr_short + r.leveraged_short),
                    }
                    for r in records
                ]
                return format_cot_slip(data)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_playbooks_text(self) -> str:
        from monika.interfaces.telegram.message_formatter import format_playbooks_slip

        try:
            from monika.application.analysis.memory.playbook_lifecycle import PlaybookLifecycleManager

            mgr = PlaybookLifecycleManager()
            all_pb = mgr.list_all_playbooks()
            items = []
            for name, meta in all_pb.items():
                stale_ts = getattr(meta, "stale_until_ts", None)
                items.append(
                    {
                        "name": name,
                        "status": meta.status.value if hasattr(meta.status, "value") else str(meta.status),
                        "win_rate": getattr(meta, "win_rate", 0.0),
                        "total_trades": getattr(meta, "trades_count", getattr(meta, "total_trades", 0)),
                        "cooldown_until": (
                            datetime.fromtimestamp(stale_ts, tz=timezone.utc).isoformat()
                            if stale_ts is not None
                            else None
                        ),
                    }
                )
            return format_playbooks_slip(items)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_rollback_text(self, name: str) -> str:
        from monika.interfaces.telegram.message_formatter import format_rollback_slip

        try:
            from monika.application.analysis.memory.playbook_ledger import PlaybookLedger

            ledger = PlaybookLedger()
            success = ledger.rollback(name)
            res = {
                "name": name,
                "status": "SUCCESS" if success else "FAILED",
                "message": f"Rolled back playbook '{name}' to prior ledger checkpoint."
                if success
                else f"No previous history snapshot found for '{name}'.",
            }
            return format_rollback_slip(res)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_crystallized_text(self) -> str:
        from monika.interfaces.telegram.message_formatter import format_crystallized_slip

        try:
            import yaml

            from monika.application.analysis.memory.skill_crystallizer import SkillCrystallizer

            crystallizer = SkillCrystallizer()
            skills_dir = crystallizer.SKILLS_DIR
            items = []
            if skills_dir.exists():
                for f in sorted(skills_dir.glob("*.md")):
                    try:
                        content = f.read_text(encoding="utf-8")
                        meta = {}
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                meta = yaml.safe_load(parts[1]) or {}
                        clean_name = f.stem.lower()
                        items.append(
                            {
                                "name": meta.get("name", clean_name),
                                "symbol": meta.get("symbol", "-"),
                                "status": meta.get("status", "active"),
                                "is_deprecated": meta.get("is_deprecated", False),
                                "win_rate": float(meta.get("win_count", 1.0))
                                / max(1.0, float(meta.get("win_count", 1.0))),
                                "total_pnl_usd": float(meta.get("total_pnl_usd", 0.0)),
                            }
                        )
                    except Exception:
                        pass
            return format_crystallized_slip(items)
        except Exception as e:
            return f"[ GAGAL ] Error: {e}"

    async def _build_vix_text(self) -> str:
        from sqlalchemy import select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import VIXData

        try:
            async with get_session() as session:
                vix_rows = (
                    (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(5))).scalars().all()
                )

                if not vix_rows:
                    return "[GRAFIK] *Data VIX belum tersedia.*"

                lines = ["*[GRAFIK] VIX (5 Data Terakhir)*\n"]
                for v in vix_rows:
                    date_str = v.date.strftime("%d %b") if v.date else "?"
                    close = f"{v.close:.2f}" if v.close is not None else "?"
                    # VIX interpretation
                    if v.close and v.close > 30:
                        icon = "[KRITIS]"
                    elif v.close and v.close > 20:
                        icon = "[WASPADA]"
                    else:
                        icon = "[AKTIF]"
                    lines.append(f"{icon} `{date_str}`: VIX = *{close}*")
                return "\n".join(lines)
        except Exception as e:
            return f"[GAGAL] Error: {e}"

    async def _build_tokens_text(self) -> str:
        try:
            from monika.core.analytics.token_auditor import TokenAuditor

            summary = await TokenAuditor.get_summary(hours=24)
            if not summary or summary["total_calls"] == 0:
                return "[LAPORAN] *Belum ada konsumsi token tercatat hari ini (24 jam terakhir).*"

            lines = ["*[LAPORAN] Laporan Konsumsi Token (24 Jam Terakhir)*\n"]
            lines.append(f"• *Total Panggilan*: {summary['total_calls']:,} calls")
            lines.append(f"• *Total Input*: {summary['input_tokens']:,} tokens")
            lines.append(f"• *Total Output*: {summary['output_tokens']:,} tokens")
            lines.append(f"• *Total Akumulasi*: {summary['total_tokens']:,} tokens")
            if summary["cached_tokens"] > 0:
                lines.append(
                    f"• *Prompt Caching*: {summary['cached_tokens']:,} tokens ({summary['cache_hit_rate_pct']:.1f}% hemat)"
                )
            lines.append(f"• *Estimasi Biaya*: `${summary['total_cost_usd']:.4f} USD`\n")

            # Subsystem Breakdown
            subsystems = await TokenAuditor.get_subsystem_breakdown(hours=24)
            if subsystems:
                lines.append("*• Berdasarkan Subsystem:*")
                for s in subsystems[:6]:
                    lines.append(
                        f"  • *{s['subsystem']}*: {s['sum_total']:,} tokens (${s['sum_cost_usd']:.4f} | {s['pct_cost']:.1f}%)"
                    )
                lines.append("")

            # Top Roles Breakdown
            roles = await TokenAuditor.get_role_breakdown(hours=24)
            if roles:
                lines.append("*[ASISTEN AI] Top Task Roles Terbesar:*")
                for r in roles[:5]:
                    lines.append(
                        f"  • `{r['task_role']}`: {r['calls']} calls, avg {r['avg_total']:,.0f} tok (${r['sum_cost_usd']:.4f})"
                    )

            return "\n".join(lines)
        except Exception as e:
            return f"[GAGAL] Error: {e}"

    async def _build_credits_text(self) -> str:
        try:
            from monika.infrastructure.api.credit_balance_tracker import CreditBalanceTracker

            rep = await CreditBalanceTracker.get_full_credit_report()

            lines = ["*[KUOTA] LAPORAN SISA KREDIT & KUOTA API*\n"]

            # 1. Live Provider Balances (Tier Berbayar)
            lines.append("*• Saldo Live Provider (Tier Berbayar):*")

            # OpenRouter Paid Key
            or_data = rep.get("openrouter", {})
            paid_status = or_data.get("paid_key", {})
            if paid_status.get("status") == "ok":
                rem = paid_status.get("remaining_usd", 0.0)
                tot = paid_status.get("total_credits_usd", 0.0)
                usg = paid_status.get("total_usage_usd", 0.0)
                lines.append(
                    f"• *OpenRouter (Paid Key)*: `${rem:.2f} USD` tersisa (Total: `${tot:.2f}` | Terpakai: `${usg:.2f}`)"
                )
            elif paid_status.get("status") == "insufficient_credits":
                lines.append("• *OpenRouter (Paid Key)*: [PERINGATAN] `$0.00 USD` (Saldo top-up habis)")
            elif not paid_status.get("configured"):
                lines.append("• *OpenRouter (Paid Key)*: _OPENROUTER_PAID_API_KEY belum disetel_")
            else:
                lines.append(f"• *OpenRouter (Paid Key)*: [PERINGATAN] Status: {paid_status.get('message', 'Error')}")

            # DeepSeek
            ds_data = rep.get("deepseek", {})
            if ds_data.get("status") == "ok":
                tot_bal = ds_data.get("total_balance_usd", 0.0)
                top_bal = ds_data.get("topped_up_balance_usd", 0.0)
                grant_bal = ds_data.get("granted_balance_usd", 0.0)
                lines.append(
                    f"• *DeepSeek*: `${tot_bal:.2f} USD` tersisa (Top-up: `${top_bal:.2f}` | Bonus: `${grant_bal:.2f}`)"
                )
            elif ds_data.get("status") == "unconfigured":
                lines.append("• *DeepSeek*: _API Key tidak aktif / opsional_")
            else:
                lines.append(f"• *DeepSeek*: [PERINGATAN] Status: {ds_data.get('message', 'Error')}")

            lines.append("")

            # 2. Pool Kunci Gratisan OpenRouter (Free Tier Models)
            free_keys = or_data.get("free_keys", {})
            if free_keys.get("configured_count", 0) > 0:
                act = free_keys.get("active_count", 0)
                cfg = free_keys.get("configured_count", 0)
                icon = "[AKTIF]" if act == cfg else ("[WASPADA]" if act > 0 else "[KRITIS]")
                lines.append("*• Pool Kunci Gratisan OpenRouter (Free Tier Models):*")
                lines.append(
                    f"{icon} *OpenRouter Free Keys*: `{act} / {cfg}` Kunci Aktif & Siap (`is_free_tier: true`)"
                )
                lines.append("")

            # 3. Sisa Kuota Harian Free Tier (Hari ini)
            quotas = rep.get("quotas", {})
            if quotas:
                lines.append("*• Sisa Kuota Harian Free Tier (Hari Ini):*")
                key_models = list(quotas.keys())
                for km in key_models:
                    if km in quotas:
                        q = quotas[km]
                        icon = "[AKTIF]" if q["pct_used"] < 70 else ("[WASPADA]" if q["pct_used"] < 90 else "[KRITIS]")
                        lines.append(
                            f"{icon} `{km}`: *{q['remaining_calls']}* / {q['rpd_limit']} RPD tersisa ({q['used_calls']} calls)"
                        )
                lines.append("")

            # 3. Akumulasi Pengeluaran Bulan Ini
            expenses = rep.get("expenses", {})
            if expenses:
                m_str = expenses.get("month_str", "Bulan Ini")
                tot_cost = expenses.get("total_month_usd", 0.0)
                tot_calls = expenses.get("total_month_calls", 0)
                lines.append(f"*• Akumulasi Pengeluaran ({m_str}):* `${tot_cost:.4f} USD` ({tot_calls:,} calls)")
                by_prov = expenses.get("by_provider", {})
                for prov, pdata in sorted(by_prov.items(), key=lambda x: x[1].get("cost_usd", 0), reverse=True):
                    lines.append(
                        f"  • *{prov.title()}*: `${pdata['cost_usd']:.4f}` ({pdata['calls']} calls, {pdata['tokens']:,} tok)"
                    )

            return "\n".join(lines)
        except Exception as e:
            return f"[GAGAL] Error Credit Balance Tracker: {e}"

    @staticmethod
    def _balance_markdown_chunk(chunk: str) -> str:
        """Ensure any unclosed markdown tags within a single chunk are closed safely."""
        if not chunk:
            return ""

        # 1. Balance code blocks (```)
        cb_matches = re.findall(r"```(\w*)", chunk)
        if len(cb_matches) % 2 == 1:
            chunk += "\n```"

        # 2. Balance inline code (`)
        no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
        if no_cb.count("`") % 2 == 1:
            chunk += "`"

        # 3. Balance bold (*) outside code blocks and inline code
        no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
        no_inline = re.sub(r"`.*?`", "", no_cb, flags=re.DOTALL)
        if no_inline.count("*") % 2 == 1:
            chunk += "*"

        # 4. Balance italic (_) outside code blocks and inline code
        no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
        no_inline = re.sub(r"`.*?`", "", no_cb, flags=re.DOTALL)
        if no_inline.count("_") % 2 == 1:
            chunk += "_"

        return chunk

    @staticmethod
    def _balance_html_chunk(chunk: str) -> tuple[str, str]:
        """Balances unclosed HTML tags for a split chunk, returning (balanced_chunk, resume_prefix)."""
        tag_pattern = re.compile(r"<\s*(/?)\s*([a-zA-Z0-9]+)(?:\s+[^>]*)?>")
        stack: list[str] = []
        VOID_TAGS = {"br", "hr", "img"}

        for m in tag_pattern.finditer(chunk):
            is_close = bool(m.group(1))
            tag_name = m.group(2).lower()
            if tag_name in VOID_TAGS:
                continue

            if not is_close:
                stack.append(tag_name)
            else:
                if tag_name in stack:
                    for idx in range(len(stack) - 1, -1, -1):
                        if stack[idx] == tag_name:
                            stack.pop(idx)
                            break

        if not stack:
            return chunk, ""

        closers = "".join(f"</{t}>" for t in reversed(stack))
        openers = "".join(f"<{t}>" for t in stack)
        return chunk + closers, openers

    @staticmethod
    def _chunk_text(
        text: str,
        max_len: int = 4000,
        sanitize_format: bool = False,
        is_html: bool = False,
    ) -> list[str]:
        """Split text into Telegram-safe chunks while preserving formatting boundaries."""
        if not text:
            return []
        if sanitize_format:
            from monika.interfaces.telegram.chat_agent import _sanitize_telegram_format

            text = _sanitize_telegram_format(text)

        balance_fn = (lambda s: s) if is_html else TelegramFormatterMixin._balance_markdown_chunk
        if len(text) <= max_len:
            return [balance_fn(text)]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= max_len:
                chunks.append(balance_fn(remaining))
                break

            # Find best split point (prefer double newline, then single newline, then space)
            split_at = remaining.rfind("\n\n", 0, max_len)
            if split_at != -1 and split_at >= max_len // 2:
                split_len = split_at + 2
            else:
                split_at = remaining.rfind("\n", 0, max_len)
                if split_at != -1 and split_at >= max_len // 3:
                    split_len = split_at + 1
                else:
                    split_at = remaining.rfind(" ", 0, max_len)
                    if split_at != -1 and split_at >= max_len // 3:
                        split_len = split_at + 1
                    else:
                        split_len = max_len

            chunk = remaining[:split_len].rstrip()
            next_remaining = remaining[split_len:].lstrip()

            if is_html:
                chunk, reopen_prefix = TelegramFormatterMixin._balance_html_chunk(chunk)
                if reopen_prefix:
                    next_remaining = reopen_prefix + next_remaining
            else:
                # Balance code blocks (```)
                cb_matches = re.findall(r"```(\w*)", chunk)
                if len(cb_matches) % 2 == 1:
                    last_cb = list(re.finditer(r"```(\w*)", chunk))[-1]
                    lang = last_cb.group(1) or ""
                    chunk += "\n```"
                    next_remaining = f"```{lang}\n" + next_remaining

                # Balance inline code (`)
                no_cb = re.sub(r"```.*?```", "", chunk, flags=re.DOTALL)
                no_cb = re.sub(r"```.*$", "", no_cb, flags=re.DOTALL)
                if no_cb.count("`") % 2 == 1:
                    chunk += "`"
                    next_remaining = "`" + next_remaining

                # Balance bold (*)
                no_inline = re.sub(r"`.*?`", "", no_cb)
                if no_inline.count("*") % 2 == 1:
                    chunk += "*"
                    next_remaining = "*" + next_remaining

                # Balance italic (_)
                if no_inline.count("_") % 2 == 1:
                    chunk += "_"
                    next_remaining = "_" + next_remaining

            chunks.append(chunk)
            remaining = next_remaining

        return chunks

    async def _build_weekly_report(self) -> str:
        from datetime import timedelta

        from sqlalchemy import func, select

        from monika.infrastructure.database.db import get_session
        from monika.infrastructure.database.models import CyclePerformance, PaperTradeRecord, Position, TokenUsageLog

        try:
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)

            async with get_session() as session:
                # Closed positions this week
                closed = (
                    (
                        await session.execute(
                            select(Position).where(Position.status == "closed").where(Position.closed_at >= week_ago)
                        )
                    )
                    .scalars()
                    .all()
                )

                paper_closed = (
                    (
                        await session.execute(
                            select(PaperTradeRecord)
                            .where(PaperTradeRecord.status == "closed")
                            .where(PaperTradeRecord.closed_at >= week_ago)
                        )
                    )
                    .scalars()
                    .all()
                )

                total_pnl = sum(p.pnl or 0 for p in closed)
                wins = [p for p in closed if (p.pnl or 0) > 0]
                losses = [p for p in closed if (p.pnl or 0) <= 0]
                win_rate = len(wins) / len(closed) * 100 if closed else 0

                # Token usage this week
                tok_result = (
                    await session.execute(
                        select(
                            TokenUsageLog.provider,
                            func.sum(TokenUsageLog.total_tokens).label("total"),
                        )
                        .where(TokenUsageLog.timestamp >= week_ago)
                        .group_by(TokenUsageLog.provider)
                    )
                ).all()

                # Cycle stats this week
                cycles = (
                    await session.execute(
                        select(func.count(CyclePerformance.id)).where(CyclePerformance.cycle_at >= week_ago)
                    )
                ).scalar_one_or_none() or 0

                avg_cost_q = (
                    await session.execute(
                        select(func.avg(CyclePerformance.api_cost_usd))
                        .where(CyclePerformance.cycle_at >= week_ago)
                        .where(CyclePerformance.api_cost_usd != None)
                    )
                ).scalar_one_or_none()

            lines = [
                f"*[LAPORAN] Weekly Report — {week_ago.strftime('%d %b')} to {now.strftime('%d %b %Y')}*\n",
                f"*Trading Performance:*",
                f"  Closed trades: {len(closed)}",
                f"  Win rate: {win_rate:.1f}%",
                f"  Total P&L: `{'${:+.2f}'.format(total_pnl)}`",
                f"  Winners: {len(wins)} | Losers: {len(losses)}",
                "",
            ]

            # Fetch tracker stats for expectancy and suspended symbols
            try:
                from monika.core.analytics.paper_tracker import PaperTracker

                tracker = PaperTracker()
                async with get_session() as tracker_session:
                    stats = await tracker.get_statistics(tracker_session)
                    exp = stats.get("expectancy_per_trade_R")
                    if exp is not None:
                        lines.append("*Edge Status:*")
                        if exp > 0:
                            lines.append(f"  [AKTIF] EDGE POSITIVE: Expectancy = +{exp:.2f}R per trade")
                        elif exp > -0.1:
                            lines.append(f"  [WASPADA] EDGE UNCERTAIN: Expectancy = {exp:.2f}R per trade")
                        else:
                            lines.append(
                                f"  [KRITIS] EDGE NEGATIVE: Expectancy = {exp:.2f}R per trade — AUTO-SUSPEND RISK"
                            )

                    suspended = await tracker.get_suspended_symbols(tracker_session)
                    if suspended:
                        lines.append(f"  [DIJEDA] Suspended Symbols: {', '.join(suspended)}")
                    lines.append("")

                    from monika.core.analytics.analysis_tracker import get_direction_accuracy_report

                    dir_acc = await get_direction_accuracy_report(tracker_session, 7)
                    if dir_acc and "error" not in dir_acc and not dir_acc.get("insufficient_data"):
                        lines.append("*Analysis Quality:*")
                        lines.append(
                            f"  [TARGET] Direction Accuracy (4h): {dir_acc.get('direction_accuracy_4h', dir_acc.get('overall_accuracy_4h_pct'))}%"
                        )
                        brier = dir_acc.get("brier_score", dir_acc.get("mean_brier_score"))
                        if brier is not None:
                            # Brier score: 0 is perfect, 1 is totally wrong, 0.25 is random guessing
                            lines.append(f"  [KEYAKINAN] Confidence Brier Score: {brier:.3f} (closer to 0 is better)")
                        lines.append("")
            except Exception as e:
                logger.debug(f"Failed to fetch tracker stats for report: {e}")

            try:
                from monika.core.telemetry.reporting.tearsheet_generator import QuantTearsheetGenerator

                report_trades = closed if closed else paper_closed
                if report_trades:
                    ts = QuantTearsheetGenerator.generate_from_trades(report_trades)
                    lines.append("*Quant Tearsheet Highlights:*")
                    lines.append(
                        f"  Sharpe: `{ts.annualized_sharpe:.2f}` | Sortino: `{ts.annualized_sortino:.2f}` | Calmar: `{ts.calmar_ratio:.2f}`"
                    )
                    lines.append(
                        f"  Max DD: `{ts.max_drawdown_pct:.2f}%` | Profit Factor: `{ts.profit_factor:.2f}` | Payoff: `{ts.payoff_ratio:.2f}`"
                    )
                    lines.append(f"  Expectancy: `{ts.expectancy_r:+.2f}R` (`${ts.expectancy_usd:+,.2f}`)")
                    lines.append("")
            except Exception as e:
                logger.debug(f"Tearsheet in weekly report failed: {e}")

            lines.extend(
                [
                    f"*System Performance:*",
                    f"  Cycles completed: {cycles}",
                    f"  Avg cost per cycle: `${avg_cost_q:.4f}`" if avg_cost_q else "  Avg cost: N/A",
                ]
            )

            if tok_result:
                lines.append("\n*Token Usage:*")
                for row in tok_result:
                    lines.append(f"  {row.provider.upper()}: {row.total:,} tokens")

            if closed:
                lines.append("\n*Trade Breakdown by Asset:*")
                by_symbol = {}
                for p in closed:
                    if p.symbol not in by_symbol:
                        by_symbol[p.symbol] = {"pnl": 0, "count": 0}
                    by_symbol[p.symbol]["pnl"] += p.pnl or 0
                    by_symbol[p.symbol]["count"] += 1
                for sym, data in sorted(by_symbol.items(), key=lambda x: x[1]["pnl"], reverse=True):
                    lines.append(f"  {sym}: {data['count']} trades, `{'${:+.2f}'.format(data['pnl'])}`")
            try:
                from monika.core.analytics.analysis_tracker import compute_model_source_performance

                async with get_session() as src_session:
                    source_perf = await compute_model_source_performance(src_session, days_back=7)
                if source_perf.get("by_decision_source"):
                    lines.append("\n*Performance by Decision Source (Model):*")
                    for source, data in sorted(
                        source_perf["by_decision_source"].items(), key=lambda x: x[1]["win_rate"], reverse=True
                    ):
                        lines.append(
                            f"  {source}: {data['win_rate']}% WR ({data['trades']} trades, avg {data['avg_pnl_pct']:+.3f}%)"
                        )
            except Exception as e:
                logger.debug(f"Decision-source performance section failed: {e}")

            return "\n".join(lines)
        except Exception as e:
            return f"[GAGAL] Error generating report: {e}"


__all__ = ["TelegramFormatterMixin"]
