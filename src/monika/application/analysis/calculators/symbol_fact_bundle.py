"""
Symbol Fact Bundle — Pre-computed, immutable-friendly market fact snapshot.

Caches grounding tables, trade invariants, and canonical prompt prefixes for
downstream debate and risk stages, eliminating redundant queries and token churn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from monika.application.analysis.calculators.invariant_calculator import compute_trade_invariants
from monika.application.analysis.grounding.market_grounding import MarketGroundingEngine
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

logger = logging.getLogger("TradingAgent.Analysis.SymbolFactBundle")


@dataclass(frozen=True)
class SymbolFactBundle:
    """Immutable pre-computed snapshot of symbol facts and cached prompt prefixes."""

    symbol: str
    fact_sheet: Any
    grounding_table: str
    trade_invariants: Optional[Dict[str, Any]] = None
    canonical_prefix: str = ""
    as_of: Optional[datetime] = None
    original_context: Optional[Dict[str, Any]] = None


async def build_symbol_fact_bundle(
    session: Any = None,
    symbol: str = "",
    fact_sheet: Any = None,
    original_context: Optional[Dict[str, Any]] = None,
    as_of: Optional[datetime] = None,
    repository: Any = None,
) -> SymbolFactBundle:
    """
    Builds and caches a SymbolFactBundle for a given symbol.
    Fetches market grounding, computes deterministic invariants when price/ATR are available,
    and formats the canonical Tier-2 prefix.
    """
    # Support both (session, symbol) and (symbol, session)
    if isinstance(session, str) and not symbol:
        sym_raw = session
        sess = None
    else:
        sym_raw = symbol
        sess = session

    clean_sym = sym_raw.upper().strip().replace("/", "")
    fs = fact_sheet if fact_sheet is not None else {}
    orig_ctx = original_context or {}

    grounding_tbl = ""
    if isinstance(fs, dict) and fs.get("empirical_market_grounding"):
        grounding_tbl = str(fs["empirical_market_grounding"])
    elif sess is not None or repository is not None:
        try:
            grounding_tbl = await MarketGroundingEngine.build_grounding_table(
                symbol=clean_sym,
                session=sess,
                days_back=10,
                repository=repository,
                as_of=as_of,
            )
        except Exception as e:
            logger.debug(f"[SymbolFactBundle] Failed building grounding table for {clean_sym}: {e}")

    # Compute trade invariants if current price and ATR are available
    invariants = None
    try:
        curr_price = None
        atr_val = None
        adr_val = None

        if isinstance(fs, dict):
            curr_price = fs.get("current_price") or fs.get("price") or fs.get("close")
            atr_val = fs.get("atr_14") or fs.get("atr") or fs.get("atr_h4")
            adr_val = fs.get("adr_5d") or fs.get("adr")

        if curr_price is None and orig_ctx:
            curr_price = orig_ctx.get("entry_price") or orig_ctx.get("price") or orig_ctx.get("entry")
        if atr_val is None and orig_ctx:
            atr_val = orig_ctx.get("atr") or orig_ctx.get("atr_14")

        if curr_price is not None and atr_val is not None:
            c_p = float(curr_price)
            a_v = float(atr_val)
            ad_v = float(adr_val) if adr_val is not None else a_v * 2.0
            if c_p > 0 and a_v > 0 and ad_v > 0:
                invariants = compute_trade_invariants(
                    symbol=clean_sym,
                    current_price=c_p,
                    atr=a_v,
                    adr_5d=ad_v,
                )
    except Exception as inv_err:
        logger.debug(f"[SymbolFactBundle] Could not compute trade invariants for {clean_sym}: {inv_err}")

    # Build canonical prefix (Segment A)
    canonical_prefix = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fs,
        original_context=orig_ctx,
        append_ledger=None,
        task_directive="",
    )

    return SymbolFactBundle(
        symbol=clean_sym,
        fact_sheet=fs,
        grounding_table=grounding_tbl,
        trade_invariants=invariants,
        canonical_prefix=canonical_prefix,
        as_of=as_of,
        original_context=orig_ctx,
    )
