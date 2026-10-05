# ==============================================================================
# File: analysis/tools/domain/cron_tool.py
# ==============================================================================

"""
Dynamic Recurring Cron Job & Background Schedule Tool for Monika.
Allows scheduling automated periodic tasks (e.g. daily COT reports,
hourly orderbook scans, news watchers) via conversational or programmatic calls.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.Cron")

DEFAULT_CRON_FILE = "data/cron_schedules.json"


class CronActionInput(BaseModel):
    """Schema for scheduling dynamic recurring cron jobs."""
    action: str = Field(
        ...,
        description="Action to perform: 'add', 'list', 'remove', or 'clear'."
    )
    name: Optional[str] = Field(
        None,
        description="Unique name identifier for the job (e.g. 'daily_cot_report', 'hourly_risk_audit')."
    )
    cron_expression: Optional[str] = Field(
        None,
        description="Standard 5-part cron expression (e.g. '0 9 * * 1-5' for 9 AM weekdays, '*/15 * * * *' for every 15 min)."
    )
    instruction: Optional[str] = Field(
        None,
        description="Instruction prompt or tool command to execute upon cron trigger."
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of the schedule purpose."
    )


@dataclass
class CronJobRecord:
    name: str
    cron_expression: str
    instruction: str
    description: str
    enabled: bool
    created_at: float
    last_run_at: Optional[float] = None


class CronRegistry:
    """Manages persistent recurring schedules on disk."""

    def __init__(self, file_path: str = DEFAULT_CRON_FILE):
        self.file_path = file_path
        self._jobs: Dict[str, CronJobRecord] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        job = CronJobRecord(**item)
                        self._jobs[job.name] = job
            except Exception as e:
                logger.debug(f"[CronRegistry] Could not load schedules: {e}")

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([asdict(j) for j in self._jobs.values()], f, indent=2)
        except Exception as e:
            logger.debug(f"[CronRegistry] Could not save schedules: {e}")

    def add_job(self, name: Union[str, CronJobRecord], cron_expr: str = "", instruction: str = "", description: str = "") -> CronJobRecord:
        if isinstance(name, CronJobRecord):
            job = name
            self._jobs[job.name] = job
            self._save()
            return job
        job = CronJobRecord(
            name=str(name).strip(),
            cron_expression=str(cron_expr).strip(),
            instruction=str(instruction).strip(),
            description=str(description).strip(),
            enabled=True,
            created_at=time.time(),
        )
        self._jobs[job.name] = job
        self._save()
        return job

    def list_jobs(self) -> List[CronJobRecord]:
        return sorted(list(self._jobs.values()), key=lambda x: x.name)

    def remove_job(self, name: str) -> bool:
        if name in self._jobs:
            del self._jobs[name]
            self._save()
            return True
        return False

    def clear(self) -> int:
        count = len(self._jobs)
        self._jobs.clear()
        self._save()
        return count


_cron_registry = CronRegistry()


@unified_tool_registry.register(
    name="schedule_cron_job",
    category="TASK_MANAGEMENT",
    input_model=CronActionInput,
)
@unified_tool_registry.register(
    name="manage_cron",
    category="TASK_MANAGEMENT",
    input_model=CronActionInput,
)
async def handle_manage_cron(
    params: CronActionInput,
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """Schedules, lists, or removes dynamic recurring cron tasks."""
    act = params.action.lower().strip()

    if act == "add":
        if not params.name:
            return {"success": False, "error": "Name is required to schedule a cron job."}
        if not params.cron_expression:
            return {"success": False, "error": "cron_expression is required (e.g. '0 9 * * 1-5')."}
        if not params.instruction:
            return {"success": False, "error": "instruction is required."}

        job = _cron_registry.add_job(
            name=params.name,
            cron_expr=params.cron_expression,
            instruction=params.instruction,
            description=params.description or "",
        )
        try:
            from scheduler.unified_cron_engine import get_unified_cron_engine
            engine = get_unified_cron_engine()
            engine.register_job(
                job_id=job.name,
                schedule_expression=params.cron_expression,
                prompt=params.instruction,
                name=params.name,
                target_delivery="telegram",
                target_destination="telegram",
            )
        except Exception as e:
            logger.error(f"[CronTool] UnifiedCronEngine register_job failed: {e}")

        return {
            "success": True,
            "message": f"Successfully registered recurring job '{job.name}' ({job.cron_expression}).",
            "job": asdict(job),
        }

    elif act == "list":
        jobs = _cron_registry.list_jobs()
        return {
            "success": True,
            "total": len(jobs),
            "jobs": [asdict(j) for j in jobs],
        }

    elif act == "remove":
        if not params.name:
            return {"success": False, "error": "Name is required to remove a cron job."}
        ok = _cron_registry.remove_job(params.name)
        if not ok:
            return {"success": False, "error": f"Cron job '{params.name}' not found."}
        try:
            from scheduler.unified_cron_engine import get_unified_cron_engine
            engine = get_unified_cron_engine()
            engine.unregister_job(params.name)
        except Exception as e:
            logger.debug(f"[CronTool] UnifiedCronEngine unregister_job: {e}")
        return {"success": True, "message": f"Removed cron job '{params.name}'."}

    elif act == "clear":
        cleared = _cron_registry.clear()
        try:
            from scheduler.unified_cron_engine import get_unified_cron_engine
            engine = get_unified_cron_engine()
            for j in engine.list_jobs():
                engine.unregister_job(j.job_id)
        except Exception as e:
            logger.debug(f"[CronTool] UnifiedCronEngine clear: {e}")
        return {"success": True, "message": f"Cleared {cleared} cron schedules."}

    return {"success": False, "error": f"Unknown action '{act}'. Use 'add', 'list', 'remove', or 'clear'."}


try:
    from analysis.tools.registry import register_tool, ToolHandler
    from sqlalchemy.ext.asyncio import AsyncSession

    @register_tool("manage_cron", aliases=["schedule_cron_job"], category="SYSTEM", parallel_safe=False)
    class ManageCronHandler(ToolHandler):
        name = "manage_cron"
        category = "SYSTEM"
        parallel_safe = False

        async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
            input_obj = CronActionInput(**args) if isinstance(args, dict) else args
            return await handle_manage_cron(input_obj, context=executor)
except Exception:
    pass

