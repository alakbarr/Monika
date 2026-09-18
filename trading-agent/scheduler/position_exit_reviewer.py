import asyncio
import logging
from datetime import datetime, timezone, timedelta
from database.db import get_session
from database.models import Position, AssetAnalysis, SystemConfig
from sqlalchemy import select
logger = logging.getLogger('TradingAgent.PositionExitReviewer')

class PositionExitReviewer:

    def __init__(self, settings: dict, per_asset_stage=None, execution_service=None, recovery_event=None):
        self.settings = settings
        self._per_asset = per_asset_stage
        self._execution_service = execution_service
        self._recovery_event = recovery_event
        self._review_interval_hours = settings.get('trading', {}).get('position_review_interval_hours', 4.0)
        self._running = False
        self._stop_event = asyncio.Event()

    async def _get_last_review_time(self, session, position_id: int):
        key = f'position_exit_review_last_{position_id}'
        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
        if not cfg or not cfg.value:
            return None
        try:
            dt = datetime.fromisoformat(cfg.value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    async def _set_last_review_time(self, session, position_id: int, when: datetime) -> None:
        key = f'position_exit_review_last_{position_id}'
        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
        val = when.isoformat()
        if cfg:
            cfg.value = val
        else:
            session.add(SystemConfig(key=key, value=val))
        await session.commit()

    async def _cleanup_stale_review_markers(self, session, open_position_ids: set) -> None:
        rows = (await session.execute(select(SystemConfig).where(SystemConfig.key.like('position_exit_review_last_%')))).scalars().all()
        deleted = 0
        for row in rows:
            try:
                pid = int(row.key.rsplit('_', 1)[-1])
            except ValueError:
                continue
            if pid not in open_position_ids:
                await session.delete(row)
                deleted += 1
        if deleted:
            await session.commit()
            logger.debug(f'PositionExitReviewer: cleaned up {deleted} stale review markers')

    async def review_open_positions(self) -> list[dict]:
        results = []
        async with get_session() as session:
            open_positions = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
        if not open_positions:
            return results

        now = datetime.now(timezone.utc)
        async with get_session() as session:
            await self._cleanup_stale_review_markers(session, {p.id for p in open_positions})

        for position in open_positions:
            async with get_session() as session:
                last_review = await self._get_last_review_time(session, position.id)
            if last_review and (now - last_review).total_seconds() < self._review_interval_hours * 3600:
                # Sudah direview dalam interval ini (termasuk sebelum restart terakhir) — skip.
                continue
            try:
                result = await self._review_single_position(position)
                results.append(result)
                async with get_session() as session:
                    await self._set_last_review_time(session, position.id, now)
            except Exception as e:
                logger.error(f'Position exit review failed for {position.symbol}: {e}')
        return results

    async def _review_single_position(self, position: Position) -> dict:
        if not self._per_asset:
            return {'position_id': position.id, 'action': 'no_reviewer'}

        holding_hours_so_far = 0.0
        if position.opened_at:
            opened = position.opened_at.replace(tzinfo=timezone.utc) if position.opened_at.tzinfo is None else position.opened_at
            holding_hours_so_far = (datetime.now(timezone.utc) - opened).total_seconds() / 3600
        max_intraday_hours = self.settings.get('trading', {}).get('risk', {}).get('max_position_holding_hours_intraday', 30)
        intraday_overdue_note = ''
        if holding_hours_so_far > max_intraday_hours:
            intraday_overdue_note = (
                f"\n⏰ INTRADAY TIMEOUT NOTICE: This position was opened as an INTRADAY RANGE-EDGE trade "
                f"(target: 50-80% of daily ADR), expected to resolve within ~1 trading day. It has now been "
                f"open {holding_hours_so_far:.1f}h — beyond the {max_intraday_hours}h expected window — "
                f"without hitting SL or TP. This is a strong signal the original thesis likely stalled or "
                f"the day's range was exhausted without reaching target. Default toward recommending EXIT "
                f"(decision='avoid') unless there is a clear, FRESH, strong reason to keep holding.\n"
            )

        exit_context = f"\nPOSITION EXIT REVIEW MODE:\nYou are reviewing an EXISTING OPEN position, NOT looking for new entries.\n{intraday_overdue_note}\nCurrent Position:\n- Symbol: {position.symbol}\n- Direction: {position.direction.upper()}\n- Entry Price: {position.entry_price}\n- Current SL: {position.sl}\n- Current TP: {position.tp}\n- Opened: {position.opened_at}\n- Position Ticket: {position.mt5_ticket}\n\nYOUR TASK:\n1. Analyze current market conditions for {position.symbol}\n2. Determine if the ORIGINAL THESIS is still valid\n3. Submit your decision as:\n   - decision='wait': Position still valid, keep holding\n   - decision='avoid': Original thesis invalidated → PROPOSE closing position\n   \nIf you recommend closing (decision='avoid'), provide:\n- Clear reason WHY the thesis is invalidated\n- Specific price evidence\n- Estimated pnl impact if closed now vs held\n\nDO NOT look for new entry signals. Focus only on whether to KEEP or EXIT the existing position.\n"

        # Jev System One Pre-Screen: Check if thesis is clearly intact to save expensive Stage 2 run
        try:
            from analysis.providers.llm_factory import get_client_for_task
            from utils.typesafe.jev_primitives import build_exit_review_prescreen
            jev_exit_client = get_client_for_task("jev_exit_prescreen", self.settings)
            if hasattr(jev_exit_client, "classify_json"):
                exit_q = build_exit_review_prescreen(position.symbol, position.direction)
                state = {
                    "symbol": position.symbol,
                    "direction": position.direction,
                    "entry_price": position.entry_price,
                    "sl": position.sl,
                    "tp": position.tp,
                    "holding_hours": round(holding_hours_so_far, 1)
                }
                prescreen_res = await jev_exit_client.classify_json(prompt="", state=state, jev_questions=exit_q)
                if (
                    prescreen_res
                    and prescreen_res.get("thesis_still_valid") is True
                    and prescreen_res.get("exit_urgency", 0) <= 1
                ):
                    logger.info(
                        f"[PositionExitReviewer] Jev pre-screen verified thesis intact for {position.symbol} "
                        f"(urgency={prescreen_res.get('exit_urgency')}) — skipping full Stage 2 review."
                    )
                    return {"position_id": position.id, "action": "kept", "reason": "jev_prescreen_intact"}
        except Exception as jev_prescreen_err:
            logger.debug(f"[PositionExitReviewer] Jev exit pre-screen bypassed: {jev_prescreen_err}")

        async with get_session() as session:
            try:
                result = await self._per_asset.run_one(session=session, symbol=position.symbol, extra_context=exit_context, skip_cooldown=True, bypass_prescreen=True)
            except Exception as e:
                logger.warning(f'Primary model failed for exit review ({e}), falling back to secondary...')
                result = await self._per_asset.run_one(session=session, symbol=position.symbol, extra_context=exit_context, skip_cooldown=True, is_secondary=True, bypass_prescreen=True)
                
        ai_decision = result.get('decision', 'wait')
        should_exit = False
        if position.direction == 'buy' and ai_decision in ('sell', 'avoid'):
            should_exit = True
        elif position.direction == 'sell' and ai_decision in ('buy', 'avoid'):
            should_exit = True
        if should_exit and self._execution_service and position.mt5_ticket:
            review_cfg = self.settings.get('trading', {}).get('position_review', {})
            auto_close_enabled = review_cfg.get('auto_close_on_invalidation', False)
            min_holding_hours = review_cfg.get('auto_close_min_holding_hours', 4.0)
            max_loss_pct = review_cfg.get('auto_close_max_loss_pct', 0.5)
            holding_hours = 0
            if position.opened_at:
                opened = position.opened_at.replace(tzinfo=timezone.utc) if position.opened_at.tzinfo is None else position.opened_at
                holding_hours = (datetime.now(timezone.utc) - opened).total_seconds() / 3600
            current_pnl_pct = 0
            try:
                if self._execution_service and self._execution_service.mt5:
                    mt5_positions = await self._execution_service.mt5.get_open_positions()
                    for mp in mt5_positions:
                        if mp['ticket'] == position.mt5_ticket:
                            entry = position.entry_price or 1
                            current = mp.get('price_current', entry)
                            move = (current - entry) / entry * 100
                            current_pnl_pct = move if position.direction == 'buy' else -move
                            break
            except Exception as e:
                logger.debug(f'PnL check failed: {e}')
            should_auto_close = auto_close_enabled and holding_hours >= min_holding_hours and (current_pnl_pct < 0) and (abs(current_pnl_pct) < max_loss_pct)
            if should_auto_close:
                logger.warning(f'AUTO-CLOSE: {position.symbol} ticket={position.mt5_ticket} held {holding_hours:.1f}h, PnL={current_pnl_pct:.2f}%, AI recommends exit.')
                try:
                    close_result = await self._execution_service.close_position_by_ticket(position.mt5_ticket, requested_by='position_exit_reviewer', reason=f'AI review: thesis invalidated after {holding_hours:.1f}h')
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_info(f"🤖 <b>Auto-Close: {position.symbol}</b>\nThesis invalidated after {holding_hours:.1f}h\nPnL: {current_pnl_pct:.2f}%\nResult: {('✅ Closed' if close_result.get('success') else '❌ Failed: ' + str(close_result.get('error')))}")
                except Exception as e:
                    logger.error(f'Auto-close failed for {position.mt5_ticket}: {e}')
            else:
                from utils.infra.notifier import AgentNotifier
                rationale = result.get('rationale', 'No rationale provided')[:300]
                await AgentNotifier().send_warning(f'🔄 <b>Position Exit Signal — {position.symbol}</b>\nAI Recommends: EXIT\nHolding: {holding_hours:.1f}h, PnL: {current_pnl_pct:.2f}%\nReason: {rationale}\n\nUse /close {position.mt5_ticket} to confirm.')
        return {'position_id': position.id, 'symbol': position.symbol, 'ai_decision': ai_decision, 'claude_decision': ai_decision, 'should_exit': should_exit}

    async def start(self):
        self._running = True
        logger.info(
            f'PositionExitReviewer started (interval per posisi: {self._review_interval_hours}h, '
            f'state review dipersist ke DB — restart TIDAK memicu review ulang jika belum due)'
        )
        if self._recovery_event:
            logger.info("[PositionExitReviewer] Waiting for recovery event before first review pass...")
            try:
                await asyncio.wait_for(self._recovery_event.wait(), timeout=180.0)
                logger.info("[PositionExitReviewer] Recovery complete, starting review loop.")
            except asyncio.TimeoutError:
                logger.warning("[PositionExitReviewer] Recovery wait timed out (180s). Proceeding anyway.")

        while self._running:
            try:
                results = await self.review_open_positions()
                if results:
                    logger.info(f'Position exit review completed: {len(results)} positions reviewed')
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'PositionExitReviewer error: {e}')
            # Poll cukup sering (maks tiap 15 menit) supaya posisi yang dibuka
            # pada jam berbeda-beda tetap direview mendekati waktu due
            # masing-masing, tanpa memicu Claude untuk posisi yang belum due
            # (state due-check dipersist di DB, jadi aman lintas restart).
            poll_seconds = min(self._review_interval_hours * 3600, 900)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_seconds)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def stop(self):
        self._running = False
        self._stop_event.set()
