# ==============================================================================
# File: agent/estop.py
# ==============================================================================

"""
Emergency Stop (ESTOP) File-Level Sentinel System.
Institutional-grade engine turn protection architecture.

Provides a fail-safe, OS-level circuit breaker via sentinel file ($MONIKA_HOME/ESTOP).
If the ESTOP file exists (or if an OSError occurs during probing), ESTOP is active.

Invariants:
1. Fail-Safe: If filesystem probe fails, fail-closed (ESTOP considered ACTIVE).
2. Graceful In-Flight Preservation: ESTOP blocks NEW tasks, orders, and turns from
   starting, but NEVER violently kills in-flight transactions or active DB commits,
   preventing partial writes and MT5 order state desynchronization.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("TradingAgent.Agent.ESTOP")


class ESTOPActiveError(Exception):
    """Raised when an operation is rejected because ESTOP is armed."""
    def __init__(self, message: str = "Emergency Stop (ESTOP) is active. New actions blocked.", reason: str = ""):
        super().__init__(message)
        self.reason = reason


def get_estop_file_path() -> Path:
    """Resolve authoritative path to the ESTOP sentinel file."""
    monika_home = os.environ.get("MONIKA_HOME")
    if monika_home:
        return Path(monika_home) / "ESTOP"

    # Fallback to project root directory
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "ESTOP"


def is_estop_active() -> bool:
    """
    Checks if the emergency stop sentinel file exists.
    Fail-safe: Returns True if file exists OR if OSError occurs while probing.
    """
    path = get_estop_file_path()
    try:
        stat_result = os.stat(path)
        # If stat succeeds, file exists
        logger.critical(f"[ESTOP] Emergency Stop Sentinel File DETECTED at {path}!")
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        # Permission error or disk fault: fail-safe by treating as active
        logger.critical(f"[ESTOP] OSError probing ESTOP sentinel at {path}: {e}. Failing safe (ESTOP ACTIVE).")
        return True


def get_estop_details() -> Optional[Dict[str, Any]]:
    """Retrieve metadata stored in the ESTOP sentinel file, if present."""
    if not is_estop_active():
        return None

    path = get_estop_file_path()
    try:
        content = path.read_text(encoding="utf-8").strip()
        if content.startswith("{"):
            return json.loads(content)
        return {"reason": content, "armed_at": "unknown"}
    except Exception as e:
        logger.debug(f"[ESTOP] Failed to parse ESTOP file payload: {e}")
        return {"reason": "ESTOP active (unreadable payload)", "armed_at": "unknown"}


def arm_estop(reason: str = "Manual Emergency Stop initiated", actor: str = "operator") -> Path:
    """
    Arms the emergency stop sentinel file atomically.
    Blocks all subsequent turns, schedulers, and new trade executions.
    """
    path = get_estop_file_path()
    payload = {
        "armed": True,
        "reason": reason,
        "actor": actor,
        "armed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    
    # Atomic rename replace
    tmp_path.replace(path)
    logger.critical(f"[ESTOP] *** ESTOP ARMED by {actor}: '{reason}' (sentinel: {path}) ***")
    return path


def disarm_estop() -> bool:
    """
    Disarms the emergency stop by removing the sentinel file.
    """
    path = get_estop_file_path()
    try:
        if path.exists():
            path.unlink()
            logger.warning(f"[ESTOP] ESTOP DISARMED. Sentinel file removed from {path}.")
            return True
        return False
    except Exception as e:
        logger.error(f"[ESTOP] Failed to disarm ESTOP: {e}")
        return False


def check_estop_or_raise(action_label: str = "Action"):
    """Convenience assertion: raises ESTOPActiveError if ESTOP is armed."""
    if is_estop_active():
        details = get_estop_details() or {}
        reason = details.get("reason", "ESTOP active")
        raise ESTOPActiveError(
            message=f"{action_label} BLOCKED: Emergency Stop (ESTOP) is currently active. Reason: {reason}",
            reason=reason,
        )
