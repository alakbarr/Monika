"""
Unified Risk Contract: Canonical single-source-of-truth for trade level boundaries.
Ensures 100% parity between Stage 2 LLM prompt generation and submission-time validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RiskContract:
    symbol: str
    min_rr_ratio: float = 1.3
    min_sl_atr_multiplier: float = 1.0
    max_sl_adr_pct: float = 0.35
    target_tp_min_adr_pct: float = 0.50
    target_tp_max_adr_pct: float = 0.80
    max_tp_entry_pct: float = 0.20
    band_tolerance_pct: float = 0.10

    def render_prompt_contract(self) -> str:
        """Render canonical risk contract section for injection into Stage 2 prompt."""
        return (
            f"=== CANONICAL RISK CONTRACT ({self.symbol}) ===\n"
            f"The following mathematical boundaries are ENFORCED by the deterministic backend risk gate:\n"
            f"1. Minimum Reward-to-Risk (R:R) Ratio: >= {self.min_rr_ratio:.2f}\n"
            f"   (Formula: |TP - Entry| >= {self.min_rr_ratio:.2f} * |Entry - SL|)\n"
            f"2. Stop Loss (SL) Minimum Distance: >= {self.min_sl_atr_multiplier:.2f}x H4 ATR\n"
            f"3. Stop Loss (SL) Maximum Distance: <= {self.max_sl_adr_pct:.0%} of Daily ADR (intraday ceiling)\n"
            f"4. Take Profit (TP) Intraday Band: [{self.target_tp_min_adr_pct:.0%}, {self.target_tp_max_adr_pct:.0%}] of Daily ADR\n"
            f"5. Maximum TP Distance: <= {self.max_tp_entry_pct:.0%} of entry price\n"
            f"Any trade proposal violating these mathematical limits will be rejected at submission time.\n"
            f"=== END CANONICAL RISK CONTRACT ===\n"
        )


def build_risk_contract(
    symbol: str,
    settings: Optional[Dict[str, Any]] = None,
    system_config_multipliers: Optional[Dict[str, float]] = None,
) -> RiskContract:
    """Build unified RiskContract respecting symbol-specific settings and DB SystemConfig."""
    cfg = settings or {}
    trading_risk = cfg.get("trading", {}).get("risk", {})

    # 1. Min R:R Ratio
    min_rr = float(trading_risk.get("min_rr_ratio", 1.3) or 1.3)

    # 2. Min SL ATR multiplier (symbol-specific override > config > default 1.0)
    sym_multipliers = system_config_multipliers or trading_risk.get("min_sl_atr_multiplier_by_symbol", {})
    if isinstance(sym_multipliers, dict):
        base_mult = float(sym_multipliers.get(symbol, sym_multipliers.get("default", 1.0)) or 1.0)
    else:
        base_mult = 1.0

    return RiskContract(
        symbol=symbol,
        min_rr_ratio=min_rr,
        min_sl_atr_multiplier=base_mult,
        max_sl_adr_pct=float(trading_risk.get("max_sl_adr_pct", 0.35) or 0.35),
        target_tp_min_adr_pct=float(trading_risk.get("target_tp_min_adr_pct", 0.50) or 0.50),
        target_tp_max_adr_pct=float(trading_risk.get("target_tp_max_adr_pct", 0.80) or 0.80),
        max_tp_entry_pct=float(trading_risk.get("max_tp_entry_pct", 0.20) or 0.20),
        band_tolerance_pct=float(trading_risk.get("band_tolerance_pct", 0.10) or 0.10),
    )
