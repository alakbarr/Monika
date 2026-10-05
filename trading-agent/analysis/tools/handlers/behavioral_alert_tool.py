# ==============================================================================
# File: analysis/tools/handlers/behavioral_alert_tool.py
# ==============================================================================

"""
Behavioral & Psychology Alert Tool Handler (Async).
Monitors trader psychological pitfalls (revenge trading, FOMO, over-leverage).
Supports passive notification alerts and active trading cooldown/quarantine locks.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from database.models import UserPreference
from database.safe_ops import safe_commit
from utils import clock

logger = logging.getLogger("TradingAgent.BehavioralAlert")


async def handle_create_behavioral_alert(args: dict, session: Optional[AsyncSession] = None, **kwargs) -> dict:
    """
    Creates a behavioral psychology alert and optionally enforces a quarantine cooldown.
    """
    alert_type = args.get("alert_type", "REVENGE_TRADING").upper()
    trigger_condition = args.get("trigger_condition", "3 consecutive losses within 30 minutes")
    action_mode = args.get("action_mode", "QUARANTINE").upper()  # WARN_ONLY or QUARANTINE
    quarantine_hours = float(args.get("quarantine_hours", 2.0))

    dt_now = clock.now()
    cooldown_until = dt_now + timedelta(hours=quarantine_hours)

    quarantine_applied = False
    if session and action_mode == "QUARANTINE":
        # Store persistent quarantine constraint in user_preferences table
        pref = UserPreference(
            user_id="default",
            category="trading_hours",
            key=f"quarantine_{alert_type.lower()}",
            value_json=json.dumps({
                "alert_type": alert_type,
                "reason": trigger_condition,
                "cooldown_until": cooldown_until.isoformat(),
                "quarantine_hours": quarantine_hours,
            }),
            is_active=True,
            created_at=dt_now,
        )
        session.add(pref)
        await safe_commit(session)
        quarantine_applied = True
        logger.warning(f"Trader quarantine active until {cooldown_until.isoformat()} ({alert_type})")

    notification_msg = (
        f"🚨 [BEHAVIORAL RISK DEFENSE] Alert: {alert_type}\n"
        f"Trigger: {trigger_condition}\n"
        f"Action: {'Trading QUARANTINE enforced for ' + str(quarantine_hours) + ' hours' if quarantine_applied else 'Warning advisory dispatched'}\n"
        f"Protection Status: Active cooling period until {cooldown_until.strftime('%H:%M:%S UTC')}."
    )

    return {
        "status": "success",
        "alert_type": alert_type,
        "trigger_condition": trigger_condition,
        "action_mode": action_mode,
        "quarantine_applied": quarantine_applied,
        "quarantine_until": cooldown_until.isoformat() if quarantine_applied else None,
        "advisory_message": notification_msg,
    }


@register_tool("create_behavioral_alert", aliases=["set_psychology_alert", "trading_quarantine"], category="RISK", parallel_safe=True)
class CreateBehavioralAlertHandler(ToolHandler):
    name = "create_behavioral_alert"
    category = "RISK"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_create_behavioral_alert(args, session=session, executor=executor, **kwargs)
