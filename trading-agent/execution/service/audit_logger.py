# ==============================================================================
# File: execution/service/audit_logger.py
# ==============================================================================

"""
Trade audit logging and position persistence engine.
Records execution outcomes to ActivityLog and persists Position & MT5Signal records.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Position, MT5Signal, OrderLog, ActivityLog, AssetAnalysis
from risk.position_sizing import SizingResult

logger = logging.getLogger("TradingAgent.ExecutionService.AuditLogger")


class TradeAuditLogger:
    """Handles audit logging and position recording for executed trades."""

    @staticmethod
    async def save_position(
        session: AsyncSession,
        analysis: AssetAnalysis,
        sizing: SizingResult,
        mt5_result: dict,
        dry_run: bool = False,
        pair_group_id: Optional[str] = None,
        auto_commit: bool = True,
        order_id: Optional[str] = None,
    ) -> Optional[int]:
        """Create a Position and MT5Signal record in DB after successful order placement."""
        try:
            req_lots = float(getattr(sizing, 'recommended_lots', 0.0) or 0.0)
            filled_lots = float(mt5_result.get('volume') or req_lots)
            partially_filled = filled_lots < (req_lots - 1e-5)

            exec_price = float(mt5_result.get('price') or getattr(sizing, 'entry_price', 0.0) or 0.0)
            req_price = float(getattr(sizing, 'entry_price', 0.0) or exec_price)

            from risk.position_sizing import get_instrument_spec
            spec = get_instrument_spec(analysis.symbol)
            pip_size = spec.pip_size if spec and spec.pip_size > 0 else 0.0001
            slippage_pips = round(abs(exec_price - req_price) / pip_size, 2)

            pos = Position(
                order_id=order_id,
                analysis_id=analysis.id,
                mt5_ticket=mt5_result.get('ticket'),
                symbol=analysis.symbol,
                direction=analysis.decision,
                volume=filled_lots,
                initial_volume=filled_lots,
                requested_volume=req_lots,
                entry_price=exec_price,
                sl=analysis.stop_loss,
                tp=analysis.take_profit,
                slippage_pips=slippage_pips,
                partially_filled=partially_filled,
                opened_at=datetime.now(timezone.utc),
                status='open',
                is_paper=dry_run,
                pair_group_id=pair_group_id,
            )
            session.add(pos)

            signal = MT5Signal(
                asset_analysis_id=analysis.id,
                symbol=analysis.symbol,
                action=analysis.decision,
                status='executed',
                mt5_ticket=mt5_result.get('ticket'),
                executed_at=datetime.now(timezone.utc)
            )
            session.add(signal)

            await session.flush()

            # Also write OrderLog
            session.add(OrderLog(
                action='place',
                symbol=analysis.symbol,
                params_json=json.dumps({
                    'analysis_id': analysis.id,
                    'direction': analysis.decision,
                    'lots': sizing.recommended_lots,
                    'entry_price': mt5_result.get('price'),
                    'sl': analysis.stop_loss,
                    'tp': analysis.take_profit,
                    'ticket': mt5_result.get('ticket'),
                }),
                requested_by='analysis_pipeline',
                approved_by='risk_gate',
                result=json.dumps({'success': True, 'ticket': mt5_result.get('ticket')}),
            ))
            if auto_commit:
                await session.commit()
            return pos.id if pos.id is not None else (mt5_result.get('ticket') or 1)
        except Exception as e:
            from sqlalchemy.exc import IntegrityError
            if isinstance(e, IntegrityError) or 'IntegrityError' in str(type(e)):
                logger.warning(f"Position DB save blocked by IntegrityError (race collision for {analysis.symbol}): {e}")
            else:
                logger.error(f"Failed to save position to DB: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
            return None

    @staticmethod
    async def log_result(
        session: AsyncSession,
        summary_text: str,
        analysis_id: Optional[int],
    ) -> None:
        """Write execution result to ActivityLog."""
        try:
            session.add(ActivityLog(
                category='trading',
                description=summary_text,
                related_id=analysis_id,
                actor='execution_service',
            ))
            await session.commit()
        except Exception as e:
            logger.debug(f"Activity log write failed (non-fatal): {e}")
