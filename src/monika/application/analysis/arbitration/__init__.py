"""
Arbitration module for reconciling Quant Strategies and LLM Debate decisions.
"""

from .signal_arbitrator import ArbitrationResult, SignalArbitrator

__all__ = ["SignalArbitrator", "ArbitrationResult"]
