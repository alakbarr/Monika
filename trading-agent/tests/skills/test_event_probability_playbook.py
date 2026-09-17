# ==============================================================================
# File: tests/skills/test_event_probability_playbook.py
# ==============================================================================
"""Unit tests for the Event Probability Playbook skill."""

import unittest
from skills.loader import load_skill, list_skills, compose_system_prompt, invalidate_cache


class TestEventProbabilityPlaybook(unittest.TestCase):
    """Test suite verifying event_probability_playbook.md completeness and compatibility."""

    def setUp(self):
        invalidate_cache()

    def test_playbook_discovered_in_skills_list(self):
        """Skill must be automatically discovered by list_skills()."""
        skills = list_skills()
        self.assertIn(
            "event_probability_playbook",
            skills,
            "event_probability_playbook must be discoverable in list_skills()",
        )

    def test_playbook_loads_and_has_substantial_content(self):
        """Skill must load cleanly and contain substantial institutional content."""
        content = load_skill("event_probability_playbook")
        self.assertIsInstance(content, str)
        self.assertGreater(
            len(content),
            5000,
            "event_probability_playbook must be comprehensive and exceed 5,000 characters",
        )

    def test_playbook_contains_5_stage_thinking_flow(self):
        """Must contain all 5 sequential stages of thinking flow."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 1: PROTOKOL THINKING FLOW 5 TAHAP", content)
        self.assertIn("Tahap 1: Data Gathering & Multi-Source Grounding", content)
        self.assertIn("Tahap 2: Priced-In Testing", content)
        self.assertIn("Tahap 3: Historical Precedents Matching", content)
        self.assertIn("Tahap 4: Press Conference & SEP Forward Guidance Decoding", content)
        self.assertIn("Tahap 5: Multi-Scenario Trading Plan Formulation & LangGraph Handshake", content)

    def test_playbook_priced_in_methodologies_alignment(self):
        """Stage 2 must align mathematically with market_dynamics_framework.md."""
        content = load_skill("event_probability_playbook")
        self.assertIn("Method 1: FedWatch Dominant Probability", content)
        self.assertIn("Method 2: COT Extreme Positioning", content)
        self.assertIn("Method 3: Price Run-Up vs ATR", content)
        self.assertIn("run_up_vs_atr", content)
        self.assertIn("Method 4: News Narrative Saturation", content)
        self.assertIn("FULLY PRICED IN", content)
        self.assertIn("LARGELY PRICED IN", content)
        self.assertIn("PARTIALLY PRICED IN", content)
        self.assertIn("NOT PRICED IN", content)
        self.assertIn("Event Timing Playbook", content)

    def test_playbook_contains_5_canonical_historical_precedents(self):
        """Must detail the 5 canonical historical central bank surprises and multi-asset transmission."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 2: PUSTAKA PRESEDEN HISTORIS KEJUTAN BANK SENTRAL", content)
        self.assertIn("1994 Greenspan Preemptive Strike", content)
        self.assertIn("Sep 2013 Bernanke \"No-Taper\" Surprise", content)
        self.assertIn("Sep 2015 Yellen \"China Shock / Global Risk\" Hold", content)
        self.assertIn("Jul 2019 Powell \"Mid-Cycle Adjustment\" Hawkish Cut", content)
        self.assertIn("Jun 2022 Powell 75bp Acceleration", content)
        # Multi-asset metrics
        self.assertIn("Yields", content)
        self.assertIn("DXY", content)
        self.assertIn("Gold", content)
        self.assertIn("Saham", content)
        self.assertIn("Kripto", content)

    def test_playbook_contains_5_consensus_failure_mechanisms(self):
        """Must detail the 5 structural market consensus failure mechanisms."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 3: TAKSONOMI 5 MEKANISME KEGAGALAN KONSENSUS PASAR", content)
        self.assertIn("Endogenous Financial Conditions Feedback Loop", content)
        self.assertIn("Mandate Asymmetry & Risk Management Loss Function", content)
        self.assertIn("Institutional Credibility & Political Independence Signaling", content)
        self.assertIn("Information Asymmetry, Latent Data, & Global Spillover", content)
        self.assertIn("Forward Guidance Ambiguity & Noise-Trader Overinterpretation", content)

    def test_playbook_contains_analog_matching_engine(self):
        """Must include quantitative scoring rubric and decision tree for precedent matching."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 3.1: KRITERIA KUANTITATIF & KUALITATIF ANALOG MATCHING ENGINE", content)
        self.assertIn("Rubrik Skor Analogi Komposit", content)
        self.assertIn("Decision Tree Pemilihan Preseden Historis", content)

    def test_playbook_contains_4_quadrant_action_vs_guidance(self):
        """Must clearly separate rate decision (Action) from SEP/Presser (Guidance) into 4 quadrants."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 4: FRAMEWORK PEMISAHAN KEPUTUSAN BUNGA (ACTION) VS FORWARD GUIDANCE", content)
        self.assertIn("18:00 UTC", content)
        self.assertIn("18:30 UTC", content)
        self.assertIn("Hawkish Continuation", content)
        self.assertIn("Dovish Hike (Sell-the-News)", content)
        self.assertIn("Hawkish Cut (Bull Trap)", content)
        self.assertIn("Dovish Easing Explosion", content)

    def test_playbook_contains_institutional_output_template(self):
        """Must include 6-part institutional response template with 3-scenario trading plan."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 5: TEMPLATE OUTPUT INSTITUSIONAL 6 BAGIAN", content)
        self.assertIn("1. Snapshot Data Terkini & Trajektori Ekspektasi Pasar", content)
        self.assertIn("2. Uji Derajat Pemfaktoran Pasar (Priced-In Score) & Asimetri Risiko", content)
        self.assertIn("3. Analisis Preseden Historis Kejutan Bank Sentral", content)
        self.assertIn("4. Dekonstruksi Proyeksi SEP & Prediksi Nada Press Conference", content)
        self.assertIn("5. Trading Plan Multi-Skenario Terstruktur", content)
        self.assertIn("Skenario A: Base Case", content)
        self.assertIn("Skenario B: Hawkish Shock", content)
        self.assertIn("Skenario C: Dovish Reversal / Sell-The-News", content)
        self.assertIn("6. Handshake ke LangGraph Execution Engine", content)

    def test_playbook_contains_langgraph_integration(self):
        """Must detail LangGraph integration via save_market_intelligence and user_market_intel."""
        content = load_skill("event_probability_playbook")
        self.assertIn("BAGIAN 6: INTEGRASI LANGGRAPH & DATABASE ENGINE", content)
        self.assertIn("save_market_intelligence", content)
        self.assertIn("user_market_intel", content)
        self.assertIn("affected_symbols", content)
        self.assertIn("directive", content)
        self.assertIn("target_cycle", content)
        self.assertIn("data_node.py", content)
        self.assertIn("fundamental_node.py", content)
        self.assertIn("per_asset_node.py", content)
        self.assertIn("risk_gate_node.py", content)

    def test_compose_system_prompt_with_event_probability_playbook(self):
        """Must successfully compose into a combined system prompt with variable substitution."""
        composed = compose_system_prompt(
            "event_probability_playbook",
            "market_dynamics_framework",
        )
        self.assertIn("Event Probability Playbook", composed)
        self.assertIn("Market Dynamics Framework", composed)


if __name__ == "__main__":
    unittest.main()
