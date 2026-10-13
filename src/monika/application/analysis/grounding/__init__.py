"""
Token Provenance & Anti-Hallucination Grounding Gate.
"""

from .provenance_tagger import ObservedFact, ProvenanceLedger

__all__ = ["ProvenanceLedger", "ObservedFact"]
