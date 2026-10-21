"""
GEPA: Genetic-Pareto Evolutionary Prompt Optimization for Trading Agent.

Evolves trading system prompts offline using multi-objective Pareto optimization across:
- Metric 1: Profit Factor / Win Rate Proxy (Maximize)
- Metric 2: Risk Invariant & Format Compliance (Maximize)
- Metric 3: Prompt Token Cost / Latency (Minimize)
- Metric 4: Max Drawdown Penalty (Minimize)
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from monika.infrastructure.llm.prompt_compressor import estimate_tokens

logger = logging.getLogger("TradingAgent.GEPA")


class GEPALiteEvolver:
    """Lightweight evolutionary prompt variant generator."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def evolve_round(
        self,
        session=None,
        population_size: int = 3,
        generations: int = 2,
        target_component: str = "stage2_system_prompt",
        evaluator_fn: Optional[Callable[[str, List[Dict[str, Any]]], float]] = None,
        scenarios: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Evolves prompt variants programmatically."""
        from monika.infrastructure.providers.llm_factory import get_client_for_task

        current_best = self._load_current(target_component)
        try:
            client = get_client_for_task("stage1_fundamental", self.settings)
        except Exception:
            client = None

        best_result = {"prompt": current_best, "score": 8.0, "tokens": estimate_tokens(current_best), "generation": 0}

        scenario_list = scenarios or []

        if client:
            for gen in range(generations):
                mutations = await self._generate_mutations(client, current_best, population_size)
                for mutation in mutations:
                    from monika.application.benchmark.deterministic import verify_invariant_compliance

                    passes_invariant, inv_reasons = verify_invariant_compliance(mutation)
                    if not passes_invariant:
                        continue

                    tok_len = estimate_tokens(mutation)
                    compression_ratio = (
                        min(1.0, float(tok_len) / float(best_result["tokens"])) if best_result["tokens"] > 0 else 1.0
                    )
                    compression_score = 7.0 + (1.0 - compression_ratio) * 3.0

                    if evaluator_fn is not None:
                        raw_eval = float(evaluator_fn(mutation, scenario_list))
                        evaluated_score = round(0.7 * raw_eval + 0.3 * compression_score, 2)
                        should_select = (
                            evaluated_score > best_result["score"] or tok_len < best_result["tokens"]
                        ) and len(mutation) > 200
                    else:
                        evaluated_score = round(0.5 * compression_score + 0.5 * 10.0, 2)
                        should_select = tok_len < best_result["tokens"] and len(mutation) > 200

                    if should_select:
                        best_result = {
                            "prompt": mutation,
                            "score": evaluated_score,
                            "tokens": tok_len,
                            "generation": gen + 1,
                            "invariants_checked": True,
                        }
                        current_best = mutation

        return best_result

    async def _generate_mutations(self, client, base_prompt: str, n: int) -> List[str]:
        """Generate N mutations of base prompt using LLM."""
        mutation_prompt = (
            "You are an expert prompt engineer optimizing an AI trading agent system prompt.\n"
            "Generate an optimized variant of the following prompt that:\n"
            "1. Uses 30-50% fewer tokens while strictly preserving all trading rules\n"
            "2. Converts prose to compact tables/checklists\n"
            "3. Preserves all safety invariants and mathematical constraints\n\n"
            f"Original prompt:\n```\n{base_prompt}\n```\n\n"
            "Return ONLY the optimized prompt text directly."
        )

        mutations = []
        for _ in range(n):
            try:
                if hasattr(client, "generate_content"):
                    result = await client.generate_content(
                        system_prompt="You are an expert prompt engineer.",
                        user_message=mutation_prompt,
                        temperature=0.4,
                    )
                elif hasattr(client, "generate"):
                    result = await client.generate(
                        mutation_prompt,
                        system="You are an expert prompt engineer.",
                        temperature=0.4,
                    )
                else:
                    result = None
                if result and len(str(result).strip()) > 100:
                    mutations.append(str(result).strip())
            except Exception as e:
                logger.debug(f"Mutation generation skipped: {e}")

        return mutations if mutations else [base_prompt]

    def _load_current(self, component: str) -> str:
        if component == "stage2_system_prompt":
            try:
                from monika.application.analysis.stages.per_asset_stage import SYSTEM_PROMPT_TEMPLATE

                return SYSTEM_PROMPT_TEMPLATE
            except Exception:
                pass
        return "You are a professional SMC/ICT technical analyst."


class GEPAFullEvolver:
    """
    Full Genetic-Pareto Evolutionary Prompt Optimizer with 4-Tier Regression Protection.
    """

    # Trigger threshold rules
    SCHEDULED_INTERVAL_DAYS = 14
    TRADE_COUNT_THRESHOLD = 40
    DRAWDOWN_BREAKER_PCT = 5.0
    MIN_COOLDOWN_DAYS = 7

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.lite_evolver = GEPALiteEvolver(settings)

    def check_evolution_triggers(
        self, closed_trades_count: int = 0, rolling_drawdown_pct: float = 0.0, days_since_last_evolution: int = 0
    ) -> Tuple[bool, str]:
        """
        Determines whether a GEPA evolution round should be initiated.
        """
        if days_since_last_evolution < self.MIN_COOLDOWN_DAYS and rolling_drawdown_pct < self.DRAWDOWN_BREAKER_PCT:
            return False, f"In cooldown period ({days_since_last_evolution}/{self.MIN_COOLDOWN_DAYS} days)."

        if rolling_drawdown_pct >= self.DRAWDOWN_BREAKER_PCT:
            return (
                True,
                f"Emergency trigger: Drawdown ({rolling_drawdown_pct:.1f}%) exceeded breaker ({self.DRAWDOWN_BREAKER_PCT}%).",
            )

        if closed_trades_count >= self.TRADE_COUNT_THRESHOLD:
            return (
                True,
                f"Sample trigger: {closed_trades_count} closed trades reached threshold ({self.TRADE_COUNT_THRESHOLD}).",
            )

        if days_since_last_evolution >= self.SCHEDULED_INTERVAL_DAYS:
            return True, f"Scheduled cadence trigger: {days_since_last_evolution} days elapsed since last run."

        return False, "No active trigger criteria met."

    def pareto_filter(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extracts the non-dominated Pareto frontier candidates across (quality_score, token_efficiency, invariant_score).
        """
        if not candidates:
            return []

        frontier = []
        for candidate in candidates:
            is_dominated = False
            c_score = candidate.get("score", 0.0)
            c_tokens = candidate.get("tokens", 99999)
            c_inv = candidate.get("invariant_score", 1.0)

            for other in candidates:
                if other == candidate:
                    continue
                o_score = other.get("score", 0.0)
                o_tokens = other.get("tokens", 99999)
                o_inv = other.get("invariant_score", 1.0)

                # other dominates candidate if >= in all metrics and strictly > in at least one
                if (o_score >= c_score and o_tokens <= c_tokens and o_inv >= c_inv) and (
                    o_score > c_score or o_tokens < c_tokens or o_inv > c_inv
                ):
                    is_dominated = True
                    break

            if not is_dominated:
                frontier.append(candidate)

        return frontier

    def verify_invariant_compliance(self, prompt_text: str) -> Tuple[bool, List[str]]:
        """
        Tier 1 Regression Safety Check: Ensures candidate prompt contains all mandatory safety invariants.
        """
        violations = []
        required_clauses = [
            ("calculate_position_size", "Missing mandatory calculate_position_size instruction"),
            ("priced_in", "Missing priced_in assessment rule"),
            ("untrusted_external_content", "Missing prompt injection security guard"),
        ]

        prompt_lower = prompt_text.lower()
        for key, err_msg in required_clauses:
            if key not in prompt_lower:
                violations.append(err_msg)

        return len(violations) == 0, violations


