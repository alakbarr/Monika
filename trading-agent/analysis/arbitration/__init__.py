"""
Arbitration module for reconciling Quant Strategies and LLM Debate decisions.
"""
from .signal_arbitrator import SignalArbitrator, ArbitrationResult

__all__ = ["SignalArbitrator", "ArbitrationResult"]
