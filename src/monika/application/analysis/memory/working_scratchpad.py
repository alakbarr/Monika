"""
Provides an isolated working memory canvas where the LLM can record, verify, and update
intermediate trading calculations across multi-turn agent execution without bloating
or degrading the primary conversation context window.

Key Features:
- Anchors key numbers (H4 ATR, 5-Day ADR, Entry, SL, TP, R:R, SMC Zones).
- Protects working state against context compaction / observation masking.
- Provides cross-verification ground truth for InHarnessGroundingValidator and PreCommitGate.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger("TradingAgent.WorkingScratchpad")


class WorkingScratchpad:
    """
    Manages active task-scoped scratchpad entries for trading analysis sessions.
    """

    _global_store: Dict[str, Dict[str, Any]] = {}

    def __init__(self, symbol: Optional[str] = None):
        self.symbol = (symbol or "").strip().upper().replace("/", "") if symbol else None

    @classmethod
    def get_or_create(cls, symbol: str) -> Dict[str, Any]:
        """Retrieves or initializes scratchpad state for a given symbol."""
        sym_clean = (symbol or "").strip().upper().replace("/", "")
        if sym_clean not in cls._global_store:
            cls._global_store[sym_clean] = {
                "symbol": sym_clean,
                "bias": "NEUTRAL",
                "h4_atr": None,
                "daily_adr": None,
                "entry_zone": {},
                "structural_sl": {},
                "target_tp": {},
                "rr_ratio": None,
                "confluence_score": None,
                "verified_confluences": [],
                "invalidation_price": None,
                "notes": [],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return cls._global_store[sym_clean]

    @classmethod
    def update_scratchpad(cls, symbol: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates the scratchpad for a symbol with validated data points.
        """
        state = cls.get_or_create(symbol)
        if not isinstance(updates, dict):
            return state

        # Numerical fields with validation
        for num_field in ("h4_atr", "daily_adr", "rr_ratio", "confluence_score", "invalidation_price"):
            if num_field in updates and updates[num_field] is not None:
                try:
                    state[num_field] = float(updates[num_field])
                except (ValueError, TypeError):
                    pass

        # Textual & structured fields
        if "bias" in updates and updates["bias"]:
            state["bias"] = str(updates["bias"]).strip().upper()

        if "entry_zone" in updates and isinstance(updates["entry_zone"], dict):
            state["entry_zone"].update(updates["entry_zone"])

        if "structural_sl" in updates and isinstance(updates["structural_sl"], dict):
            state["structural_sl"].update(updates["structural_sl"])

        if "target_tp" in updates and isinstance(updates["target_tp"], dict):
            state["target_tp"].update(updates["target_tp"])

        if "verified_confluences" in updates and isinstance(updates["verified_confluences"], list):
            existing = set(state["verified_confluences"])
            for c in updates["verified_confluences"]:
                if c and str(c) not in existing:
                    state["verified_confluences"].append(str(c))
                    existing.add(str(c))

        if "notes" in updates:
            raw_notes = updates["notes"]
            if isinstance(raw_notes, list):
                state["notes"] = [str(n)[:250] for n in raw_notes if n][-10:]
            elif isinstance(raw_notes, str) and raw_notes.strip():
                state["notes"].append(raw_notes.strip()[:250])
                state["notes"] = state["notes"][-10:]

        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.debug(f"[WorkingScratchpad] Updated {symbol}: bias={state['bias']}, confluences={len(state['verified_confluences'])}")
        return state

    @classmethod
    def read_scratchpad(cls, symbol: str) -> Dict[str, Any]:
        """Returns the current scratchpad contents for a symbol."""
        return cls.get_or_create(symbol)

    @classmethod
    def clear(cls, symbol: Optional[str] = None) -> None:
        """Clears scratchpad for a symbol or all symbols."""
        if symbol:
            sym_clean = symbol.strip().upper().replace("/", "")
            cls._global_store.pop(sym_clean, None)
        else:
            cls._global_store.clear()

    @classmethod
    def get_summary_text(cls, symbol: str) -> str:
        """Returns a dense, telegraphic textual summary of active scratchpad."""
        state = cls.get_or_create(symbol)
        parts = [f"SCRATCHPAD[{state['symbol']}]: bias={state['bias']}"]
        if state["h4_atr"]:
            parts.append(f"ATR14={state['h4_atr']:.4f}")
        if state["daily_adr"]:
            parts.append(f"ADR5={state['daily_adr']:.4f}")
        if state["invalidation_price"]:
            parts.append(f"Invalidation={state['invalidation_price']:.4f}")
        if state["rr_ratio"]:
            parts.append(f"RR={state['rr_ratio']:.2f}")
        if state["confluence_score"] is not None:
            parts.append(f"Score={state['confluence_score']:.1f}")
        if state["verified_confluences"]:
            parts.append(f"Confluences=[{', '.join(state['verified_confluences'])}]")
        if state["notes"]:
            parts.append(f"Notes=[{'; '.join(state['notes'][-3:])}]")
        return " | ".join(parts)
