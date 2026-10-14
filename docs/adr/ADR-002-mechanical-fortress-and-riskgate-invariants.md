# ADR-002: The Mechanical Fortress & RiskGate Invariants

## Status
Accepted

## Context
In automated algorithmic trading interacting with live financial broker sockets, probabilistic outputs from LLMs (such as generative trade hypotheses) cannot be trusted to execute trades directly. Any hallucination, unhandled prompt injection, or math drift could cause financial ruin.

## Decision
Mandate the "Mechanical Fortress" principle:
1. LLMs only propose; deterministic mathematical filters dispose.
2. Orders MUST pass through `RiskGate`: position sizing, margin limits, daily loss ceiling, risk-of-ruin bounds, and mandatory Stop-Loss validation.
3. Fail-Closed invariant: on any exception, timeout, NaN, or ambiguous risk value, the proposal is rejected immediately.
4. Default to simulated paper trading unless explicit authentication and operator confirmation are verified.

## Consequences
- **Positive**: Complete financial safety. Even if LLMs experience anomalous states or hallucinate invalid lot sizes, the mechanical gate blocks execution deterministically.
- **Trade-offs**: Slightly increased latency (sub-millisecond evaluation in pure Python) and rejection of trade ideas that do not meet strict risk invariants.
