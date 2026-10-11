# ==============================================================================
# File: graph/nodes/risk/__init__.py
# Monika Modular Risk Gate Node Package
# ==============================================================================

"""
Decomposed sub-modules of the RiskGate node architecture:
- level_synthesizer: Order entry/SL/TP single-pass derivation & repair
- quant_arbitration: Quant alpha evaluation & SignalArbitrator defense
- portfolio_synthesis: AI portfolio synthesis & correlation heat reduction
- rejection_auditor: Unified paper what-if & benchmark trajectory auditing
- proposal_notifier: Operator notification dispatch
"""

from graph.nodes.risk.level_synthesizer import _safe_num, resolve_and_repair_levels
from graph.nodes.risk.portfolio_synthesis import ai_portfolio_synthesis, apply_portfolio_synthesis_reduction
from graph.nodes.risk.proposal_notifier import send_proposal_notifications
from graph.nodes.risk.quant_arbitration import run_quant_arbitration
from graph.nodes.risk.rejection_auditor import audit_trade_rejection

__all__ = [
    "_safe_num",
    "resolve_and_repair_levels",
    "ai_portfolio_synthesis",
    "apply_portfolio_synthesis_reduction",
    "send_proposal_notifications",
    "run_quant_arbitration",
    "audit_trade_rejection",
]