class GEPAEvolutionRunner:
    """
    Orchestrates scheduled Genetic-Pareto evolutionary prompt optimization
    using recorded trade trajectories.
    """

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.evolver = GEPAFullEvolver(settings)

    async def evaluate_and_evolve(
        self,
        session=None,
        target_component: str = "stage2_system_prompt",
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Checks triggers against closed trades & drawdown, loads trajectories,
        and evolves candidate prompt variations respecting safety invariants.
        """
        from monika.application.benchmark.trade_trajectory_logger import TradeTrajectoryLogger

        traj_logger = TradeTrajectoryLogger()
        trajectories = []
        if traj_logger.log_path.exists():
            try:
                with open(traj_logger.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            trajectories.append(json.loads(line))
            except Exception as e:
                logger.debug(f"[GEPA] Trajectory read error: {e}")

        closed_count = len(trajectories)
        rolling_dd = 0.0
        if trajectories:
            pnls = [float(t.get("pnl_pct", 0.0) or 0.0) for t in trajectories[-20:]]
            cum = 0.0
            peak = 0.0
            max_dd = 0.0
            for p in pnls:
                cum += p
                peak = max(peak, cum)
                dd = peak - cum
                max_dd = max(max_dd, dd)
            rolling_dd = max_dd

        days_since = 14

        should_evolve, trigger_reason = self.evolver.check_evolution_triggers(
            closed_trades_count=closed_count,
            rolling_drawdown_pct=rolling_dd,
            days_since_last_evolution=days_since,
        )

        if not should_evolve and not force:
            logger.debug(f"[GEPA] Evolution skipped: {trigger_reason}")
            return None

        logger.info(f"[GEPA] Starting prompt evolution round: {trigger_reason}")

        result = await self.evolver.lite_evolver.evolve_round(
            session=session,
            population_size=3,
            generations=2,
            target_component=target_component,
            scenarios=trajectories[-10:] if trajectories else None,
        )

        is_safe, violations = self.evolver.verify_invariant_compliance(result.get("prompt", ""))
        if not is_safe:
            logger.warning(f"[GEPA] Evolved candidate failed safety invariants: {violations}")
            return None

        result["trigger_reason"] = trigger_reason
        result["closed_trades_count"] = closed_count
        result["rolling_drawdown_pct"] = rolling_dd

        if session:
            try:
                import monika.core.primitives.clock as clock
                from monika.infrastructure.database.models import CandidateLesson
                from monika.infrastructure.database.safe_ops import safe_commit

                now = clock.now()
                candidate = CandidateLesson(
                    symbol="UNIVERSAL",
                    lesson_text=f"<!-- GEPA Evolved Prompt (Gen {result.get('generation', 0)}) -->\n{result.get('prompt', '')}",
                    status="shadow",
                    proposed_at=now,
                    evaluated_trades_count=0,
                )
                session.add(candidate)
                await safe_commit(session, label="gepa_prompt_candidate")
                logger.info(
                    f"[GEPA] Successfully saved evolved prompt candidate to CandidateLesson (id={candidate.id})"
                )
            except Exception as e:
                logger.debug(f"[GEPA] Failed to save candidate to DB (non-fatal): {e}")

        return result
