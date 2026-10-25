"""
Structured Turn Failure Diagnostics & Error-as-Input Self-Correction Builder.

Provides deterministic root-cause classification and actionable remediation directives
whenever an agent turn encounters a tool schema violation, tool execution failure,
guardrail block, stop-gate rejection, or anti-slop quality rejection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

TurnFailureCategory = Literal[
    "tool_schema_error",
    "tool_execution_error",
    "guardrail_rejection",
    "stop_gate_rejection",
    "empty_response",
    "truncated_output",
    "slop_quality_rejection",
    "incomplete_todo",
]


@dataclass(frozen=True)
class TurnFailureDiagnostic:
    """Structured diagnostic describing what failed in a turn, why, and how to fix it."""

    turn_number: int
    category: TurnFailureCategory
    what_failed: str
    root_cause: str
    actionable_remediation: str
    tool_name: Optional[str] = None
    failed_parameters: Optional[Dict[str, object]] = None
    expected_schema_summary: Optional[str] = None

    def format_directive(self) -> str:
        """Render a high-signal self-correction block for injection into the agent context."""
        lines = [
            f"[TURN FAILURE DIAGNOSTIC — TURN {self.turn_number} SELF-CORRECTION REQUIRED]",
            f"• Failure Category: {self.category}",
            f"• What Failed: {self.what_failed}",
            f"• Root Cause: {self.root_cause}",
            f"• Required Remediation: {self.actionable_remediation}",
        ]
        if self.expected_schema_summary:
            lines.append(f"• Expected Schema Contract: {self.expected_schema_summary}")
        lines.append(
            "Do NOT stop, apologize, or repeat the identical failing call. Execute the Required Remediation now."
        )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, object]:
        """Serialize diagnostic for inclusion in structured tool_result payloads."""
        payload: Dict[str, object] = {
            "turn_number": self.turn_number,
            "category": self.category,
            "what_failed": self.what_failed,
            "root_cause": self.root_cause,
            "actionable_remediation": self.actionable_remediation,
            "directive": self.format_directive(),
        }
        if self.tool_name:
            payload["tool_name"] = self.tool_name
        if self.expected_schema_summary:
            payload["expected_schema_summary"] = self.expected_schema_summary
        return payload


class TurnFailureDiagnosticBuilder:
    """Factory methods constructing TurnFailureDiagnostic objects from runtime failures."""

    @staticmethod
    def summarize_schema(schema: Optional[Dict[str, object]], focus_fields: Optional[List[str]] = None) -> str:
        """Build a compact human- and LLM-readable summary of required fields, types, and enums."""
        if not schema or not isinstance(schema, dict):
            return ""
        raw_props = schema.get("properties")
        props: Dict[str, object] = raw_props if isinstance(raw_props, dict) else {}
        raw_req = schema.get("required")
        required: List[str] = [str(r) for r in raw_req] if isinstance(raw_req, list) else []

        target_keys = focus_fields if focus_fields else (required if required else list(props.keys())[:10])
        parts: List[str] = []
        for key in target_keys:
            prop_spec = props.get(key)
            if not isinstance(prop_spec, dict):
                parts.append(f"{key} (required)" if key in required else key)
                continue
            p_type = prop_spec.get("type", "any")
            enum_vals = prop_spec.get("enum")
            req_tag = "REQUIRED" if key in required else "optional"
            if isinstance(enum_vals, list) and enum_vals:
                parts.append(f"{key}: {p_type} [{req_tag}, enum={enum_vals}]")
            else:
                parts.append(f"{key}: {p_type} [{req_tag}]")

        if required:
            return f"Required keys={required}; Specs={{ {'; '.join(parts)} }}"
        return f"Specs={{ {'; '.join(parts)} }}"

    @classmethod
    def from_schema_validation_error(
        cls,
        turn_number: int = 0,
        tool_name: str = "",
        tool_input: Optional[Dict[str, object]] = None,
        error_msg: str = "",
        schema: Optional[Dict[str, object]] = None,
    ) -> TurnFailureDiagnostic:
        """Create a diagnostic for pre-execution JSON schema validation failures."""
        actual_input = tool_input if isinstance(tool_input, dict) else {}
        provided_keys = sorted(str(k) for k in actual_input.keys())
        raw_req = schema.get("required") if isinstance(schema, dict) else None
        required_keys = [str(r) for r in raw_req] if isinstance(raw_req, list) else []
        missing_keys = [k for k in required_keys if k not in provided_keys]

        focus = missing_keys if missing_keys else required_keys
        schema_summary = cls.summarize_schema(schema, focus_fields=focus if focus else None)

        if missing_keys:
            root_cause = (
                f"Tool call to '{tool_name}' omitted mandatory schema properties: {missing_keys}. "
                f"Provided keys were: {provided_keys}. Validator message: {error_msg}"
            )
            remediation = (
                f"Re-invoke '{tool_name}' immediately in your next turn and include all missing mandatory keys "
                f"({', '.join(missing_keys)}) with grounded values conforming to the schema."
            )
        else:
            root_cause = (
                f"Tool call to '{tool_name}' failed parameter type/enum validation: {error_msg}. "
                f"Provided keys: {provided_keys}."
            )
            remediation = (
                f"Inspect the Expected Schema Contract for '{tool_name}', correct the invalid parameter type or "
                f"enum value, and re-invoke '{tool_name}'."
            )

        return TurnFailureDiagnostic(
            turn_number=turn_number,
            category="tool_schema_error",
            what_failed=f"Schema validation rejected tool call '{tool_name}'.",
            root_cause=root_cause,
            actionable_remediation=remediation,
            tool_name=tool_name,
            failed_parameters=actual_input,
            expected_schema_summary=schema_summary or None,
        )

    @classmethod
    def from_tool_execution_error(
        cls,
        turn_number: int = 0,
        tool_name: str = "",
        tool_input: Optional[Dict[str, object]] = None,
        error_msg: str = "",
        error_str: Optional[str] = None,
    ) -> TurnFailureDiagnostic:
        """Create a diagnostic for runtime tool execution errors or domain validation rejections."""
        actual_err = error_msg or error_str or "Unknown execution error"
        actual_input = tool_input if isinstance(tool_input, dict) else {}
        err_lower = actual_err.lower()
        if "ditolak" in err_lower or "rejected" in err_lower or "validation" in err_lower or "missing_" in err_lower:
            root_cause = f"Domain/business validation rejected '{tool_name}' payload: {actual_err}"
            remediation = (
                f"Address every specific validation error listed in '{actual_err}' (e.g. missing prerequisite tool "
                f"calls, invalid R:R or SL/TP geometry, weak invalidation, or missing currency bias) and re-submit "
                f"'{tool_name}' with corrected parameters."
            )
        elif "timeout" in err_lower or "timed out" in err_lower or "connection" in err_lower:
            root_cause = (
                f"Transient infrastructure timeout/connection error while executing '{tool_name}': {actual_err}"
            )
            remediation = (
                f"Do not abort the task. Either retry '{tool_name}' once with narrower parameters or proceed using "
                f"already pre-fetched context data while explicitly noting the unavailable source."
            )
        else:
            compact_args = ""
            try:
                compact_args = json.dumps(actual_input, default=str)[:200]
            except Exception:
                compact_args = str(actual_input)[:200]
            root_cause = f"Execution of '{tool_name}' with args {compact_args} raised an error: {actual_err}"
            remediation = (
                f"Verify parameter names and values for '{tool_name}', fix the cause of '{actual_err}', "
                f"and continue executing the remaining steps to complete the task."
            )

        return TurnFailureDiagnostic(
            turn_number=turn_number,
            category="tool_execution_error",
            what_failed=f"Tool '{tool_name}' returned an execution or validation error.",
            root_cause=root_cause,
            actionable_remediation=remediation,
            tool_name=tool_name,
            failed_parameters=actual_input,
        )

    @classmethod
    def from_guardrail_verdict(
        cls,
        turn_number: int,
        tool_name: str,
        guard_name: str,
        reason: str,
        suggested_fix: Optional[str] = None,
    ) -> TurnFailureDiagnostic:
        """Create a diagnostic when a tool call is blocked or suppressed by ToolGuardrailController."""
        remediation = suggested_fix or (
            f"Comply with {guard_name}: do not repeat blocked call '{tool_name}'. "
            f"Satisfy the prerequisite action or synthesize already gathered observations to conclude."
        )
        return TurnFailureDiagnostic(
            turn_number=turn_number,
            category="guardrail_rejection",
            what_failed=f"Guardrail '{guard_name}' intercepted tool '{tool_name}'.",
            root_cause=reason,
            actionable_remediation=remediation,
            tool_name=tool_name,
        )

    @classmethod
    def from_stop_gate_rejection(
        cls,
        turn_number: int,
        gate_name: str,
        reason: str,
        remaining_turns: int,
    ) -> TurnFailureDiagnostic:
        """Create a diagnostic when a turn attempts to finish but is blocked by a stop gate."""
        return TurnFailureDiagnostic(
            turn_number=turn_number,
            category="stop_gate_rejection",
            what_failed=f"Premature turn completion blocked by '{gate_name}'.",
            root_cause=reason,
            actionable_remediation=(
                f"You have {remaining_turns} turn(s) remaining. Fulfill the exact requirement of '{gate_name}' "
                f"({reason}) before attempting to conclude."
            ),
        )

    @classmethod
    def from_slop_rejection(
        cls,
        turn_number: int,
        violations: List[str],
        stage_name: str,
    ) -> TurnFailureDiagnostic:
        """Create a diagnostic when final text or submission violates the Anti-Slop Quality Gate."""
        joined = "; ".join(violations)
        return TurnFailureDiagnostic(
            turn_number=turn_number,
            category="slop_quality_rejection",
            what_failed=f"Output quality rejected by AntiSlopQualityGate in stage '{stage_name}'.",
            root_cause=f"Detected AI slop, placeholder text, or ungrounded filler: {joined}",
            actionable_remediation=(
                "Rewrite the output immediately with high information density, concrete numerical anchors, "
                "causal mechanisms, and zero AI filler phrases, placeholders, or emoticons."
            ),
        )
