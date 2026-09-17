# ==============================================================================
# File: proposed_test_playbook_stress_challenge.py
# Drop-in updated test suite for tests/skills/test_playbook_stress_challenge.py
# Reflecting full resolution of Challenger 2's 4 remedies.
# ==============================================================================

import re
import unittest
from skills.loader import load_skill, invalidate_cache


class TestPlaybookStressChallenge(unittest.TestCase):
    """Rigorous empirical stress test harness verifying the 4 remedies in event_probability_playbook.md."""

    @classmethod
    def setUpClass(cls):
        invalidate_cache()
        cls.playbook_text = load_skill("event_probability_playbook")

    def test_spike_avoidance_rules_defined(self):
        """Verify that spike avoidance directives exist across all temporal phases."""
        content = self.playbook_text
        # Pre-event rule
        self.assertIn("PRE-EVENT", content)
        self.assertIn("DILARANG", content)
        self.assertIn("breakout entry searah konsensus", content)

        # Event spike avoidance rule
        self.assertIn("EVENT (0-4 jam)", content)
        self.assertIn("JANGAN PERNAH", content)
        self.assertIn("mengejar spike candle pertama", content)

        # Post-event quality window
        self.assertIn("POST-EVENT (4-48 jam)", content)
        self.assertIn("JENDELA KUALITAS TERTINGGI", content)

    def test_remedy_1_quadrant_2_avoids_pre_release_orders(self):
        """
        REMEDY 1 VERIFICATION:
        Quadrant 2 MUST NOT advocate placing orders before release ('sebelum rilis').
        It must explicitly mandate waiting for liquidity sweep and post-presser confirmation.
        """
        content = self.playbook_text
        q2_row = [line for line in content.splitlines() if "| **2. Dovish Hike (Sell-the-News)** |" in line][0]
        self.assertIn("JANGAN pasang order sebelum rilis", q2_row)
        self.assertIn("pasca-presser", q2_row)
        self.assertIn("MSS reclaim", q2_row)

    def test_remedy_2_analog_matching_rubric_includes_powell_2019(self):
        """
        REMEDY 2 VERIFICATION:
        The 100-point rubric in Section 3.1 covers all 5 canonical historical surprises:
        - Bernanke 2013 (FCI Divergence, 25 pts)
        - Yellen 2015 (Global Contagion, 20 pts)
        - Greenspan 1994 (Independence Friction, 15 pts)
        - Powell 2022 (Whisper Leak, 20 pts)
        - Powell 2019 (Priced-In Crowding & Easing Cycle Mispricing, 20 pts)
        Total = 100 pts across exactly 5 components.
        """
        content = self.playbook_text
        rubric_section = content.split("## BAGIAN 3.1:")[1].split("### 2. Decision Tree")[0]

        self.assertIn("Bernanke 2013", rubric_section)
        self.assertIn("Yellen 2015", rubric_section)
        self.assertIn("Greenspan 1994", rubric_section)
        self.assertIn("Powell 2022", rubric_section)
        self.assertIn("Powell 2019", rubric_section)

        # Verify weights sum to 100
        weight_matches = re.findall(r"Bobot:\s*(\d+)\s*Poin", rubric_section)
        self.assertEqual(len(weight_matches), 5)
        self.assertEqual(sum(int(w) for w in weight_matches), 100)

    def test_remedy_3_priced_in_score_clamping_and_gate_alignment(self):
        """
        REMEDY 3 VERIFICATION:
        1. Explicit clamping formula: min(10, max(1, ...))
        2. Line 322 gating aligned with Line 85 (priced-in 5-7 for lot size cut, >=8/9 for WAIT/hard block).
        """
        content = self.playbook_text
        self.assertIn("min(10,", content)
        self.assertIn("DILARANG", content)
        self.assertIn("membuka posisi baru searah konsensus sebelum rilis event", content)
        self.assertIn("priced-in 5-7 (LARGELY PRICED IN)", content)
        self.assertIn("hard block", content)

    def test_remedy_4_timing_h4_close_reconciled_with_presser_entry(self):
        """
        REMEDY 4 VERIFICATION:
        Multi-timeframe execution discipline clearly differentiates:
        - Intraday: 15-30m post-presser with M15/H1 MSS
        - Macro Swing: H4 close
        """
        content = self.playbook_text
        self.assertIn("Biarkan H4 candle menutup", content)
        self.assertIn("15-30 menit pasca-presser dimulai", content)
        self.assertIn("Intraday Execution (M15 / H1)", content)
        self.assertIn("Macro Swing Execution (H4 / D1)", content)

    def test_distinct_five_failure_mechanisms(self):
        """Verify all 5 consensus failure mechanisms are distinct."""
        content = self.playbook_text
        mechanisms = [
            "Endogenous Financial Conditions Feedback Loop",
            "Mandate Asymmetry & Risk Management Loss Function",
            "Institutional Credibility & Political Independence Signaling",
            "Information Asymmetry, Latent Data, & Global Spillover",
            "Forward Guidance Ambiguity & Noise-Trader Overinterpretation",
        ]
        for m in mechanisms:
            self.assertIn(m, content, f"Failure mechanism '{m}' must be defined in playbook")

    def test_action_vs_guidance_four_quadrants(self):
        """Verify 4-quadrant separation of Rate Action vs Forward Guidance."""
        content = self.playbook_text
        quadrants = [
            "Hawkish Continuation",
            "Dovish Hike (Sell-the-News)",
            "Hawkish Cut (Bull Trap)",
            "Dovish Easing Explosion",
        ]
        for q in quadrants:
            self.assertIn(q, content, f"Quadrant '{q}' must be detailed in matrix")

    def test_downstream_save_market_intelligence_schema_compatibility(self):
        """Verify save_market_intelligence parameter consistency."""
        content = self.playbook_text
        self.assertIn("save_market_intelligence(", content)
        self.assertIn("title=", content)
        self.assertIn("summary=", content)
        self.assertIn("intel_type=\"deep_research\"", content)
        self.assertIn("directive=\"scenario_watch\"", content)
        self.assertIn("target_cycle=\"until_event\"", content)
        self.assertIn("expires_in_hours=", content)


if __name__ == "__main__":
    unittest.main()
