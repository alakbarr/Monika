# ==============================================================================
# File: analysis/stages/per_asset/runner_mixins/single_asset_helpers.py
# Description: Helper routines for single-asset analysis execution
# ==============================================================================

import json
import logging
import sys
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.stages.per_asset.context_builder import _flatten_system_prompt
from monika.infrastructure.providers.llm_factory import create_client

logger = logging.getLogger("TradingAgent.PerAssetStage")


def _get_create_client():
    runner_mod = sys.modules.get("monika.application.analysis.stages.per_asset.runner")
    if runner_mod and hasattr(runner_mod, "create_client"):
        return runner_mod.create_client
    return create_client


def compute_prompt_invariants(
    settings: dict,
    symbol: str,
    raw_bundle_data: Any,
    initial_context_blocks: list,
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
            adr_raw = raw_bundle_data.get("get_daily_range_context")
            adr_f = adr_raw.get("adr_5d") if isinstance(adr_raw, dict) else None
            smc_raw = raw_bundle_data.get("get_smc_zones_H4") or raw_bundle_data.get("get_smc_zones")
            smc_f = (
                smc_raw if isinstance(smc_raw, list) else (smc_raw.get("zones") if isinstance(smc_raw, dict) else [])
            )
            sr_raw = (
                raw_bundle_data.get("get_fibonacci_levels_H4")
                or raw_bundle_data.get("get_fibonacci_levels")
                or raw_bundle_data.get("get_optimal_intraday_levels")
            )
            sr_f = sr_raw if isinstance(sr_raw, list) else []

            if curr_px and atr_f:
                invariants_dict = compute_trade_invariants(
                    symbol=symbol,
                    current_price=float(curr_px),
                    atr=float(atr_f),
                    adr_5d=float(adr_f) if adr_f else float(atr_f) * 2.5,
                    smc_zones=smc_f,
                    sr_zones=sr_f,
                    min_rr=float(settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)),
                )
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
