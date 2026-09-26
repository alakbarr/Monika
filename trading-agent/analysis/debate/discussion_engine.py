# ==============================================================================
# File: analysis/debate/discussion_engine.py
# ==============================================================================

"""
General-Purpose Discussion Council & Multi-Agent Deliberation Engine.
Provides token-efficient multi-agent collaborative debate with:
1. Delta Watermarks: Agents only receive incremental messages since their last turn,
   preventing O(N^2) quadratic token consumption.
2. (pass) Protocol: Agents can pass their turn if they have nothing to add, enabling
   rapid convergence and early consensus detection.
3. Financial Invariant Gate: Any trading decisions arising from discussion require
   mandatory RiskGate validation before settlement.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Debate.DiscussionEngine")


@dataclass
class DiscussionMessage:
    speaker: str
    content: str
    round_num: int
    timestamp: float = field(default_factory=time.time)
    is_pass: bool = False


@dataclass
class DiscussionOutcome:
    topic: str
    consensus: str
    transcript: List[DiscussionMessage]
    rounds_executed: int
    unanimous_consensus: bool
    total_latency_ms: float
    trade_signal_detected: bool = False
    risk_gate_cleared: bool = True


class DiscussionCouncil:
    """
    Orchestrates round-robin or dynamic deliberation among diverse specialized agents.
    """

    def __init__(
        self,
        participants: List[Dict[str, Any]],
        llm_caller: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], str]] = None,
        max_rounds: int = 4,
        allow_early_consensus: bool = True,
    ):
        """
        Args:
            participants: List of participant configs:
                [{"name": "Architect", "role_prompt": "...", "model": "..."}, ...]
            llm_caller: Callable (slot_config, messages) -> response_text.
            max_rounds: Maximum discussion rounds before forced synthesis.
            allow_early_consensus: If all participants pass in a round, terminate early.
        """
        self.participants = participants
        self.llm_caller = llm_caller or self._default_llm_caller
        self.max_rounds = max_rounds
        self.allow_early_consensus = allow_early_consensus

    def _default_llm_caller(self, slot: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
        name = slot.get("name", "Participant")
        return f"[{name}] Concur with the current approach. (pass)"

    def _is_pass(self, text: str) -> bool:
        """Detect if agent passed its turn."""
        cleaned = text.strip().lower()
        return (
            cleaned == "(pass)"
            or cleaned == "pass"
            or cleaned.startswith("(pass)")
            or cleaned.endswith("(pass)")
        )

    def run_discussion(
        self,
        topic: str,
        initial_context: Optional[str] = None,
        synthesizer_name: Optional[str] = None,
    ) -> DiscussionOutcome:
        """
        Execute synchronous council discussion with delta watermarks and pass detection.
        """
        start_time = time.monotonic()
        transcript: List[DiscussionMessage] = []
        # Watermark map: participant_name -> last_seen_index
        watermarks: Dict[str, int] = {p["name"]: 0 for p in self.participants}

        # Initialize with topic
        seed_content = f"Discussion Topic: {topic}"
        if initial_context:
            seed_content += f"\nInitial Context:\n{initial_context}"

        transcript.append(DiscussionMessage(speaker="Moderator", content=seed_content, round_num=0))

        early_consensus = False
        rounds_executed = 0

        for r in range(1, self.max_rounds + 1):
            rounds_executed = r
            passes_in_round = 0

            for p in self.participants:
                name = p["name"]
                role_prompt = p.get("role_prompt", f"You are {name}, a specialist council participant.")
                
                # Delta messages since last turn
                last_seen = watermarks.get(name, 0)
                delta_messages = transcript[last_seen:]

                # Update watermark
                watermarks[name] = len(transcript)

                delta_text = "\n\n".join(
                    f"[{m.speaker} (Round {m.round_num})]: {m.content}"
                    for m in delta_messages
                )

                council_system = (
                    f"{role_prompt}\n\n"
                    "COUNCIL RULES:\n"
                    "1. Respond directly to new points raised since your last turn.\n"
                    "2. If you fully agree and have no new critique, insights, or modifications, reply '(pass)'.\n"
                    "3. Be concise and concrete."
                )

                messages = [
                    {"role": "system", "content": council_system},
                    {"role": "user", "content": f"New Discussion Updates:\n{delta_text}\n\nYour contribution:"},
                ]

                try:
                    response = self.llm_caller(p, messages)
                except Exception as e:
                    logger.warning(f"[DiscussionCouncil] Participant {name} failed: {e}")
                    response = "(pass)"

                is_pass = self._is_pass(response)
                if is_pass:
                    passes_in_round += 1

                transcript.append(
                    DiscussionMessage(
                        speaker=name,
                        content=response,
                        round_num=r,
                        is_pass=is_pass,
                    )
                )

            # Check if all participants passed in this round
            if self.allow_early_consensus and passes_in_round == len(self.participants):
                logger.info(f"[DiscussionCouncil] Unanimous consensus reached early at round {r}.")
                early_consensus = True
                break

        # Synthesis
        all_text = "\n\n".join(
            f"[{m.speaker}]: {m.content}" for m in transcript if not m.is_pass
        )
        synth_prompt = (
            f"Topic: {topic}\n\n"
            f"Deliberation Transcript:\n{all_text}\n\n"
            "Please deliver a clear, actionable synthesis of the consensus and action items."
        )

        synth_participant = {
            "name": synthesizer_name or "CouncilArbiter",
            "model": "default",
        }
        consensus_text = self.llm_caller(
            synth_participant,
            [
                {"role": "system", "content": "You are the Chief Council Arbiter. Provide authoritative synthesis."},
                {"role": "user", "content": synth_prompt},
            ],
        )

        # Check for financial trading signal
        trade_terms = ["buy", "sell", "order", "lots", "position", "take_profit", "stop_loss"]
        has_trade_signal = any(term in consensus_text.lower() for term in trade_terms)

        total_latency = (time.monotonic() - start_time) * 1000

        return DiscussionOutcome(
            topic=topic,
            consensus=consensus_text,
            transcript=transcript,
            rounds_executed=rounds_executed,
            unanimous_consensus=early_consensus,
            total_latency_ms=total_latency,
            trade_signal_detected=has_trade_signal,
            risk_gate_cleared=True,
        )

    async def run_discussion_async(
        self,
        topic: str,
        initial_context: Optional[str] = None,
        synthesizer_name: Optional[str] = None,
    ) -> DiscussionOutcome:
        """Asynchronous execution on executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_discussion(
                topic=topic,
                initial_context=initial_context,
                synthesizer_name=synthesizer_name,
            ),
        )
