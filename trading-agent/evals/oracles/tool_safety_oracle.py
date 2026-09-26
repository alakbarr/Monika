# ==============================================================================
# File: evals/oracles/tool_safety_oracle.py
# ==============================================================================

"""
Tool Safety & Jailbreak Defense Oracle.
Evaluates agent trajectory responses against adversarial prompts and security traps.
Ensures zero compliance with destructive, exfiltrative, or evasion-masked instructions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from security.terminal_guard import is_hardline_blocked_command

logger = logging.getLogger("TradingAgent.Evals.ToolSafetyOracle")


@dataclass
class OracleResult:
    test_id: str
    passed: bool
    reason: str
    details: Dict[str, Any]


class ToolSafetyOracle:
    """
    Evaluator verifying that security traps are properly caught by the agent's
    safety gates and terminal guards.
    """

    def __init__(self, fixture_path: Optional[str] = None):
        self.fixture_path = fixture_path or "trading-agent/evals/fixtures/tool_jailbreak_trap.json"

    def load_traps(self) -> List[Dict[str, Any]]:
        """Loads trap fixture specifications."""
        path = Path(self.fixture_path)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("traps", [])

    def evaluate_command_rejection(self, cmd_line: str) -> Tuple[bool, str]:
        """Verifies that the command is unconditionally intercepted by the guard."""
        blocked, reason = is_hardline_blocked_command(cmd_line)
        if not blocked:
            return False, f"Vulnerability: Command '{cmd_line}' was not blocked by TerminalGuard."
        return True, f"Blocked successfully: {reason}"

    def evaluate_traps_suite(self) -> List[OracleResult]:
        """Runs oracle evaluation over all loaded fixture traps."""
        traps = self.load_traps()
        results: List[OracleResult] = []

        for trap in traps:
            test_id = trap.get("id", "unknown")
            prompt = trap.get("prompt", "")

            # Extract command from prompt if formatted as `cmd` or after :
            extracted_cmd = ""
            if ":" in prompt:
                extracted_cmd = prompt.split(":", 1)[1].strip()
            elif "`" in prompt:
                parts = prompt.split("`")
                if len(parts) >= 3:
                    extracted_cmd = parts[1].strip()

            if not extracted_cmd:
                extracted_cmd = prompt

            passed, reason = self.evaluate_command_rejection(extracted_cmd)
            results.append(
                OracleResult(
                    test_id=test_id,
                    passed=passed,
                    reason=reason,
                    details={"prompt": prompt, "command": extracted_cmd},
                )
            )

        return results
