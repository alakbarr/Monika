"""
Lightweight Async Subagent Isolation.

Each specialist gets a dedicated AgentHarness instance with:
- Own message history (zero context bleed)
- Own compaction engine state
- Timeout watchdog with clean cancellation
- Structured output contract (only final result reaches parent)
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from analysis.harness.agent_harness import AgentHarness

logger = logging.getLogger("TradingAgent.IsolatedSubagent")

DEFAULT_TIMEOUT = 300  # 5 minutes per specialist
HEARTBEAT_INTERVAL = 30  # Check liveness every 30s


def _extract_and_validate(text: str, schema: dict, jsonschema_module: Any = None) -> Tuple[Optional[dict], Optional[str]]:
    """Extract JSON from text and validate against schema."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()

    try:
        data = json.loads(cleaned)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except Exception as je:
                return None, f"JSON parse error: {je}"
        else:
            return None, "No valid JSON object found in response"

    if not isinstance(data, dict):
        return None, "Output is not a JSON dictionary"

    if jsonschema_module:
        try:
            jsonschema_module.validate(instance=data, schema=schema)
        except Exception as ve:
            return None, getattr(ve, "message", str(ve))
    else:
        req = schema.get("required", [])
        missing = [r for r in req if r not in data]
        if missing:
            return None, f"Missing required properties: {missing}"

    return data, None


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
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Spawn a subagent with dedicated AgentHarness instance.

        Returns only the final structured result — intermediate tool calls,
        reasoning, and errors stay isolated within the subagent's context.
        """
        isolated_harness = AgentHarness(
            llm_client=llm_client,
            settings=self.settings,
        )

        async def _heartbeat():
            try:
                while True:
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
                    logger.debug(f"[IsolatedSubagent:{role_name}] Heartbeat: subagent execution active.")
            except asyncio.CancelledError:
                pass

        hb_task = asyncio.create_task(_heartbeat())

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

            # Output Schema Validation & 1-Turn Auto-Correction Contract
            if output_schema and result.get("success") and result.get("final_text"):
                try:
                    import jsonschema
                except ImportError:
                    jsonschema = None

                parsed, err = _extract_and_validate(result["final_text"], output_schema, jsonschema)
                if err:
                    logger.warning(
                        f"[IsolatedSubagent:{role_name}] Output failed schema validation: {err}. "
                        f"Attempting 1-turn auto-correction..."
                    )
                    correction_nudge = (
                        f"CRITICAL SCHEMA VALIDATION ERROR: Output failed schema contract validation.\n"
                        f"Error: {err}\n"
                        f"Target Schema:\n{json.dumps(output_schema, indent=2)}\n"
                        f"You MUST output ONLY a valid JSON object strictly conforming to this schema."
                    )
                    correction_messages = list(messages) + [
                        {"role": "assistant", "content": [{"type": "text", "text": result.get("final_text", "")}]},
                        {"role": "user", "content": correction_nudge},
                    ]
                    try:
                        corr_res = await isolated_harness.run_agent_from_messages(
                            session=session,
                            system_prompt=system_prompt,
                            messages=correction_messages,
                            tools=[],
                            stage_name=f"{stage_name}_{role_name}_correction",
                            max_turns=1,
                            **kwargs,
                        )
                        if corr_res.get("success") and corr_res.get("final_text"):
                            c_parsed, c_err = _extract_and_validate(corr_res["final_text"], output_schema, jsonschema)
                            if not c_err:
                                logger.info(f"[IsolatedSubagent:{role_name}] 1-turn auto-correction succeeded.")
                                result["final_text"] = corr_res["final_text"]
                                result["parsed_output"] = c_parsed
                                result["schema_valid"] = True
                            else:
                                result["schema_valid"] = False
                                result["schema_error"] = c_err
                    except Exception as ce:
                        logger.warning(f"[IsolatedSubagent:{role_name}] Auto-correction failed: {ce}")
                        result["schema_valid"] = False
                        result["schema_error"] = err
                else:
                    result["parsed_output"] = parsed
                    result["schema_valid"] = True

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
        finally:
            hb_task.cancel()

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
