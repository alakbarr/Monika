import logging
import json
from typing import Optional, Any
from analysis.providers.llm_factory import get_client_for_task
import utils.clock as clock

logger = logging.getLogger("TradingAgent.TradeReflector")

LESSON_TAG_TAXONOMY = [
    'sl_too_tight', 'sl_too_wide', 'premature_entry', 'late_entry',
    'news_spike_sl_hit', 'spread_widening_sl_hit', 'tp_too_greedy', 'tp_too_conservative',
    'counter_trend_entry', 'chased_price', 'ignored_priced_in_risk',
    'correct_macro_wrong_timing', 'correct_timing_wrong_macro', 'regime_misread',
    'well_executed_setup', 'correlation_overexposure',
]

REFLECTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'reflection_text': {'type': 'string'},
        'lesson_tags': {'type': 'array', 'items': {'type': 'string', 'enum': LESSON_TAG_TAXONOMY}},
        'specific_lesson': {'type': 'string'},
        'next_trade_adjustment': {'type': 'string'},
        'alpha_lesson': {'type': 'string'},
        'process_was_sound': {
            'type': 'boolean',
            'description': (
                'TRUE if the original decision was logical based on information available AT THAT TIME, '
                'REGARDLESS of the final outcome. FALSE if the decision was process-flawed (e.g. '
                'confluence was actually weak, ignored evident red flags).'
            ),
        },
        'outcome_process_classification': {
            'type': 'string',
            'enum': ['good_process_good_outcome', 'good_process_bad_outcome',
                     'bad_process_good_outcome_lucky', 'bad_process_bad_outcome'],
        },
        'macro_thesis_correct': {
            'type': 'boolean',
            'description': 'True if core macro thesis proved correct, regardless of trade result'
        },
        'synthesis_adjudication_sound': {
            'type': 'boolean',
            'description': (
                'TRUE if final synthesis (specialist conflict adjudication, trust_weight assignment, '
                'debate judge decision) was logical based on specialist reports available AT THAT TIME — '
                'separate from whether the raw underlying data was accurate.'
            )
        },
    },
    'required': ['reflection_text', 'lesson_tags', 'specific_lesson', 'next_trade_adjustment',
                 'process_was_sound', 'outcome_process_classification', 'macro_thesis_correct',
                 'synthesis_adjudication_sound'],
}

