"""
Cross-Agent Synchronizer
Implements post-analysis pairwise CDS and selective suppression.

Per research: synchronization should be SELECTIVE — suppress the lower-confidence
contradicting agent, do NOT broadcast the "winner's" belief to all agents.
This prevents the contamination effect.
"""

import logging
from typing import Optional

logger = logging.getLogger('TradingAgent.CrossAgentSync')

# Correlation structure for trading pairs
# (sym1, sym2, expected_correlation_coefficient)
PAIR_CORRELATIONS = [
    ('EURUSD', 'GBPUSD', 0.85),
    ('EURUSD', 'AUDUSD', 0.70),
    ('EURUSD', 'USDJPY', -0.80),
    ('GBPUSD', 'AUDUSD', 0.65),
    ('GBPUSD', 'USDJPY', -0.75),
    ('AUDUSD', 'USDJPY', -0.65),
    ('XAUUSD', 'EURUSD', 0.65),
    ('XAUUSD', 'GBPUSD', 0.55),
    ('XAUUSD', 'USDJPY', -0.60),
    ('XAUUSD', 'AUDUSD', 0.60),
]

from utils.protocol.context_coherence import USD_DIRECTION_IMPLICATIONS as USD_IMPLICATIONS


class CrossAgentSynchronizer:
    """
    Implements cross-agent coherence checking and selective suppression.
    
    Key principle from research: when agents disagree on correlated tasks,
    suppress the lower-confidence agent rather than broadcasting any belief.
    """

    def __init__(self, contradiction_threshold: float = 0.65):
        self.contradiction_threshold = contradiction_threshold

    def detect_contradictions(self, pa_results: dict) -> list[dict]:
        """
        Detect pairs of agents with contradictory decisions on correlated assets.
        
        Returns list of contradiction info dicts.
        """
        contradictions = []

        for sym1, sym2, expected_corr in PAIR_CORRELATIONS:
            if sym1 not in pa_results or sym2 not in pa_results:
                continue

            result1 = pa_results[sym1]
            result2 = pa_results[sym2]

            decision1 = result1.get('decision', 'wait')
            decision2 = result2.get('decision', 'wait')

            # Only check tradeable decisions
            if decision1 not in ('buy', 'sell') or decision2 not in ('buy', 'sell'):
                continue

            # Get USD implications
            impl1 = USD_IMPLICATIONS.get(sym1, {}).get(decision1)
            impl2 = USD_IMPLICATIONS.get(sym2, {}).get(decision2)

            if not impl1 or not impl2:
                continue

            # Check for contradiction: ANY highly correlated pair (positive or negative)
            # must agree on the implied USD direction.
            is_contradictory = False
            if abs(expected_corr) > 0.5 and impl1 != impl2:
                is_contradictory = True

            if not is_contradictory:
                continue

            # Measure contradiction severity (use absolute correlation as severity)
            contradiction_cds = abs(expected_corr)

            if contradiction_cds < self.contradiction_threshold:
                continue  # Not strong enough to suppress

            # Identify suspect (lower confidence = more suspect)
            conf1 = result1.get('confidence', 0.5)
            conf2 = result2.get('confidence', 0.5)
            suspect = sym1 if conf1 < conf2 else sym2
            
            # Also consider confluence score — lower score = more suspect
            cs1 = result1.get('confluence_score') or 0
            cs2 = result2.get('confluence_score') or 0
            
            if cs1 != 0 and cs2 != 0:
                # If confluence score clearly differs, weight that more
                if cs1 < cs2 - 2:
                    suspect = sym1
                elif cs2 < cs1 - 2:
                    suspect = sym2

            contradictions.append({
                'sym1': sym1,
                'sym2': sym2,
                'dir1': decision1,
                'dir2': decision2,
                'impl1': impl1,
                'impl2': impl2,
                'expected_corr': expected_corr,
                'contradiction_cds': contradiction_cds,
                'suspect': suspect,
                'conf1': conf1,
                'conf2': conf2,
                'cs1': cs1,
                'cs2': cs2,
            })

        return contradictions

    def apply_selective_suppression(
        self,
        pa_results: dict,
        contradictions: list[dict]
    ) -> tuple[dict, list[str]]:
        """
        Apply selective suppression to resolve contradictions.
        
        IMPORTANT: Only suppress the SUSPECT agent. Do NOT broadcast the 
        "winner's" belief to other agents. This prevents contamination.
        
        Returns: (updated_results, suppressed_symbols)
        """
        suppressed = set()
        updated = dict(pa_results)

        for contradiction in contradictions:
            suspect = contradiction['suspect']
            
            if suspect in suppressed:
                continue  # Already suppressed by a previous contradiction

            sym1, sym2 = contradiction['sym1'], contradiction['sym2']
            trusted = sym2 if suspect == sym1 else sym1
            
            original_decision = updated[suspect].get('decision', 'unknown')
            updated[suspect] = dict(updated[suspect])
            updated[suspect]['_original_decision'] = original_decision
            updated[suspect]['decision'] = 'wait'
            updated[suspect]['confidence'] = 0.0
            updated[suspect]['rationale'] = (
                f"[SSVP Cross-Agent Suppression] "
                f"Decision '{original_decision}' suppressed due to contradiction with {trusted}. "
                f"Both {sym1} and {sym2} have correlated USD exposure (r={contradiction['expected_corr']:.2f}), "
                f"but their decisions imply opposite USD directions "
                f"({contradiction['impl1']} vs {contradiction['impl2']}). "
                f"Lower-confidence agent ({suspect}: conf={contradiction['conf1' if suspect == sym1 else 'conf2']:.2f}) "
                f"suppressed per SSVP selective synchronization protocol. "
                f"Re-analysis recommended with explicit cross-pair context."
            )
            suppressed.add(suspect)
            
            logger.warning(
                f"[SSVP] Suppressed {suspect} ({original_decision}) "
                f"due to contradiction with {trusted} "
                f"(corr={contradiction['expected_corr']:.2f})"
            )

        return updated, list(suppressed)
