# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/single_asset_helpers.py
# Description: Helper routines for single-asset analysis execution
# ==============================================================================

import json
import logging
import sys
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.stages.per_asset.context_builder import _flatten_system_prompt
from monika.infrastructure.database.models import PriceOHLCV, TechnicalIndicator
from monika.infrastructure.providers.llm_factory import create_client

logger = logging.getLogger("TradingAgent.PerAssetStage")


def _get_create_client():
    runner_mod = sys.modules.get("monika.application.analysis.stages.per_asset.runner")
    if runner_mod and hasattr(runner_mod, "create_client"):
        return runner_mod.create_client
    return create_client


async def compute_prompt_invariants(
    settings: dict,
    symbol: str,
    raw_bundle_data: Any,
    initial_context_blocks: list,
    session: Optional[AsyncSession] = None,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Compute zero-arithmetic invariants and format for prompt injection."""
    curr_px: Optional[float] = None
    atr_f: Optional[float] = None
    adr_f: Optional[float] = None
    try:
        from monika.application.analysis.calculators.invariant_calculator import (
            compute_trade_invariants,
            format_invariants_for_prompt,
        )

        if isinstance(raw_bundle_data, dict):
            hist = (
                raw_bundle_data.get("get_price_history_H4")
                or raw_bundle_data.get("get_price_history_H1")
                or raw_bundle_data.get("get_price_history")
            )
            if hist and isinstance(hist, dict) and hist.get("bars"):
                curr_px = hist["bars"][-1].get("close")
            if curr_px is None:
                ind = (
                    raw_bundle_data.get("get_technical_indicators_H4")
                    or raw_bundle_data.get("get_technical_indicators_D1")
                    or raw_bundle_data.get("get_technical_indicators")
                )
                if ind and isinstance(ind, dict):
                    curr_px = ind.get("current_close") or ind.get("close")
            atr_raw = (
                raw_bundle_data.get("get_atr_H4") or raw_bundle_data.get("get_atr_D1") or raw_bundle_data.get("get_atr")
            )
            atr_f = atr_raw.get("atr") if isinstance(atr_raw, dict) else atr_raw
            adr_raw = raw_bundle_data.get("daily_range_context") or raw_bundle_data.get("get_daily_range_context")
            adr_f = (
                (adr_raw.get("adr_5d") or adr_raw.get("adr") or adr_raw.get("effective_range"))
                if isinstance(adr_raw, dict)
                else None
            )
            smc_raw = raw_bundle_data.get("get_smc_zones_H4") or raw_bundle_data.get("get_smc_zones")
            if isinstance(smc_raw, list):
                smc_f = smc_raw
            elif isinstance(smc_raw, dict):
                smc_f = (
                    list(smc_raw.get("zones") or [])
                    + list(smc_raw.get("order_blocks") or [])
                    + list(smc_raw.get("fair_value_gaps") or smc_raw.get("fvg_zones") or [])
                )
            else:
                smc_f = []
            sr_raw = (
                raw_bundle_data.get("get_fibonacci_levels_H4")
                or raw_bundle_data.get("get_fibonacci_levels")
                or raw_bundle_data.get("get_optimal_intraday_levels")
            )
            sr_f = (
                list(sr_raw)
                if isinstance(sr_raw, list)
                else (list(sr_raw.get("levels") or sr_raw.get("sr_zones") or []) if isinstance(sr_raw, dict) else [])
            )
            if isinstance(smc_raw, dict) and isinstance(smc_raw.get("sr_zones"), list):
                sr_f.extend(smc_raw["sr_zones"])

            if curr_px and atr_f:
                h4_impulse = raw_bundle_data.get("h4_impulse_atr")
                if h4_impulse is None and hist and isinstance(hist, dict) and hist.get("bars"):
                    bars = hist["bars"]
                    closes = [float(b.get("close", 0)) for b in bars if isinstance(b, dict) and "close" in b]
                    if len(closes) >= 3 and atr_f and float(atr_f) > 0:
                        h4_impulse = round((float(curr_px) - closes[-3]) / float(atr_f), 4)

                reg_class = raw_bundle_data.get("regime_classification") or raw_bundle_data.get("market_regime")
                if isinstance(reg_class, dict):
                    reg_class = reg_class.get(symbol) or reg_class.get("regime")

                invariants_dict = compute_trade_invariants(
                    symbol=symbol,
                    current_price=float(curr_px),
                    atr=float(atr_f),
                    adr_5d=float(adr_f) if adr_f else float(atr_f) * 2.2,
                    smc_zones=smc_f,
                    sr_zones=sr_f,
                    min_rr=float(settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.5)),
                    regime_classification=str(reg_class) if reg_class else None,
                    h4_impulse_atr=float(h4_impulse) if h4_impulse is not None else None,
                )
                raw_bundle_data["precomputed_invariants"] = invariants_dict
                raw_bundle_data["bracket_options"] = invariants_dict.get("bracket_options")

                if session:
                    try:
                        from monika.application.analysis.calculators.intraday_level_optimizer import (
                            compute_optimal_levels,
                        )

                        opt_buy = await compute_optimal_levels(session, symbol, "buy", float(curr_px), settings)
                        opt_sell = await compute_optimal_levels(session, symbol, "sell", float(curr_px), settings)
                        if opt_buy and opt_buy.get("entry_allowed"):
                            invariants_dict["optimal_buy"] = opt_buy
                        if opt_sell and opt_sell.get("entry_allowed"):
                            invariants_dict["optimal_sell"] = opt_sell
                    except Exception as opt_err:
                        logger.debug(f"[{symbol}] Optimal levels precompute error: {opt_err}")

                inv_block = format_invariants_for_prompt(invariants_dict)
                initial_context_blocks.append(("PRE-COMPUTED TRADE INVARIANTS", inv_block))
    except Exception as inv_err:
        logger.debug(f"[{symbol}] Invariants computation non-fatal: {inv_err}")
    return curr_px, atr_f, adr_f


async def handle_billing_fallback(
    runner: Any,
    session: AsyncSession,
    symbol: str,
    result: dict,
    active_client: Any,
    system_prompt: Any,
    user_message: str,
    dynamic_tools: list,
) -> dict:
    """Handle LLM billing error with fallback model switch if approved."""
    if result.get("is_billing_error") and (
        runner.consent_callback is not None
        or (runner.is_fallback_always_approved is not None and runner.is_fallback_always_approved())
    ):
        role_fallbacks = runner.settings.get("llm", {}).get("task_roles", {}).get("stage2_per_asset_primary", {})
        fallback_model = (
            role_fallbacks.get("billing_fallback")
            or role_fallbacks.get("fallback")
            or role_fallbacks.get("fallback_2")
            or role_fallbacks.get("fallback_3")
            or role_fallbacks.get("primary")
        )
        approved = False
        if runner.is_fallback_always_approved is not None and runner.is_fallback_always_approved():
            approved = True
        elif runner.consent_callback is not None:
            logger.warning(f"[{symbol}] Billing error detected. Requesting fallback consent...")
            approved = await runner.consent_callback(
                f"Saldo LLM utama habis (Stage 2: {symbol}). Pindah ke model fallback ({fallback_model})?"
            )

        if approved:
            logger.info(f"[{symbol}] Fallback approved. Switching to fallback client ({fallback_model})...")
            fallback_client = _get_create_client()(fallback_model, runner.settings)

            messages = result.get("context_messages", [])
            instruction = (
                f"\n\nCRITICAL MANDATORY INSTRUCTION: You MUST call the `submit_asset_analysis` tool with "
                f"'symbol': '{symbol}' to record your final decision (buy/sell/wait/avoid) before finishing your turn. "
                f"Ensure 'invalidation' is a plain string, NOT an array or list. Do not respond with just text."
            )
            if not messages:
                messages = [{"role": "user", "content": user_message + instruction}]
            else:
                messages.append({"role": "user", "content": instruction})

            fallback_result = await fallback_client.run_agent_from_messages(
                session=session,
                system_prompt=_flatten_system_prompt(system_prompt),
                messages=messages,
                tools=dynamic_tools,
                max_tool_turns=active_client.max_tool_turns,
                stage_name=f"per_asset_{symbol}",
            )

            if fallback_result["success"]:
                return fallback_result
    return result


def extract_entry_price_from_analysis(analysis: Optional[Any]) -> Optional[float]:
    """Extract entry price float safely from entry_zone or fallbacks."""
    entry_price_val = None
    if analysis and getattr(analysis, "entry_zone", None):
        try:
            ez = json.loads(analysis.entry_zone) if isinstance(analysis.entry_zone, str) else analysis.entry_zone
            if isinstance(ez, dict) and "price" in ez:
                entry_price_val = float(ez["price"])
        except Exception:
            pass
    if entry_price_val is None and analysis:
        if getattr(analysis, "entry_price", None) is not None:
            try:
                entry_price_val = float(analysis.entry_price)
            except ValueError, TypeError:
                pass
        elif getattr(analysis, "price_at_analysis", None) is not None:
            try:
                entry_price_val = float(getattr(analysis, "price_at_analysis"))
            except ValueError, TypeError:
                pass
        elif getattr(analysis, "current_price", None) is not None:
            try:
                entry_price_val = float(getattr(analysis, "current_price"))
            except ValueError, TypeError:
                pass
    return entry_price_val


async def evaluate_debate_candidate_and_levels(
    analysis: Any,
    session: Optional[AsyncSession],
    symbol: str,
    entry_price_val: Optional[float],
    specialist_biases: Optional[dict[str, str]] = None,
    precomputed_brackets: Optional[dict[str, Any]] = None,
    result_dict: Optional[dict[str, Any]] = None,
) -> tuple[bool, Optional[float], Optional[float], Optional[int], Any, Optional[float]]:
    """Evaluate candidate_for_debate flag and auto-recover structural SL/TP if missing."""
    decision = getattr(analysis, "decision", "WAIT") if analysis else "WAIT"

    def _safe_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except ValueError, TypeError:
            return None

    def _safe_int(val: Any) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(val)
        except ValueError, TypeError:
            return None

    sl_val = _safe_float(getattr(analysis, "stop_loss", None)) if analysis else None
    tp_val = _safe_float(getattr(analysis, "take_profit", None)) if analysis else None
    cs_val = _safe_int(getattr(analysis, "confluence_score", None)) if analysis else None

    # Fetch latest price and ATR as fallback references if needed
    latest_atr: Optional[float] = None
    if session and (entry_price_val is None or sl_val is None or tp_val is None or not precomputed_brackets):
        try:
            now_dt = clock.now()
            if entry_price_val is None:
                p_row = (
                    await session.execute(
                        select(PriceOHLCV.close)
                        .where(PriceOHLCV.symbol == symbol)
                        .where(PriceOHLCV.timeframe == "M15")
                        .where(PriceOHLCV.timestamp <= now_dt)
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if p_row is not None:
                    entry_price_val = float(p_row)

            ti_row = (
                await session.execute(
                    select(TechnicalIndicator)
                    .where(
                        TechnicalIndicator.symbol == symbol,
                        TechnicalIndicator.timeframe.in_(["H4", "H1"]),
                        TechnicalIndicator.indicator_name == "ATR_14",
                    )
                    .where(TechnicalIndicator.timestamp <= now_dt)
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if ti_row and ti_row.value_json:
                raw_atr = json.loads(ti_row.value_json)
                latest_atr = float(raw_atr.get("atr", 0) if isinstance(raw_atr, dict) else raw_atr)
        except Exception:
            pass

    b_opts: Optional[dict[str, Any]] = (
        dict(precomputed_brackets)
        if isinstance(precomputed_brackets, dict)
        and "long_option_a" in precomputed_brackets
        and "short_option_b" in precomputed_brackets
        else None
    )
    res_d = result_dict if isinstance(result_dict, dict) else {}
    fallback_impulse = res_d.get("h4_impulse_atr")
    fallback_regime = res_d.get("regime_classification") or res_d.get("market_regime")
    if isinstance(fallback_regime, dict):
        fallback_regime = fallback_regime.get(symbol) or fallback_regime.get("regime")

    if b_opts is None and entry_price_val is not None and latest_atr is not None and latest_atr > 0:
        try:
            from monika.application.analysis.calculators.invariant_calculator import (
                generate_concrete_bracket_options,
            )

            b_opts = generate_concrete_bracket_options(
                symbol=symbol,
                current_price=entry_price_val,
                atr=latest_atr,
                adr_5d=latest_atr * 2.2,
                target_rr=1.60,
                regime_classification=str(fallback_regime) if fallback_regime else None,
                h4_impulse_atr=float(fallback_impulse) if fallback_impulse is not None else None,
            )
        except Exception:
            b_opts = None

    if b_opts is not None:
        if isinstance(result_dict, dict):
            result_dict["bracket_options"] = b_opts
        if analysis is not None:
            try:
                setattr(analysis, "bracket_options", b_opts)
            except Exception:
                pass

    is_candidate_for_debate = False
    if analysis:
        if str(decision).strip().lower() in ("buy", "sell"):
            is_candidate_for_debate = True
        elif str(decision).strip().lower() == "wait" and cs_val is not None and cs_val >= 6:
            p_in = _safe_float(getattr(analysis, "priced_in_score", None)) or 0.0
            exh = _safe_float(getattr(analysis, "exhaustion_risk", None)) or 0.0
            # Bug #64: Never promote WAIT to debate candidate if market is already priced in or exhausted
            if p_in >= 8.0 or exh >= 9.0:
                is_candidate_for_debate = False
            else:
                rat = str(getattr(analysis, "rationale", "") or "").lower()
                conflict_keywords = (
                    "conflict",
                    "diverg",
                    "macro",
                    "opposing",
                    "brief",
                    "ssvp",
                    "headwind",
                    "bias",
                    "discount",
                    "premium",
                    "order block",
                    "fvg",
                    "pullback",
                    "retest",
                )
                has_structural_setup = any(kw in rat for kw in conflict_keywords)

                # Auto-recover structural SL/TP if model omitted them on WAIT decision
                if (sl_val is None or tp_val is None) and has_structural_setup:
                    inval_price = _safe_float(getattr(analysis, "invalidation_price", None))
                    ref_px = entry_price_val
                    ref_atr = latest_atr

                    inval_valid = False
                    if inval_price is not None and ref_px is not None and ref_atr is not None and ref_atr > 0:
                        dist_to_inval = abs(ref_px - inval_price)
                        # Bug #68: Only use invalidation_price as SL if distance is between 1.0x and 2.5x ATR
                        if 1.0 * ref_atr <= dist_to_inval <= 2.5 * ref_atr:
                            inval_valid = True
                            inval_dir = str(getattr(analysis, "invalidation_direction", "") or "").lower()
                            if "below" in inval_dir or inval_price < ref_px:
                                if sl_val is None:
                                    sl_val = inval_price
                                if tp_val is None:
                                    risk_d = abs(ref_px - sl_val)
                                    tp_val = round(ref_px + (1.6 * risk_d), 5)
                            elif "above" in inval_dir or inval_price > ref_px:
                                if sl_val is None:
                                    sl_val = inval_price
                                if tp_val is None:
                                    risk_d = abs(sl_val - ref_px)
                                    tp_val = round(ref_px - (1.6 * risk_d), 5)

                    if not inval_valid and (
                        b_opts is not None or (ref_px is not None and ref_atr is not None and ref_atr > 0)
                    ):
                        if b_opts is None and ref_px is not None and ref_atr is not None:
                            from monika.application.analysis.calculators.invariant_calculator import (
                                generate_concrete_bracket_options,
                            )

                            b_opts = generate_concrete_bracket_options(
                                symbol=symbol,
                                current_price=ref_px,
                                atr=ref_atr,
                                adr_5d=ref_atr * 2.2,
                                target_rr=1.60,
                                regime_classification=str(fallback_regime) if fallback_regime else None,
                                h4_impulse_atr=float(fallback_impulse) if fallback_impulse is not None else None,
                            )
                            if isinstance(result_dict, dict):
                                result_dict["bracket_options"] = b_opts

                        if b_opts is not None:
                            is_bull = any(w in rat for w in ("bull", "long", "discount", "buy"))
                            is_bear = any(w in rat for w in ("bear", "short", "premium", "sell"))

                            spec_bull = 0
                            spec_bear = 0
                            if isinstance(specialist_biases, dict):
                                for role_k, bias_v in specialist_biases.items():
                                    b_str = str(bias_v or "").lower()
                                    weight = 2 if role_k in ("technical", "macro") else 1
                                    if "bull" in b_str or "buy" in b_str:
                                        spec_bull += weight
                                    elif "bear" in b_str or "sell" in b_str:
                                        spec_bear += weight

                            inval_dir = str(getattr(analysis, "invalidation_direction", "") or "").lower()
                            bull_kw_count = sum(rat.count(w) for w in ("bullish", "long", "discount", "buy"))
                            bear_kw_count = sum(rat.count(w) for w in ("bearish", "short", "premium", "sell"))

                            prefer_bear = (
                                (is_bear and not is_bull)
                                or (spec_bear > spec_bull)
                                or (spec_bear == spec_bull and "above" in inval_dir)
                                or (
                                    spec_bear == spec_bull
                                    and "below" not in inval_dir
                                    and bear_kw_count > bull_kw_count
                                )
                            )
                            chosen_opt = b_opts["short_option_b"] if prefer_bear else b_opts["long_option_a"]
                            if sl_val is None:
                                sl_val = float(chosen_opt["stop_loss"])
                            if tp_val is None:
                                tp_val = float(chosen_opt["take_profit"])

                if sl_val is not None and tp_val is not None and has_structural_setup:
                    is_candidate_for_debate = True
                    try:
                        if analysis.stop_loss is None:
                            analysis.stop_loss = sl_val
                        if analysis.take_profit is None:
                            analysis.take_profit = tp_val
                        if session:
                            await session.commit()
                    except Exception as sync_err:
                        logger.debug(f"[{symbol}] Non-fatal error syncing recovered debate levels: {sync_err}")

    return is_candidate_for_debate, sl_val, tp_val, cs_val, decision, entry_price_val


async def finalize_single_asset_result(
    session: AsyncSession,
    symbol: str,
    analysis: Any,
    analysis_id: Any,
    decision: str,
    confidence: float,
    elapsed: float,
    result: dict,
    active_client: Any,
    specialist_biases: dict,
    precomputed_bracket_options: Any,
) -> dict:
    try:
        from monika.infrastructure.database.event_store import TradingEventStore

        await TradingEventStore.emit(
            session=session,
            event_type="analysis.stage2.completed",
            payload={
                "symbol": symbol,
                "analysis_id": analysis_id,
                "decision": decision,
                "confidence": confidence,
                "elapsed_seconds": elapsed,
                "tool_calls_made": result.get("tool_calls_made", 0),
                "turns": result.get("turns", 0),
            },
            correlation_id=f"cycle_stage2_{symbol}_{analysis_id or clock.now().strftime('%Y%m%d%H%M%S')}",
            actor="per_asset_stage",
        )
    except Exception as es_err:
        logger.debug(f"Event store emit analysis.stage2.completed error: {es_err}")

    # Clean up temporary pending specialist biases
    try:
        from monika.infrastructure.database.models import SystemConfig

        _biases_key = f"pending_specialist_biases_{symbol}"
        _cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == _biases_key))).scalar_one_or_none()
        if _cfg:
            await session.delete(_cfg)
            await session.commit()
    except Exception:
        pass

    entry_price_val = extract_entry_price_from_analysis(analysis)

    (
        is_candidate_for_debate,
        sl_val,
        tp_val,
        cs_val,
        decision,
        entry_price_val,
    ) = await evaluate_debate_candidate_and_levels(
        analysis=analysis,
        session=session,
        symbol=symbol,
        entry_price_val=entry_price_val,
        specialist_biases=specialist_biases,
        precomputed_brackets=precomputed_bracket_options,
        result_dict=result,
    )
    if precomputed_bracket_options and "bracket_options" not in result:
        result["bracket_options"] = precomputed_bracket_options

    # Bug #72: Propagate verified lot_size into result for downstream RiskGate
    verified_lots = None
    if isinstance(result, dict) and result.get("lot_size"):
        verified_lots = result.get("lot_size")
    elif hasattr(active_client, "verification_ledger"):
        sz_record = active_client.verification_ledger.get_last_execution("calculate_position_size")
        if sz_record and sz_record.get("result", {}).get("recommended_lots"):
            verified_lots = sz_record["result"]["recommended_lots"]
    if verified_lots is not None:
        result["lot_size"] = float(verified_lots)

    result.update(
        {
            "symbol": symbol,
            "analysis_id": analysis_id,
            "decision": decision,
            "confidence": confidence,
            "entry_price": entry_price_val,
            "stop_loss": sl_val,
            "take_profit": tp_val,
            "confluence_score": cs_val,
            "elapsed_seconds": elapsed,
            "candidate_for_debate": is_candidate_for_debate,
        }
    )
    return result
