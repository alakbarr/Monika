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

    agent_dir = Path(__file__).resolve().parent.parent
    if (agent_dir / "ESTOP").exists():
        return agent_dir / "ESTOP"
    project_root = agent_dir.parent
    return project_root / "ESTOP"


def get_estop_candidate_paths() -> list[Path]:
    """Returns all potential sentinel paths checked for ESTOP state."""
    candidate_paths = [get_estop_file_path()]
    agent_dir = Path(__file__).resolve().parent.parent
    if (agent_dir / "ESTOP") not in candidate_paths:
        candidate_paths.append(agent_dir / "ESTOP")
    return candidate_paths


def is_estop_active() -> bool:
    """
    Checks if the emergency stop sentinel file exists.
    Fail-safe: Returns True if file exists OR if OSError occurs while probing.
    """
    for path in get_estop_candidate_paths():
        try:
            stat_result = os.stat(path)
            logger.critical(f"[ESTOP] Emergency Stop Sentinel File DETECTED at {path}!")
            return True
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.critical(f"[ESTOP] OSError probing ESTOP sentinel at {path}: {e}. Failing safe (ESTOP ACTIVE).")
            return True
    return False


def get_estop_details() -> Optional[Dict[str, Any]]:
    """Retrieve metadata stored in the ESTOP sentinel file, if present."""
    if not is_estop_active():
        return None

    for path in get_estop_candidate_paths():
        try:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content.startswith("{"):
                    return json.loads(content)
                return {"reason": content, "armed_at": "unknown"}
        except Exception as e:
            logger.debug(f"[ESTOP] Failed to parse ESTOP file payload at {path}: {e}")
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
    Disarms the emergency stop by removing all sentinel files.
    """
    removed_any = False
    for path in get_estop_candidate_paths():
        try:
            if path.exists():
                path.unlink()
                logger.warning(f"[ESTOP] ESTOP DISARMED. Sentinel file removed from {path}.")
                removed_any = True
        except Exception as e:
            logger.error(f"[ESTOP] Failed to remove sentinel at {path}: {e}")
    return removed_any


def check_estop_or_raise(action_label: str = "Action"):
    """Convenience assertion: raises ESTOPActiveError if ESTOP is armed."""
    if is_estop_active():
        details = get_estop_details() or {}
        reason = details.get("reason", "ESTOP active")
        raise ESTOPActiveError(
            message=f"{action_label} BLOCKED: Emergency Stop (ESTOP) is currently active. Reason: {reason}",
            reason=reason,
        )
