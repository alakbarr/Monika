"""
Lightweight Async Subagent Isolation.

Each specialist gets a dedicated AgentHarness instance with:
- Own message history (zero context bleed)
- Own compaction engine state
- Timeout watchdog with clean cancellation
- Structured output contract (only final result reaches parent)
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from analysis.harness.agent_harness import AgentHarness

logger = logging.getLogger("TradingAgent.IsolatedSubagent")

DEFAULT_TIMEOUT = 300  # 5 minutes per specialist
HEARTBEAT_INTERVAL = 30  # Check liveness every 30s


class IsolatedSubagentRunner:
    """Run analysis subagents with dedicated harness instances."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def run_isolated(
        self,
        role_name: str,
        llm_client: Any,
        system_prompt: str,
        messages: List[dict],
        tools: List[dict],
        stage_name: str = "isolated",
        timeout: int = DEFAULT_TIMEOUT,
        session: Any = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Spawn a subagent with dedicated AgentHarness instance.

        Returns only the final structured result — intermediate tool calls,
        reasoning, and errors stay isolated within the subagent's context.
        """
        # Dedicated harness — fresh compaction state, fresh message history
        isolated_harness = AgentHarness(
            llm_client=llm_client,
            settings=self.settings,
        )

        try:
            result = await asyncio.wait_for(
                isolated_harness.run_agent_from_messages(
                    session=session,
                    system_prompt=system_prompt,
                    messages=list(messages),  # Copy — prevent cross-agent mutation
                    tools=tools,
                    stage_name=f"{stage_name}_{role_name}",
                    **kwargs,
                ),
                timeout=timeout,
            )

            if result.get("success"):
                logger.info(
                    f"[IsolatedSubagent:{role_name}] Completed in "
                    f"{result.get('turns', '?')} turns, "
                    f"{result.get('tool_calls_made', 0)} tool calls"
                )
            else:
                logger.warning(
                    f"[IsolatedSubagent:{role_name}] Failed: {result.get('error', 'unknown')}"
                )

            return result

        except asyncio.TimeoutError:
            logger.error(
                f"[IsolatedSubagent:{role_name}] Timed out after {timeout}s — "
                f"killing and returning partial result"
            )
            return {
                "success": False,
                "error": f"Specialist {role_name} timed out after {timeout}s",
                "final_text": "",
                "tool_calls_made": 0,
                "turns": 0,
            }
        except Exception as e:
            logger.error(
                f"[IsolatedSubagent:{role_name}] Unexpected error: {e}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "final_text": "",
            }

    async def run_parallel_isolated(
        self,
        specs: List[Dict[str, Any]],
        timeout: int = DEFAULT_TIMEOUT,
        session: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        Run multiple isolated subagents concurrently.

        Args:
            specs: List of dicts with keys:
                role_name, llm_client, system_prompt, messages, tools, stage_name
        """
        tasks = [
            self.run_isolated(
                session=session, timeout=timeout, **spec
            )
            for spec in specs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"Subagent {specs[i].get('role_name', i)} raised: {res}")
                final.append({"success": False, "error": str(res)})
            else:
                final.append(res)
        return final