class TradeReflector:
    def __init__(self, settings: Optional[dict] = None):
        if settings is None:
            import yaml, os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            try:
                with open(os.path.join(base_dir, 'config', 'settings.yaml'), 'r') as f:
                    settings = yaml.safe_load(f)
            except Exception:
                settings = {}
        self.settings: dict = settings or {}
        
    async def _fetch_enrichment_context(self, session, reflection) -> dict:
        """Kumpulkan konteks kaya: AssetAnalysis asli + temuan trade_autopsy."""
        enrichment = {}
        try:
            from database.models import AssetAnalysis
            ana = await session.get(AssetAnalysis, reflection.analysis_id)
            if ana:
                enrichment['confluence_score'] = ana.confluence_score
                enrichment['confluence_factors'] = (
                    json.loads(ana.confluence_factors_json) if ana.confluence_factors_json else []
                )
                try:
                    if hasattr(ana, 'specialist_biases_json') and ana.specialist_biases_json:
                        enrichment['specialist_biases'] = json.loads(ana.specialist_biases_json)
                except Exception:
                    pass
                enrichment['priced_in_score'] = ana.priced_in_score
                enrichment['entry_zone'] = ana.entry_zone
                enrichment['stop_loss'] = ana.stop_loss
                enrichment['take_profit'] = ana.take_profit
                enrichment['invalidation'] = ana.invalidation
                enrichment['debate_verdict'] = ana.debate_verdict
                if hasattr(ana, 'debate_bull_thesis') and ana.debate_bull_thesis:
                    enrichment['debate_bull_thesis'] = ana.debate_bull_thesis[:500]
                if hasattr(ana, 'debate_bear_dissent') and ana.debate_bear_dissent:
                    enrichment['debate_bear_dissent'] = ana.debate_bear_dissent[:500]
                if hasattr(ana, 'risk_multiplier') and ana.risk_multiplier is not None:
                    enrichment['risk_multiplier_applied'] = ana.risk_multiplier
        except Exception as e:
            logger.debug(f'AssetAnalysis enrichment fetch failed: {e}')

        try:
            from database.models import SystemConfig
            from sqlalchemy import select
            position_id = getattr(reflection, 'position_id', None)
            if position_id:
                key = f'autopsy_{reflection.symbol}_{position_id}'
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                if cfg and cfg.value:
                    autopsy_data = json.loads(cfg.value)
                    enrichment['autopsy_patterns'] = autopsy_data.get('patterns', [])
        except Exception as e:
            logger.debug(f'Autopsy fetch failed: {e}')

        try:
            from database.models import SystemConfig
            from sqlalchemy import select
            adv_key = f'adversarial_outcome_{reflection.analysis_id}'
            adv_cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == adv_key))).scalar_one_or_none()
            if adv_cfg and adv_cfg.value:
                adv_data = json.loads(adv_cfg.value)
                enrichment['adversarial_check_verdict'] = {
                    'hard_block': adv_data.get('hard_block'),
                    'recommend_block': adv_data.get('recommend_block'),
                    'quality': adv_data.get('quality'),
                }
        except Exception as e:
            logger.debug(f'Adversarial verdict fetch for reflection failed (non-fatal): {e}')

        try:
            from database.models import VIXData
            from sqlalchemy import select
            vix_res = await session.execute(
                select(VIXData).order_by(VIXData.date.desc()).limit(1)
            )
            vix_row = vix_res.scalar_one_or_none() if hasattr(vix_res, 'scalar_one_or_none') else None
            if vix_row and isinstance(getattr(vix_row, 'close', None), (int, float)):
                enrichment['vix_close'] = float(vix_row.close)
        except Exception as e:
            logger.debug(f'VIX context fetch for reflection failed: {e}')

        return enrichment

    def _verify_reflection_quality(self, data: Any, was_profitable: Optional[bool]) -> tuple[bool, str]:
        """
        Self-Critique Audit Gate for Reflection.
        Verifies that lessons are actionable, non-platitude, and factually aligned with trade outcome.
        """
        if not isinstance(data, dict):
            return False, "Response was not a valid dictionary structure."

        specific = str(data.get('specific_lesson', '')).strip().lower()
        if len(specific) < 20:
            return False, "specific_lesson is too terse (<20 characters); provide concrete technical context."

        PLATITUDES = [
            "be more careful", "follow the plan", "bad luck", "market was volatile",
            "do better next time", "stick to rules", "risk management is important",
            "sometimes market wins", "just noise"
        ]
        for plat in PLATITUDES:
            if plat in specific:
                return False, f"specific_lesson contains generic platitude '{plat}'. Must state exact technical rule."

        tags = data.get('lesson_tags', [])
        if not tags or not isinstance(tags, list):
            return False, "lesson_tags cannot be empty."

        invalid_tags = [t for t in tags if t not in LESSON_TAG_TAXONOMY]
        if invalid_tags:
            return False, f"lesson_tags contains invalid tags: {invalid_tags}. Use only LESSON_TAG_TAXONOMY."

        outcome_cls = data.get('outcome_process_classification')
        if was_profitable is True and outcome_cls in ('good_process_bad_outcome', 'bad_process_bad_outcome'):
            return False, f"Outcome conflict: trade was profitable but classified as '{outcome_cls}'."
        if was_profitable is False and outcome_cls == 'good_process_good_outcome':
            return False, "Outcome conflict: trade was a loss but classified as 'good_process_good_outcome'."

        return True, ""

    async def record_pending_reflection(
        self,
        session,
        analysis_id: int,
        symbol: str,
        decision: str,
        confidence: float,
        confluence_score: Optional[int],
        rationale: str,
        is_paper: bool = False,
        position_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Immediately append pending reflection at trade entry (I5).
        Decouples upfront decision capture from deferred post-mortem evaluation.
        """
        from database.models import DecisionReflection
        from database.safe_ops import safe_commit
        try:
            entry = DecisionReflection(
                analysis_id=analysis_id,
                symbol=symbol,
                decision=decision,
                confidence=confidence,
                confluence_score=confluence_score,
                rationale_summary=rationale,
                is_paper_whatif=is_paper,
                position_id=position_id,
                status="pending",
            )
            session.add(entry)
            await safe_commit(session, label="record_pending_reflection")
            return entry.id
        except Exception as e:
            logger.error(f"Failed to record pending reflection: {e}")
            return None

    async def deferred_evaluate_outcome(
        self,
        session,
        reflection_id: int,
        exit_price: float,
        exit_reason: str,
        pnl_usd: float,
        holding_hours: float,
        was_profitable: bool,
    ) -> None:
        """
        Update trade outcome metrics asynchronously when trade closes,
        then trigger reflective post-mortem analysis (I5).
        """
        from database.models import DecisionReflection
        from database.safe_ops import safe_commit
        reflection = await session.get(DecisionReflection, reflection_id)
        if not reflection:
            logger.warning(f"Deferred reflection evaluation: reflection #{reflection_id} not found.")
            return

        reflection.outcome_pnl_usd = pnl_usd
        reflection.exit_reason = exit_reason
        reflection.holding_hours = holding_hours
        reflection.was_profitable = was_profitable
        await safe_commit(session, label="deferred_outcome_metrics")

        # Now trigger the LLM post-mortem reflection
        await self.reflect_on_trade(session, reflection_id)

    async def reflect_on_trade(self, session, reflection_id: int):
        from database.models import DecisionReflection
        reflection = await session.get(DecisionReflection, reflection_id)
        if not reflection:
            return
            
        enrichment = await self._fetch_enrichment_context(session, reflection)
        client = get_client_for_task("trade_reflection", self.settings or {})
        
        alpha_text = f"Alpha vs {reflection.benchmark_name}: {reflection.alpha_return:.2f}%" if reflection.benchmark_name and reflection.alpha_return is not None else "No Alpha data."
        
        is_whatif = getattr(reflection, 'is_paper_whatif', False)
        if is_whatif:
            outcome_str = f"Hypothetical Outcome: {'Profitable' if reflection.whatif_direction_correct else 'Loss'} ({reflection.whatif_hypothetical_pnl_pips} pips)"
            exit_str = "Exit Reason: 24h Time Limit (Paper What-If)"
            holding_str = "Holding: 24h"
        else:
            outcome_str = f"Outcome: {'Profitable' if reflection.was_profitable else 'Loss'} (${reflection.outcome_pnl_usd})"
            exit_str = f"Exit Reason: {reflection.exit_reason}"
            holding_str = f"Holding: {reflection.holding_hours}h"
            
        user_msg = (
            f"Trade Rationale: {reflection.rationale_summary}\n"
            f"Decision: {reflection.decision} (Confidence: {reflection.confidence})\n"
            f"{outcome_str}\n"
            f"{exit_str}\n{holding_str}\n{alpha_text}\n"
            f"Enrichment Data: {json.dumps(enrichment)}"
        )
        
        sys_prompt = ("You are a trading post-mortem analyst. Use ONLY the tags from the provided enum. "
                      "specific_lesson and next_trade_adjustment must be concrete and actionable, "
                      "not generic platitudes like 'be more careful'. "
                      "If `adversarial_check_verdict` is present in the enrichment data, explicitly evaluate whether its warning "
                      "proved accurate or inaccurate compared to the actual outcome — incorporate this conclusion into `alpha_lesson`.")
        resp = await client.generate_content(system_prompt=sys_prompt, user_message=user_msg,
                                              response_schema=REFLECTION_SCHEMA)
        
        try:
            data = json.loads(resp) if isinstance(resp, str) else resp

            # Self-Correcting Reflection Critique Loop
            is_valid, critique = self._verify_reflection_quality(data, reflection.was_profitable)
            if not is_valid:
                logger.warning(f"Reflection critique triggered for #{reflection_id}: {critique}. Requesting self-correction.")
                refine_msg = (
                    f"{user_msg}\n\n"
                    f"CRITIQUE ON PREVIOUS DRAFT:\n"
                    f"Your previous reflection was rejected by the audit gate: {critique}\n"
                    f"Provide an improved, strictly concrete reflection with non-generic lessons matching actual outcome."
                )
                resp = await client.generate_content(system_prompt=sys_prompt, user_message=refine_msg,
                                                      response_schema=REFLECTION_SCHEMA)
                data = json.loads(resp) if isinstance(resp, str) else resp

            if isinstance(data, dict):
                reflection.reflection_text = data.get('reflection_text', '')
                reflection.lesson_tags = json.dumps(data.get('lesson_tags', []))
                reflection.specific_lesson = data.get('specific_lesson', '')
                reflection.next_trade_adjustment = data.get('next_trade_adjustment', '')
                reflection.alpha_lesson = data.get('alpha_lesson', '')
                reflection.process_was_sound = data.get('process_was_sound')
                reflection.outcome_process_classification = data.get('outcome_process_classification')
                reflection.status = "resolved"
                reflection.resolved_at = clock.now()
        except Exception as e:
            logger.error(f"Reflector JSON Parse Error: {e}")
        from database.safe_ops import safe_commit
        await safe_commit(session, label="trade_reflector")
        try:
            from database.event_store import TradingEventStore
            await TradingEventStore.emit(
                session=session,
                event_type="learning.reflection",
                payload={
                    "reflection_id": reflection_id,
                    "symbol": reflection.symbol,
                    "was_profitable": reflection.was_profitable,
                    "status": reflection.status,
                },
                correlation_id=f"reflection_{reflection_id}",
                actor="trade_reflector",
            )
        except Exception:
            pass

        # Closed-Loop Skill Crystallization
        if getattr(reflection, 'was_profitable', False):
            try:
                from analysis.memory.skill_crystallizer import SkillCrystallizer
                crystallizer = SkillCrystallizer(self.settings)
                await crystallizer.evaluate_and_crystallize(session, symbol=reflection.symbol)
            except Exception as cry_err:
                logger.debug(f"Skill crystallization non-fatal error: {cry_err}")
