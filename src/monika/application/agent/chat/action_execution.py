# ==============================================================================
# File: application/agent/chat/action_execution.py
# ==============================================================================

"""
Trade action execution, order dispatcher, and database mutation execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import (
    ActivityLog,
    Position,
    RiskState,
)
from monika.application.agent.chat.base import _ChatAgentMixinBase, logger
from monika.application.agent.chat.pending_actions import PendingAction


class ActionExecutionMixin(_ChatAgentMixinBase):
    """Mixin handling action execution and database mutations."""

    async def _execute_action(self, action: PendingAction) -> str:
        """Meneruskan aksi yang dikonfirmasi ke ExecutionService."""
        from monika.application.execution.execution_service import ExecutionService
        from monika.core.config.settings import load_settings

        svc = getattr(self, "execution_service", None) or ExecutionService(self.settings)
        params = action.params

        if action.action_type == "place_order":
            # Build a minimal AssetAnalysis-like object for ExecutionService
            symbol = str(params.get("symbol") or "")
            direction = str(params.get("direction") or "")
            if not symbol or not direction:
                return "[GAGAL] Order ditolak: parameter 'symbol' dan 'direction' wajib diisi."

            async with get_session() as session:
                from monika.application.analysis.tools.tool_executor import ToolExecutor
                from monika.infrastructure.database.models import AssetAnalysis, FundamentalBrief

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
                    return (
                        f"[GAGAL] Order ditolak oleh validasi struktural (ADR-band/R:R/SL-TP alignment):\n"
                        + "\n".join(f"• {err}" for err in val_errs)
                    )

                # Slippage validation: Only apply price drift check to market orders. For limit/stop, validate entry side.
                order_type = str(params.get("order_type", "market")).lower()
                curr_price, is_stale, _ = await svc._get_current_price(symbol, direction)
                if is_stale:
                    return f"[GAGAL] Order ditolak: Data harga broker untuk {symbol} kedaluwarsa (stale price). Silakan periksa koneksi feed broker."
                if curr_price is None:
                    return f"[GAGAL] Order ditolak: Gagal mengambil harga pasar terkini untuk {symbol} dari broker."

                proposed_entry = params.get("entry_price")
                if order_type == "market":
                    if proposed_entry is None:
                        proposed_entry = curr_price
                        params["entry_price"] = curr_price
                    atr_res = await executor.execute("get_atr", {"symbol": symbol, "timeframe": "H1"})
                    atr = (atr_res.get("atr_14") if isinstance(atr_res, dict) else None) or (curr_price * 0.005)
                    max_allowed_slippage = atr * 0.5
                    price_drift = abs(curr_price - proposed_entry)
                    if price_drift > max_allowed_slippage:
                        return f"[GAGAL] Order kedaluwarsa karena harga bergerak melebihi batas toleransi slippage (0.5 ATR / {price_drift:.5f} vs max {max_allowed_slippage:.5f}). Silakan ajukan ulang."
                elif order_type in ("limit", "buy_limit", "sell_limit") and proposed_entry:
                    if direction == "buy" and proposed_entry >= curr_price:
                        return f"[GAGAL] Buy Limit entry ({proposed_entry:.5f}) harus berada di bawah harga pasar saat ini ({curr_price:.5f})."
                    elif direction == "sell" and proposed_entry <= curr_price:
                        return f"[GAGAL] Sell Limit entry ({proposed_entry:.5f}) harus berada di atas harga pasar saat ini ({curr_price:.5f})."

                brief = (
                    await session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )
                ).scalar_one_or_none()

                analysis = AssetAnalysis(
                    symbol=symbol,
                    generated_at=datetime.now(timezone.utc),
                    brief_id=brief.id if brief else None,
                    decision=direction,
                    confidence=params.get("confidence", 0.7),
                    entry_zone=json.dumps(
                        {
                            "type": params.get("order_type", "market"),
                            "price": params.get("entry_price"),
                        }
                    ),
                    stop_loss=params.get("stop_loss"),
                    take_profit=params.get("take_profit"),
                    rationale=params.get("rationale", "Proposed via Telegram chat (Structural Validation Passed)"),
                    reevaluation_trigger=json.dumps({"type": "time", "detail": "Re-evaluate in 6h"}),
                )
                session.add(analysis)
                await session.flush()

                result = await svc.execute_analysis(
                    session,
                    analysis,
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
                    from monika.infrastructure.storage.journal_helper import record_trade_to_workspace

                    j_res = record_trade_to_workspace(
                        self.settings,
                        {
                            "symbol": result.symbol,
                            "action": result.decision.upper(),
                            "volume": result.executed_lots,
                            "price": result.executed_price,
                            "ticket": result.mt5_ticket,
                            "stop_loss": params.get("stop_loss"),
                            "take_profit": params.get("take_profit"),
                            "thesis": params.get("rationale", "Executed via Telegram confirmation"),
                            "status": "OPEN",
                        },
                    )
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
                    from monika.infrastructure.storage.journal_helper import record_trade_to_workspace

                    j_res = record_trade_to_workspace(
                        self.settings,
                        {
                            "symbol": params.get("symbol", "POSITION"),
                            "action": "CLOSE",
                            "ticket": ticket,
                            "exit_price": result.get("price"),
                            "profit": result.get("profit"),
                            "status": "CLOSED",
                            "thesis": params.get("reason", "Manual close via Telegram"),
                        },
                    )
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
                    res = await svc.close_positions_batch(
                        filter_type=filter_type, requested_by="chat_user", reason=reason
                    )
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
            import monika.core.primitives.clock as clock
            from monika.core.analytics.paper_tracker import PaperTracker
            from monika.infrastructure.database.models import PaperTradeRecord, PriceOHLCV

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
                    q = q.where(PaperTradeRecord.symbol == symbol.upper().replace("/", ""))
                trade = (await session.execute(q)).scalars().first()
                if not trade:
                    return f"[ERROR] Open paper trade not found for id={trade_id} / symbol={symbol}."

                last_bar = (
                    await session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == trade.symbol)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                exit_p = last_bar.close if last_bar else trade.entry_price

                pnl_pct = 0.0
                if trade.entry_price and exit_p:
                    if trade.direction == "buy":
                        pnl_pct = ((exit_p - trade.entry_price) / trade.entry_price) * 100.0
                    else:
                        pnl_pct = ((trade.entry_price - exit_p) / trade.entry_price) * 100.0

                closed_at = clock.now()
                trade.status = "closed"
                trade.exit_price = exit_p
                trade.exit_reason = "manual_chat_close"
                trade.closed_at = closed_at
                trade.pnl_pct = round(pnl_pct, 4)
                if trade.opened_at:
                    trade.holding_hours = round((closed_at - trade.opened_at).total_seconds() / 3600.0, 2)

                tracker = PaperTracker(self.settings)
                await tracker._close_linked_position(session, trade)
                await session.commit()
                msg = f"[OK] Paper trade #{trade.id} ({trade.symbol}) closed manually @ {exit_p:.5f}. Realized PnL: {pnl_pct:+.2f}%"
                try:
                    from monika.infrastructure.storage.journal_helper import record_trade_to_workspace

                    record_trade_to_workspace(
                        self.settings,
                        {
                            "symbol": trade.symbol,
                            "action": f"CLOSE_{trade.direction.upper()}",
                            "ticket": f"PAPER-{trade.id}",
                            "volume": getattr(trade, "lots", 0.01),
                            "entry_price": trade.entry_price,
                            "price": exit_p,
                            "pnl_pct": pnl_pct,
                            "status": "CLOSED",
                            "thesis": f"Paper trade closed manually. Realized PnL: {pnl_pct:+.2f}%",
                        },
                    )
                except Exception as je:
                    logger.debug(f"[WorkspaceJournal] paper auto-journal failed: {je}")
                return msg

        elif action.action_type == "modify_paper_sl_tp":
            from monika.infrastructure.database.models import PaperTradeRecord

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
                    q = q.where(PaperTradeRecord.symbol == symbol.upper().replace("/", ""))
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
            from monika.infrastructure.database.models import TradeTrigger

            trigger_id = params.get("trigger_id") or params.get("id")
            if not trigger_id:
                return "[ERROR] Trigger ID required."
            try:
                trig_id_int = int(trigger_id)
            except ValueError:
                return f"[ERROR] Invalid trigger ID format: {trigger_id}"
            async with get_session() as session:
                trigger = (
                    await session.execute(select(TradeTrigger).where(TradeTrigger.id == trig_id_int))
                ).scalar_one_or_none()
                if not trigger:
                    return f"[ERROR] Trigger #{trigger_id} not found."
                trigger.status = "cancelled"
                await session.commit()
                return f"[OK] Trigger #{trigger.id} cancelled."

        elif action.action_type == "pause_trading":
            from monika.domain.risk.risk_gate import RiskGate

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
            from monika.domain.risk.risk_gate import RiskGate

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
            from monika.application.analysis.tools.tool_executor import ToolExecutor

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
                res = await svc.apply_immediate_breakeven(
                    only_profit=only_profit, symbol=symbol, requested_by="telegram_chat"
                )
                return f"[KEAMANAN] [OK] {res.get('message', 'Positions secured to Breakeven.')}\nUpdated: {res.get('updated_count', 0)}, Skipped: {res.get('skipped_count', 0)}"
            return "[ERROR] Execution service does not support bulk breakeven."

        elif action.action_type == "cancel_stale_pending_orders":
            from monika.application.analysis.tools.handlers.trade_intel import handle_cancel_stale_pending_orders

            max_age = float(params.get("max_age_hours", 24))
            res = await handle_cancel_stale_pending_orders({"max_age_hours": max_age})
            if res.get("status") == "success":
                return f"[OK] Stale orders cancelled: {res.get('canceled_count', 0)} cancelled, {res.get('failed_count', 0)} failed."
            return f"[ERROR] Failed to cancel stale orders: {res.get('error')}"

        elif action.action_type == "set_trailing_stop":
            from monika.application.analysis.tools.handlers.position_mgmt import handle_set_trailing_stop

            async with get_session() as session:
                res = await handle_set_trailing_stop(params, session=session, settings=self.settings)
                if res.get("success"):
                    return f"[OK] Trailing stop configured: updated {res.get('updated_count', 0)} positions ({res.get('updated_tickets', [])})."
                return f"[ERROR] Failed to set trailing stop: {res.get('error') or res.get('message')}"

        elif action.action_type == "update_config":
            from monika.infrastructure.database.models import SystemConfig

            key = params.get("key") or params.get("parameter")
            value = params.get("value")
            if not key or value is None:
                return "[ERROR] Parameter 'key' and 'value' required for update_config."
            async with get_session() as session:
                cfg = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == str(key)))
                ).scalar_one_or_none()
                if cfg:
                    cfg.value = str(value)
                else:
                    session.add(SystemConfig(key=str(key), value=str(value)))
                await session.commit()
                try:
                    from monika.domain.risk.risk_gate import RiskGate

                    gate = RiskGate(self.settings)
                    if hasattr(gate, "hot_reload_risk_parameters"):
                        getattr(gate, "hot_reload_risk_parameters")({str(key): value})
                except Exception:
                    pass
                return f"[OK] Configuration '{key}' updated to '{value}'."

        elif action.action_type == "update_user_preference":
            from monika.infrastructure.database.models import UserPreference

            user_id = str(self.user_id)
            cat = str(params.get("category") or "general")
            key = str(params.get("key") or "preference")
            val = params.get("value")
            val_json = json.dumps(val) if not isinstance(val, str) else val
            async with get_session() as session:
                pref = (
                    await session.execute(
                        select(UserPreference).where(
                            UserPreference.user_id == user_id,
                            UserPreference.category == cat,
                            UserPreference.key == key,
                        )
                    )
                ).scalar_one_or_none()
                if pref:
                    pref.value_json = val_json
                    pref.is_active = True
                else:
                    session.add(
                        UserPreference(
                            user_id=user_id,
                            category=cat,
                            key=key,
                            value_json=val_json,
                            is_active=True,
                        )
                    )
                await session.commit()
                return f"[OK] User preference updated: [{cat}] {key} = {val_json}"

        elif action.action_type == "db_mutation":
            return await self._execute_db_mutation(params)

        elif action.action_type == "execute_terminal_command":
            if not getattr(self, "is_admin", False):
                return "[GAGAL] Akses Ditolak: Perintah terminal hanya diizinkan untuk Admin."
            from monika.application.analysis.tools.tool_executor import ToolExecutor

            async with get_session() as session:
                executor = ToolExecutor(session, settings=self.settings)
                res = await executor.execute("terminal", params)
                return f"[TERMINAL OUTPUT]\n{res}"

        elif action.action_type == "desktop_gui_action":
            if not getattr(self, "is_admin", False):
                return "[GAGAL] Akses Ditolak: Aksi desktop GUI hanya diizinkan untuk Admin."
            from monika.application.analysis.tools.tool_executor import ToolExecutor

            async with get_session() as session:
                executor = ToolExecutor(session, settings=self.settings)
                res = await executor.execute("computer_use", params)
                return f"[GUI ACTION RESULT]\n{res}"

        elif action.action_type == "partial_close_and_breakeven":
            from monika.infrastructure.database.models import Position

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
                pos = (
                    await session.execute(select(Position).where(Position.mt5_ticket == ticket))
                ).scalar_one_or_none()
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

        from datetime import date

        from sqlalchemy import BigInteger, Integer
        from sqlalchemy import inspect as sqla_inspect

        from monika.application.analysis.tools.handlers.db_tools import get_table_model_map
        from monika.application.analysis.tools.tool_guardrails import DATABASE_IMMUTABLE_TABLES
        from monika.infrastructure.database.models import ActivityLog

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
                        except ValueError, TypeError:
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

                    session.add(
                        ActivityLog(
                            category="database",
                            description=f"Telegram Admin {self.user_id} UPDATED {table_name} #{target_id}: {pre_state} -> {updated_fields}",
                            actor="telegram_admin",
                        )
                    )
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
                    session.add(
                        ActivityLog(
                            category="database",
                            description=f"Telegram Admin {self.user_id} INSERTED into {table_name} (ID: #{new_id}): {valid_fields}",
                            actor="telegram_admin",
                        )
                    )
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
                        except ValueError, TypeError:
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

                    session.add(
                        ActivityLog(
                            category="database",
                            description=f"Telegram Admin {self.user_id} DELETED from {table_name} #{target_id}: {pre_state}",
                            actor="telegram_admin",
                        )
                    )
                    await session.commit()
                    return f" Berhasil menghapus rekaman #{target_id} dari tabel *{table_name}*."

                else:
                    return f"[GAGAL] Operasi database '{operation}' tidak didukung. Pilihan: insert, update, delete."

            except Exception as e:
                await session.rollback()
                logger.error(f"[ChatAgent] Database mutation failed: {e}", exc_info=True)
                return f"[GAGAL] Gagal memodifikasi database: {str(e)}"
