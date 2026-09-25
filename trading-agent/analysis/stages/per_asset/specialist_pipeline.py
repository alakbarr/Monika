# ==============================================================================
# File: analysis/stages/per_asset/specialist_pipeline.py
# ==============================================================================

import asyncio
import logging
import json
import sys
from datetime import datetime, timezone
from typing import Optional, Any, Callable, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

def _get_clock():
    pas = sys.modules.get("analysis.stages.per_asset_stage")
    if pas and hasattr(pas, "clock"):
        return pas.clock
    return clock

from analysis.providers.llm_factory import get_client_for_task
from analysis.stages.per_asset.context_builder import (
    SPECIALIST_PROMPTS, _render_specialist_prompt, SYMBOL_TO_COT
)

logger = logging.getLogger("TradingAgent.PerAsset.SpecialistPipeline")

class SpecialistPipelineMixin:
    """Mixin untuk eksekusi specialist debate pipeline dan verifikasi second opinion."""

    settings: Dict[str, Any]
    _specialist_weights_cache: Dict[str, Any]

    _SPECIALIST_KEY_MAP = {
        'technical': ['get_technical_indicators_D1', 'get_technical_indicators_H4', 'get_technical_indicators_H1',
                      'get_atr_H4', 'get_price_history_H4', 'get_price_history_H1', 'price_history_D1_recent',
                      'get_swing_points_H4', 'get_structure_breaks_H4', 'get_smc_zones_H4',
                      'get_fibonacci_levels_H4', 'get_liquidity_sweep_context', 'get_volume_profile_context',
                      'get_volatility_regime_H4', 'market_regime', 'structure_breaks_D1', 'smc_zones_D1',
                      'timesfm_forecast', 'market_chronicle', 'recent_lessons', 'pattern_similarity'],
        'sentiment': ['cot_report', 'retail_sentiment', 'fxssi_sentiment', 'fear_greed_index', 'funding_rate', 'recent_news',
                      'market_chronicle', 'recent_lessons', 'market_regime', 'user_market_intel'],
        'macro': ['get_fundamental_brief', 'get_dxy', 'get_economic_calendar', 'get_market_session',
                  'get_macro_bias_score', 'priced_in_subscores', 'recent_news', 'market_chronicle', 'recent_lessons', 'user_market_intel',
                  'interest_rates', 'get_interest_rates', 'fedwatch_probabilities', 'get_fedwatch_probabilities',
                  'central_bank_expectations', 'get_central_bank_expectations',
                  'bond_yield_spreads', 'get_bond_yield_spreads', 'treasury_yields', 'get_treasury_yields', 'timesfm_forecast'],
    }

    async def _get_specialist_reliability_cached(self, session) -> dict:
        """Full reliability dict per specialist: {trust_weight, chronically_unreliable, accuracy_pct, total}."""
        from datetime import datetime, timezone
        now = _get_clock().now()
        cache = self._specialist_weights_cache
        if cache['weights'] and cache['ts'] and (now - cache['ts']).total_seconds() < 6 * 3600:
            return cache['weights']
        try:
            from utils.analytics.specialist_tracker import compute_specialist_reliability
            data = await compute_specialist_reliability(session)
            specialists = data.get('specialists', {})
        except Exception as e:
            logger.debug(f'Specialist reliability fetch failed, using defaults: {e}')
            specialists = {}
        defaults = {
            'technical': {'trust_weight': 1.0, 'chronically_unreliable': False},
            'sentiment': {'trust_weight': 0.7, 'chronically_unreliable': False},
            'macro': {'trust_weight': 1.0, 'chronically_unreliable': False},
        }
        final = {name: specialists.get(name, default) for name, default in defaults.items()}
        self._specialist_weights_cache = {'weights': final, 'ts': now}
        return final

    async def _get_specialist_trust_weights(self, session) -> dict:
        """Helper to get just the trust weights for injection into context."""
        rel = await self._get_specialist_reliability_cached(session)
        return {name: metrics['trust_weight'] for name, metrics in rel.items()}

    async def _execute_specialist_debate_pipeline(
        self,
        session: AsyncSession,
        symbol: str,
        raw_bundle_data: dict,
    ) -> tuple[str, dict, dict, dict]:
        """Mengeksekusi analisis spesialis (teknikal, sentimen, makro) dan menyusun sintesis adjudikasi."""
        specialist_biases: dict[str, str] = {}
        specialist_confidence: dict[str, str] = {}
        specialist_trust: dict[str, float] = {}
        extra_context_str = ""

        try:
            tech_client = get_client_for_task('specialist_technical', self.settings)
            sent_client = get_client_for_task('specialist_sentiment', self.settings)
            macro_client = get_client_for_task('specialist_macro', self.settings)

            # Cap domain specialist reasoning tokens to prevent excessive token burn
            for sc in (tech_client, sent_client, macro_client):
                if hasattr(sc, 'set_thinking_budget'):
                    sc.set_thinking_budget(1024)
                elif hasattr(sc, 'thinking_budget'):
                    sc.thinking_budget = 1024

            # SOTA Memory Link: Ensure active structural macro events are present for domain specialists
            if isinstance(raw_bundle_data, dict) and 'market_chronicle' not in raw_bundle_data:
                try:
                    from analysis.memory.chronicle_writer import ChronicleWriter
                    c_bullets = await ChronicleWriter(self.settings).get_condensed_chronicle_bullets(session, symbol=symbol, limit=3)
                    if c_bullets:
                        raw_bundle_data['market_chronicle'] = c_bullets
                except Exception:
                    pass

            if isinstance(raw_bundle_data, dict) and 'user_market_intel' not in raw_bundle_data:
                try:
                    from database.models import UserMarketIntel
                    from sqlalchemy import or_
                    now_intel = _get_clock().now()
                    intel_rows = (await session.execute(
                        select(UserMarketIntel).where(
                            UserMarketIntel.is_active == True,
                            or_(UserMarketIntel.expires_at.is_(None), UserMarketIntel.expires_at > now_intel)
                        ).order_by(UserMarketIntel.created_at.desc())
                    )).scalars().all()
                    rel_bullets = []
                    sym_clean = symbol.upper().replace('/', '')
                    for r in intel_rows:
                        aff_list = r.affected_symbols_list if hasattr(r, "affected_symbols_list") else (
                            [s.strip() for s in (r.affected_symbols or "").split(",") if s.strip()]
                        )
                        aff = [s.upper().replace('/', '') for s in aff_list]
                        if not aff or "ALL" in aff or sym_clean in aff:
                            rel_bullets.append(f"[{r.intel_type.upper()} - {r.directive}]: {r.title} — {r.summary}")
                    if rel_bullets:
                        raw_bundle_data['user_market_intel'] = rel_bullets
                except Exception:
                    pass

            tech_data_view = self._build_structured_specialist_view(raw_bundle_data, 'technical')
            sent_data_view = self._build_structured_specialist_view(raw_bundle_data, 'sentiment')
            macro_data_view = self._build_structured_specialist_view(raw_bundle_data, 'macro')

            from utils.protocol.context_coherence import get_base_quote_tags
            currencies = get_base_quote_tags(symbol).split(',')
            base_currency = currencies[0].strip() if currencies else 'USD'
            quote_currency = currencies[1].strip() if len(currencies) > 1 else 'USD'

            SPECIALIST_RESPONSE_SCHEMA_EXTENDED = {
                "type": "object",
                "properties": {
                    "directional_bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
                    "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "nearest_entry_zone": {"type": "object", "properties": {"type": {"type": "string"}, "price_high": {"type": "number"}, "price_low": {"type": "number"}, "direction": {"type": "string"}}},
                    "structural_sl": {"type": "object", "properties": {"price": {"type": "number"}, "basis": {"type": "string"}}},
                    "cot_net_position": {"type": "object", "properties": {"value": {"type": "number"}, "bias": {"type": "string"}, "is_extreme": {"type": "boolean"}}},
                    "retail_positioning": {"type": "object", "properties": {"long_pct": {"type": "number"}, "contrarian_signal": {"type": "string"}}},
                    "base_currency_bias": {"type": "string"},
                    "quote_currency_bias": {"type": "string"},
                    "dxy_alignment": {"type": "string"},
                    "priced_in_risk": {"type": "string"},
                    "key_evidence": {"type": "array", "items": {"type": "string"}},
                    "invalidation_condition": {"type": "string"},
                    "analysis": {"type": "string"}
                },
                "required": ["directional_bias", "confidence", "key_evidence", "invalidation_condition", "analysis"]
            }

            async def run_specialist_with_schema(client, role_desc, data_view):
                from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
                target_header = f"[TARGET ASSET]: {symbol} (Base: {base_currency}, Quote: {quote_currency})\n\n"
                telegraphic_specialist_directive = (
                    "\n[TELEGRAPHIC MANDATE]: Think strictly in dense analytical bullet points. "
                    "Output valid JSON strictly matching the schema. Analysis field must be at most 2 concise sentences. "
                    "Zero conversational pleasantries, zero fluff."
                )
                anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
                anchored_sys = f"{anchor}\n\n---\n\n{role_desc}{telegraphic_specialist_directive}"
                result_str = await client.generate_content(
                    system_prompt=anchored_sys,
                    user_message=target_header + data_view,
                    response_schema=SPECIALIST_RESPONSE_SCHEMA_EXTENDED,
                    max_tokens=max(getattr(client, 'max_tokens', 4096) or 4096, 4096)
                )
                try:
                    result = json.loads(result_str) if isinstance(result_str, str) else result_str
                    return result or {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'FAILED', 'key_evidence': [], 'invalidation_condition': 'N/A', 'analysis': 'No analysis generated'}
                except Exception:
                    return {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'FAILED', 'key_evidence': [], 'invalidation_condition': 'N/A', 'analysis': result_str or ''}

            # ── H3: Isolated Subagent Execution ──
            async def run_specialist_isolated(role, client, prompt, data_view):
                try:
                    return await asyncio.wait_for(
                        run_specialist_with_schema(client, prompt, data_view),
                        timeout=180.0
                    )
                except asyncio.TimeoutError:
                    logger.error(f"[{symbol}] Specialist {role} timed out after 180s")
                    return {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'TIMEOUT', 'key_evidence': [], 'invalidation_condition': 'N/A', 'analysis': 'Specialist timed out'}
                except Exception as e:
                    logger.error(f"[{symbol}] Specialist {role} raised error: {e}")
                    return {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'FAILED', 'key_evidence': [], 'invalidation_condition': 'N/A', 'analysis': str(e)}

            tech_res, sent_res, macro_res = await asyncio.gather(
                run_specialist_isolated('technical', tech_client, SPECIALIST_PROMPTS['technical'], tech_data_view),
                run_specialist_isolated('sentiment', sent_client, SPECIALIST_PROMPTS['sentiment'], sent_data_view),
                run_specialist_isolated('macro', macro_client, SPECIALIST_PROMPTS['macro'], macro_data_view),
                return_exceptions=True,
            )

            for name, res in (('technical', tech_res), ('sentiment', sent_res), ('macro', macro_res)):
                if isinstance(res, BaseException):
                    logger.error(f'[{symbol}] Specialist {name} failed: {res}')

            tech_res = tech_res if not isinstance(tech_res, BaseException) else {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'FAILED'}
            sent_res = sent_res if not isinstance(sent_res, BaseException) else {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'FAILED'}
            macro_res = macro_res if not isinstance(macro_res, BaseException) else {'directional_bias': 'UNAVAILABLE', 'confidence': 'LOW', 'status': 'FAILED'}

            for name, report in [('technical', tech_res), ('sentiment', sent_res), ('macro', macro_res)]:
                if isinstance(report, dict) and 'directional_bias' in report:
                    bias = str(report['directional_bias']).lower()
                    if bias in ('bullish', 'bearish'):
                        specialist_biases[name] = bias
                    elif bias == 'unavailable':
                        specialist_biases[name] = 'unavailable'
                    else:
                        specialist_biases[name] = 'mixed/neutral'
                    specialist_confidence[name] = str(report.get('confidence', 'LOW')).lower()
                else:
                    specialist_biases[name] = 'unavailable'
                    specialist_confidence[name] = 'low'

            CONFIDENCE_LEVEL_WEIGHT = {'high': 1.0, 'medium': 0.6, 'low': 0.3}
            specialist_trust = await self._get_specialist_trust_weights(session)
            def _weight(n):
                if specialist_biases.get(n) == 'unavailable':
                    return 0.0
                return CONFIDENCE_LEVEL_WEIGHT.get(specialist_confidence.get(n, 'low'), 0.3) * specialist_trust.get(n, 1.0)
            weighted_bullish = sum(_weight(n) for n in specialist_biases if specialist_biases[n] == 'bullish')
            weighted_bearish = sum(_weight(n) for n in specialist_biases if specialist_biases[n] == 'bearish')
            distinct_biases = set(v for v in specialist_biases.values() if v in ('bullish', 'bearish'))
            significant_disagreement = len(distinct_biases) >= 2 and weighted_bullish >= 0.6 and weighted_bearish >= 0.6
            if significant_disagreement:
                try:
                    from database.models import SystemConfig
                    from sqlalchemy import select as _sel3
                    key = f'specialist_disagreement_{symbol}'
                    cfg = (await session.execute(_sel3(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                    val = json.dumps({'biases': specialist_biases, 'flagged_at': _get_clock().now().isoformat()})
                    if cfg:
                        cfg.value = val
                    else:
                        session.add(SystemConfig(key=key, value=val))
                    await session.commit()
                except Exception as e:
                    logger.debug(f'Failed to persist specialist disagreement flag: {e}')

            try:
                from database.models import SystemConfig
                from sqlalchemy import select as _sel_biases
                biases_payload = json.dumps({
                    'biases': specialist_biases,
                    'confidence': specialist_confidence,
                    'trust_weights_used': {k: round(specialist_trust.get(k, 1.0), 3) for k in specialist_biases},
                    'computed_at': _get_clock().now().isoformat(),
                })
                _biases_key = f'pending_specialist_biases_{symbol}'
                _biases_cfg = (await session.execute(
                    _sel_biases(SystemConfig).where(SystemConfig.key == _biases_key)
                )).scalar_one_or_none()
                if _biases_cfg:
                    _biases_cfg.value = biases_payload
                else:
                    session.add(SystemConfig(key=_biases_key, value=biases_payload))
                await session.commit()
            except Exception as e:
                logger.debug(f'[{symbol}] Failed to persist specialist biases for trust tracking: {e}')

            # Specialist Distillation Contract: compact reports to prevent context bloat
            def _distill_specialist_report(rep: Any, max_chars: int = 400) -> str:
                if not isinstance(rep, dict):
                    return str(rep)[:max_chars]
                distilled = {
                    "bias": rep.get("directional_bias", "NEUTRAL"),
                    "conf": rep.get("confidence", "LOW"),
                    "zone": rep.get("nearest_entry_zone"),
                    "sl": rep.get("structural_sl"),
                    "signals": (rep.get("key_signals") or rep.get("signals") or rep.get("key_evidence") or [])[:3],
                    "summary": str(rep.get("analysis") or rep.get("summary") or rep.get("rationale") or "")[:200]
                }
                # Drop None / empty entries to minimize tokens
                compact = {k: v for k, v in distilled.items() if v}
                return json.dumps(compact, ensure_ascii=False)

            extra_context_str += '\n\n--- SPECIALIST REPORTS ---\n'
            extra_context_str += f'[Technical Analyst — Bias: {specialist_biases.get("technical", "unknown").upper()}]:\n{_distill_specialist_report(tech_res)}\n\n'
            extra_context_str += f'[Sentiment Analyst — Bias: {specialist_biases.get("sentiment", "unknown").upper()}]:\n{_distill_specialist_report(sent_res)}\n\n'
            extra_context_str += f'[Macro Analyst — Bias: {specialist_biases.get("macro", "unknown").upper()}]:\n{_distill_specialist_report(macro_res)}\n\n'

            t_weight = specialist_trust.get('technical', 1.0)
            m_weight = specialist_trust.get('macro', 1.0)
            s_weight = specialist_trust.get('sentiment', 0.7)

            full_reliability = await self._get_specialist_reliability_cached(session)
            chronic_names = [n for n in ('technical', 'sentiment', 'macro') if full_reliability.get(n, {}).get('chronically_unreliable', False)]
            chronic_notice = ''
            if chronic_names:
                chronic_notice = (
                    f"\n🚫 SPECIALIST TIDAK DAPAT DIPERCAYA (akurasi historis <40% dari 20+ trade): "
                    f"{', '.join(chronic_names)}. ABAIKAN arah/klaim dari specialist ini sepenuhnya dalam "
                    f"sintesis — jangan biarkan pendapat mereka mempengaruhi keputusan akhir, treat their "
                    f"report as if it were not provided.\n"
                )

            adjudication_framework = (
                f"\n## SYNTHESIS ADJUDICATION TRUST WEIGHTS\n"
                f"Technical Trust Weight: {t_weight:.2f} | Macro Trust Weight: {m_weight:.2f} | Sentiment Trust Weight: {s_weight:.2f}\n"
                f"{chronic_notice}\n"
            )
            extra_context_str += adjudication_framework

            # Subagent Blackboard Working Memory
            try:
                from analysis.subagent_blackboard import SubagentBlackboard
                blackboard = SubagentBlackboard(symbol)
                if isinstance(raw_bundle_data, dict):
                    blackboard.set_slot("market_invariants", {
                        "price": raw_bundle_data.get("current_price"),
                        "atr": raw_bundle_data.get("atr"),
                        "dxy": raw_bundle_data.get("dxy"),
                        "vix": raw_bundle_data.get("vix"),
                    })
                if isinstance(tech_res, dict) and tech_res.get("status") != "FAILED":
                    blackboard.set_slot("technical_poi", tech_res)
                if isinstance(sent_res, dict) and sent_res.get("status") != "FAILED":
                    blackboard.set_slot("sentiment_positioning", sent_res)
                if isinstance(macro_res, dict) and macro_res.get("status") != "FAILED":
                    blackboard.set_slot("macro_drivers", macro_res)

                bb_distilled = blackboard.export_distilled_context(max_tokens=600)
                if bb_distilled:
                    extra_context_str += f"\n\n[SUBAGENT BLACKBOARD MEMORY]:\n{bb_distilled}\n"
            except Exception as bb_err:
                logger.debug(f"[{symbol}] Blackboard export non-fatal: {bb_err}")

            if self.settings.get("scenario_tree", {}).get("enabled", False):
                try:
                    from analysis.scenario_tree import ScenarioTreeEngine
                    st_engine = ScenarioTreeEngine(self.settings)
                    cur_p = 0.0
                    if isinstance(raw_bundle_data, dict):
                        for k in ("get_technical_indicators_H4", "get_technical_indicators_D1", "get_technical_indicators_H1", "get_technical_indicators"):
                            t_val = raw_bundle_data.get(k)
                            if isinstance(t_val, dict):
                                ind = t_val.get("indicators", t_val)
                                if isinstance(ind, dict):
                                    raw_val = ind.get("close") if ind.get("close") is not None else ind.get("price")
                                    if raw_val is not None:
                                        try:
                                            cur_p = float(raw_val)
                                            if cur_p > 0:
                                                break
                                        except (ValueError, TypeError):
                                            pass
                        if cur_p <= 0:
                            for hk in ("get_price_history_H4", "get_price_history_H1", "price_history_D1_recent", "get_price_history"):
                                h_val = raw_bundle_data.get(hk)
                                if isinstance(h_val, dict) and h_val.get("bars"):
                                    cur_p = float(h_val["bars"][-1].get("close", 0.0))
                                    break
                                elif isinstance(h_val, list) and h_val:
                                    last_bar = h_val[-1]
                                    if isinstance(last_bar, dict) and "close" in last_bar:
                                        cur_p = float(last_bar.get("close", 0.0))
                                        break

                    if cur_p > 0:
                        d1_t = specialist_biases.get("technical", "NEUTRAL").upper()
                        macro_b = specialist_biases.get("macro", "NEUTRAL").upper()

                        cur_atr = cur_p * 0.005
                        cur_rsi = None
                        if isinstance(raw_bundle_data, dict):
                            atr_candidate = raw_bundle_data.get("atr")
                            if atr_candidate is not None:
                                try:
                                    cur_atr = float(atr_candidate)
                                except (ValueError, TypeError):
                                    pass
                            for k in ("get_technical_indicators_H4", "get_technical_indicators_D1", "get_technical_indicators_H1", "get_technical_indicators"):
                                t_val = raw_bundle_data.get(k)
                                if isinstance(t_val, dict):
                                    ind = t_val.get("indicators", t_val)
                                    if isinstance(ind, dict):
                                        if cur_atr == cur_p * 0.005:
                                            raw_atr = ind.get("ATR_14") or ind.get("ATR") or ind.get("atr")
                                            if isinstance(raw_atr, dict):
                                                raw_atr = raw_atr.get("value") or raw_atr.get("atr")
                                            if raw_atr is not None:
                                                try:
                                                    p_atr = float(raw_atr)
                                                    if p_atr > 0:
                                                        cur_atr = p_atr
                                                except (ValueError, TypeError):
                                                    pass
                                        if cur_rsi is None:
                                            raw_rsi = ind.get("RSI_14") or ind.get("RSI") or ind.get("rsi")
                                            if isinstance(raw_rsi, dict):
                                                raw_rsi = raw_rsi.get("value") or raw_rsi.get("rsi")
                                            if raw_rsi is not None:
                                                try:
                                                    cur_rsi = float(raw_rsi)
                                                except (ValueError, TypeError):
                                                    pass

                        confluence = 8
                        if isinstance(raw_bundle_data, dict):
                            raw_c = raw_bundle_data.get("confluence_score") or (raw_bundle_data.get("prescreen_result") or {}).get("confluence_score")
                            if raw_c is not None:
                                try:
                                    confluence = int(raw_c)
                                except (ValueError, TypeError):
                                    pass

                        drift = 1.0
                        if isinstance(raw_bundle_data, dict):
                            raw_d = raw_bundle_data.get("spread_drift") or raw_bundle_data.get("spread_ratio")
                            if raw_d is not None:
                                try:
                                    drift = float(raw_d)
                                except (ValueError, TypeError):
                                    pass

                        tree = st_engine.create_deterministic_tree(
                            symbol=symbol,
                            current_price=cur_p,
                            d1_trend=d1_t,
                            atr_14=cur_atr,
                            macro_bias=macro_b,
                            confluence_score=confluence,
                            spread_drift=drift,
                            rsi=cur_rsi
                        )
                        extra_context_str += f"\n\n## SCENARIO TREE MULTI-HYPOTHESIS BRANCHING\n"
                        extra_context_str += f"Expected Value: {tree.expected_value:.2f} | Scenario Decision: {tree.final_decision}\n"
                        for b_name, b_node in tree.branches.items():
                            extra_context_str += f"- {b_name.upper()}: Prob={b_node.probability:.0%}, RR={b_node.reward_risk_ratio:.1f}, Invalidation={b_node.invalidation_level:.5f}\n"
                except Exception as st_err:
                    logger.debug(f"[{symbol}] Scenario tree generation non-fatal error: {st_err}")

        except Exception as e:
            logger.error(f'Specialist decomposition failed, falling back to monolithic: {e}')

        return extra_context_str, specialist_biases, specialist_confidence, specialist_trust

    async def _run_second_opinion_check(self, session, symbol: str, analysis) -> dict:
        try:
            secondary = get_client_for_task('stage2_per_asset_secondary', self.settings)

            factors = []
            try:
                factors = json.loads(analysis.confluence_factors_json) if analysis.confluence_factors_json else []
            except Exception:
                pass
            entry_zone = {}
            try:
                entry_zone = json.loads(analysis.entry_zone) if analysis.entry_zone else {}
            except Exception:
                pass
            entry_px = entry_zone.get('price') or analysis.price_at_analysis
            rr = None
            if entry_px and analysis.stop_loss and analysis.take_profit:
                sl_d = abs(entry_px - analysis.stop_loss)
                tp_d = abs(entry_px - analysis.take_profit)
                rr = round(tp_d / sl_d, 2) if sl_d > 0 else None

            structured_summary = {
                'symbol': symbol, 'decision': analysis.decision,
                'confluence_score': analysis.confluence_score, 'confluence_factors': factors,
                'priced_in_score': analysis.priced_in_score,
                'entry': entry_px, 'stop_loss': analysis.stop_loss, 'take_profit': analysis.take_profit,
                'rr_ratio': rr, 'invalidation': analysis.invalidation,
                'rationale_excerpt': (analysis.rationale or '')[:800],
            }
            SECOND_OPINION_SCHEMA = {
                'type': 'object', 'properties': {
                    'agree': {'type': 'boolean'},
                    'disagreement_category': {'type': 'string', 'enum': [
                        'none', 'weak_rr', 'sl_too_tight', 'confluence_overstated',
                        'priced_in_risk_ignored', 'macro_conflict', 'other']},
                    'reason': {'type': 'string'}
                }, 'required': ['agree', 'disagreement_category', 'reason']
            }
            min_rr = float(self.settings.get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.3))
            sys_prompt = ("You are a skeptical second-opinion risk reviewer. Independently sanity-check "
                           f"this trade using ONLY the structured facts given. disagree=true if: R:R < {min_rr:.1f}, "
                           "confluence_score seems unsupported by listed factors, priced_in_score >= 7 without "
                           "clear justification in rationale, or rationale contradicts SL/TP direction.")
            result = await secondary.classify_json(
                prompt=f"Trade proposal:\n{json.dumps(structured_summary, indent=2)}",
                system_prompt=sys_prompt, schema=SECOND_OPINION_SCHEMA)
            return result or {'agree': True, 'disagreement_category': 'none',
                               'reason': 'second_opinion_call_failed_defaulting_agree'}
        except Exception as e:
            logger.debug(f'[{symbol}] Second opinion check failed (non-fatal): {e}')
            return {'agree': True, 'disagreement_category': 'none', 'reason': 'error_defaulting_agree'}

    def _build_structured_specialist_view(self, raw_bundle_data: dict, specialist: str) -> str:
        import json as _json
        keys = self._SPECIALIST_KEY_MAP.get(specialist, [])
        slice_data = {k: v for k, v in raw_bundle_data.items() if k in keys and v is not None}

        if not slice_data:
            return '(no structured data available for this specialist — flag low confidence)'

        if specialist == 'sentiment':
            has_valid_data = False
            for k, v in slice_data.items():
                v_str = str(v).lower()
                if not ('error' in v_str or 'not found' in v_str or 'unavailable' in v_str or 'failed' in v_str):
                    has_valid_data = True
                    break
            if not has_valid_data:
                return '(no structured data available for this specialist — flag low confidence)'

        # LSS Micro-Pruning for technical specialist: summarize large OHLCV bar lists
        if specialist == 'technical':
            for h_key in ('get_price_history_H4', 'get_price_history_H1', 'price_history_D1_recent'):
                val = slice_data.get(h_key)
                bars = None
                is_dict_wrapper = False
                if isinstance(val, list) and len(val) > 10:
                    bars = val
                elif isinstance(val, dict) and isinstance(val.get('bars'), list) and len(val['bars']) > 10:
                    bars = val['bars']
                    is_dict_wrapper = True

                if bars:
                    try:
                        closes = [float(b.get('close', 0)) for b in bars if isinstance(b, dict)]
                        highs = [float(b.get('high', 0)) for b in bars if isinstance(b, dict)]
                        lows = [float(b.get('low', 0)) for b in bars if isinstance(b, dict)]
                        extrema = {
                            "period_high": max(highs) if highs else None,
                            "period_low": min(lows) if lows else None,
                            "net_change": round(closes[-1] - closes[0], 5) if len(closes) >= 2 else 0,
                            "total_bars_available": len(bars)
                        }
                        compacted = {
                            "summary_extrema": extrema,
                            "recent_10_bars": bars[-10:]
                        }
                        if is_dict_wrapper:
                            slice_data[h_key]['bars'] = compacted
                        else:
                            slice_data[h_key] = compacted
                    except Exception:
                        if is_dict_wrapper:
                            slice_data[h_key]['bars'] = bars[-10:]
                        else:
                            slice_data[h_key] = bars[-10:]

        return _json.dumps(slice_data, separators=(',', ':'), default=str)


class SpecialistPipeline(SpecialistPipelineMixin):
    """Component for specialist debate pipeline orchestration via composition (H-1)."""
    def __init__(self, settings: Optional[dict] = None, runner: Optional[Any] = None):
        self.settings = settings or {}
        self.runner = runner
