"""
Ad-Hoc Dynamic Subagent Manager.

Executes sidecar investigation subagents asynchronously outside the main cycle lock.
Enforces concurrency limits (semaphore=3) and emits structured AdHocInvestigationVerdict
telemetry for consumption by Trading Committee nodes.
"""

import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from analysis.providers.llm_factory import get_client_for_task
from analysis.subagent.isolated_harness import IsolatedSubagentRunner

logger = logging.getLogger("TradingAgent.AdHocSubagentManager")


@dataclass
class AdHocInvestigationVerdict:
    investigation_id: str
    symbol: str
    topic: str
    anomaly_detected: bool
    confidence: float
    recommendation: str  # "proceed", "reduce_risk", "halt", "monitor"
    findings: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdHocSubagentManager:
    """
    Manages non-blocking on-demand market investigation subagents.
    Operates outside the global cycle lock to prevent pipeline stalls.
    """

    def __init__(self, settings: Optional[dict] = None, max_concurrency: int = 3):
        self.settings = settings or {}
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.runner = IsolatedSubagentRunner(self.settings)
        self._verdicts: Dict[str, AdHocInvestigationVerdict] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}

    def get_latest_verdict(self, symbol: str, max_age_seconds: int = 1800) -> Optional[AdHocInvestigationVerdict]:
        """Returns the most recent investigation verdict for symbol if within freshness threshold."""
        clean_sym = symbol.strip().upper()
        verdict = self._verdicts.get(clean_sym)
        if not verdict:
            return None

        try:
            created_dt = datetime.fromisoformat(verdict.created_at)
            age = (datetime.now(timezone.utc) - created_dt).total_seconds()
            if age <= max_age_seconds:
                return verdict
        except Exception:
            return verdict
        return None

    async def investigate_async(
        self,
        symbol: str,
        topic: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 120,
    ) -> asyncio.Task:
        """Launches an ad-hoc investigation as a background task without blocking caller."""
        clean_sym = symbol.strip().upper()
        task = asyncio.create_task(
            self.run_investigation(clean_sym, topic, context or {}, timeout=timeout),
            name=f"adhoc_investigation_{clean_sym}",
        )
        self._active_tasks[clean_sym] = task
        task.add_done_callback(lambda t: self._active_tasks.pop(clean_sym, None))
        return task

    async def run_investigation(
        self,
        symbol: str,
        topic: str,
        context: Dict[str, Any],
        timeout: int = 120,
    ) -> AdHocInvestigationVerdict:
        """
        Runs an isolated investigation subagent bounded by concurrency semaphore.
        """
        clean_sym = symbol.strip().upper()
        investigation_id = f"adhoc_{clean_sym}_{int(datetime.now(timezone.utc).timestamp())}"

        async with self.semaphore:
            logger.info(f"[AdHocManager] Starting investigation '{topic}' for {clean_sym} (id={investigation_id})")
            llm_client = get_client_for_task("macro_analyst", self.settings)
            if not llm_client:
                # Return neutral verdict if client unavailable
                verdict = AdHocInvestigationVerdict(
                    investigation_id=investigation_id,
                    symbol=clean_sym,
                    topic=topic,
                    anomaly_detected=False,
                    confidence=0.0,
                    recommendation="proceed",
                    findings="LLM client unavailable for ad-hoc investigation; defaulting to neutral.",
                )
                self._verdicts[clean_sym] = verdict
                return verdict

            system_prompt = (
                "You are an Institutional Market Anomaly Investigator. "
                "Your objective is to examine rapid price action, order flow anomalies, "
                "macro news shocks, or correlation breakdowns for the target asset. "
                "Respond strictly with a JSON object:\n"
                "{\n"
                '  "anomaly_detected": true/false,\n'
                '  "confidence": 0.0 to 1.0,\n'
                '  "recommendation": "proceed" | "reduce_risk" | "halt" | "monitor",\n'
                '  "findings": "Brief factual analysis with specific observations"\n'
                "}"
            )

            user_prompt = (
                f"Asset: {clean_sym}\n"
                f"Investigation Topic: {topic}\n"
                f"Context Data: {context}\n"
                "Analyze the situation and output your JSON assessment."
            )

            try:
                raw_result = await asyncio.wait_for(
                    llm_client.generate(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        temperature=0.1,
                    ),
                    timeout=timeout,
                )

                import json
                import re

                text = getattr(raw_result, "content", "") or str(raw_result)
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                cleaned = match.group(1).strip() if match else text.strip()
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end != -1:
                    data = json.loads(cleaned[start:end+1])
                else:
                    data = {}

                verdict = AdHocInvestigationVerdict(
                    investigation_id=investigation_id,
                    symbol=clean_sym,
                    topic=topic,
                    anomaly_detected=bool(data.get("anomaly_detected", False)),
                    confidence=float(data.get("confidence", 0.5)),
                    recommendation=str(data.get("recommendation", "monitor")).lower(),
                    findings=str(data.get("findings", "Anomaly inspection completed.")),
                )
            except Exception as exc:
                logger.warning(f"[AdHocManager] Investigation for {clean_sym} encountered error: {exc}")
                verdict = AdHocInvestigationVerdict(
                    investigation_id=investigation_id,
                    symbol=clean_sym,
                    topic=topic,
                    anomaly_detected=False,
                    confidence=0.0,
                    recommendation="monitor",
                    findings=f"Investigation timed out or failed: {exc}",
                )

            self._verdicts[clean_sym] = verdict
            logger.info(
                f"[AdHocManager] Finished {clean_sym} -> anomaly={verdict.anomaly_detected}, "
                f"rec={verdict.recommendation}, conf={verdict.confidence:.2f}"
            )
            return verdict


_global_adhoc_manager: Optional[AdHocSubagentManager] = None


def get_adhoc_manager(settings: Optional[dict] = None) -> AdHocSubagentManager:
    global _global_adhoc_manager
    if _global_adhoc_manager is None:
        _global_adhoc_manager = AdHocSubagentManager(settings=settings)
    return _global_adhoc_manager
