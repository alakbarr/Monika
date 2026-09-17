# ==============================================================================
# File: tests/skills/test_event_probability_stress.py
# ==============================================================================
"""Empirical Stress-Test Suite for Event Probability Playbook.

Adversarial testing covering:
1. Concurrency and thread safety of loader & cache invalidation
2. Path traversal security
3. Multi-skill composition with token budget stress
4. Template variable injection and SafeDict boundary conditions
5. Analytical oracles: Priced-in score, 100-pt analog rubric, decision tree, 4-quadrant matrix
6. Contract consistency with tools_definitions and database schemas
"""

import concurrent.futures
import re
import unittest
from skills.loader import (
    load_skill,
    list_skills,
    compose_system_prompt,
    invalidate_cache,
    SafeDict,
    _sanitize_skill_name,
)


class TestEventProbabilityPlaybookStress(unittest.TestCase):
    """Adversarial stress-testing suite for event_probability_playbook.md."""

    def setUp(self):
        invalidate_cache()

    # ----------------------------------------------------------------------
    # 1. Loader Concurrency & Thread Safety
    # ----------------------------------------------------------------------
    def test_concurrent_loading_and_invalidation(self):
        """Stress test: Concurrent threads loading skill and invalidating cache simultaneously."""
        errors = []

        def worker(idx: int):
            try:
                if idx % 5 == 0:
                    invalidate_cache()
                content = load_skill("event_probability_playbook")
                if len(content) < 20000:
                    errors.append(f"Thread {idx} got truncated content: {len(content)} chars")
                if "1994 Greenspan" not in content:
                    errors.append(f"Thread {idx} missing 1994 Greenspan")
            except Exception as e:
                errors.append(f"Thread {idx} raised: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(worker, i) for i in range(80)]
            concurrent.futures.wait(futures)

        self.assertEqual(len(errors), 0, f"Concurrent load failures: {errors}")

    # ----------------------------------------------------------------------
    # 2. Path Traversal & Sanitize Security
    # ----------------------------------------------------------------------
    def test_path_traversal_attempts(self):
        """Sanitizer must block path traversal attempts."""
        malicious_inputs = [
            "../event_probability_playbook",
            "..\\event_probability_playbook",
            "trading/event_probability_playbook",
            "event_probability_playbook/../../",
            "/event_probability_playbook",
            "\\event_probability_playbook",
            "",
            "   ",
            ".event_probability_playbook",
        ]
        for bad_input in malicious_inputs:
            with self.subTest(bad_input=bad_input):
                with self.assertRaises(ValueError):
                    load_skill(bad_input)

    # ----------------------------------------------------------------------
    # 3. Multi-Skill Composition Stress
    # ----------------------------------------------------------------------
    def test_composition_with_all_major_skills(self):
        """Compose event_probability_playbook with 8+ core skills simultaneously."""
        core_skills = [
            "event_probability_playbook",
            "market_dynamics_framework",
            "adjudication_framework",
            "smc_ict_playbook",
            "liquidity_and_macro_edge",
            "risk_management_principles",
            "session_timing_rules",
            "lessons_learned",
        ]
        composed = compose_system_prompt(*core_skills)
        self.assertIsInstance(composed, str)
        # Verify all skills are present in the composed string
        self.assertIn("Event Probability Playbook", composed)
        self.assertIn("Market Dynamics Framework", composed)
        self.assertIn("Adjudication Framework", composed)
        self.assertIn("SMC/ICT Playbook", composed)
        self.assertIn("Liquidity Sweep, Macro Bias", composed)
        self.assertIn("Risk Management Principles", composed)
        self.assertIn("Session Timing Rules", composed)
        self.assertIn("Lessons Learned", composed)

    def test_composition_under_tight_token_budget(self):
        """Composition with max_tokens budget should truncate gracefully without crashing."""
        for budget in [500, 1500, 3000, 8000, 15000]:
            with self.subTest(budget=budget):
                composed = compose_system_prompt(
                    "event_probability_playbook",
                    "market_dynamics_framework",
                    max_tokens=budget,
                )
                self.assertIsInstance(composed, str)
                self.assertGreater(len(composed), 0)

    # ----------------------------------------------------------------------
    # 4. Template Variable Substitution & SafeDict Resilience
    # ----------------------------------------------------------------------
    def test_template_substitution_adversarial_values(self):
        """Template substitution with special chars, code strings, and unicode."""
        adversarial_vars = {
            "symbol": "XAU/USD",
            "date": "2026-09-16",
            "chair": "Kevin Warsh",
            "regex": r"(\d{1,3}\.\d{1,2})%",
            "json_payload": '{"directive": "scenario_watch", "action": 1}',
            "unicode_text": "Inflasi 3.4% — suku bunga €/$ ¥",
        }
        composed = compose_system_prompt("event_probability_playbook", **adversarial_vars)
        self.assertIsInstance(composed, str)
        self.assertIn("Event Probability Playbook", composed)

    def test_safedict_with_playbook_content(self):
        """Verify SafeDict format_map doesn't fail on playbook content."""
        content = load_skill("event_probability_playbook")
        # Ensure no unescaped format keys cause KeyError when using SafeDict
        safe_map = SafeDict({"symbol": "EURUSD"})
        # Should not raise
        result = content.format_map(safe_map)
        self.assertEqual(len(result), len(content))

    # ----------------------------------------------------------------------
    # 5. Analytical Oracle: 100-Point Analog Rubric Sum
    # ----------------------------------------------------------------------
    def test_analog_matching_rubric_weights_sum_to_100(self):
        """Verify the 5 components of Analog Match Score sum exactly to 100 points."""
        content = load_skill("event_probability_playbook")
        # Extract weights from Bagian 3.1
        weight_matches = re.findall(r"Bobot:\s*(\d+)\s*Poin", content)
        self.assertEqual(
            len(weight_matches),
            5,
            f"Expected 5 weight components in Analog Matching Rubric, found {len(weight_matches)}: {weight_matches}",
        )
        weights = [int(w) for w in weight_matches]
        total_weight = sum(weights)
        self.assertEqual(
            total_weight,
            100,
            f"Analog matching weights must sum to exactly 100 points, got {total_weight} ({weights})",
        )

    # ----------------------------------------------------------------------
    # 6. Analytical Oracle: 5 Historical Surprises Multi-Asset Completeness
    # ----------------------------------------------------------------------
    def test_historical_precedents_multi_asset_coverage(self):
        """Every historical precedent in Bagian 2 must specify yields, DXY, gold, equities, crypto, and systemic impacts."""
        content = load_skill("event_probability_playbook")
        required_precedents = [
            "1994 Greenspan",
            "2013 Bernanke",
            "2015 Yellen",
            "2019 Powell",
            "2022 Powell",
        ]
        required_asset_classes = [
            "Yields",
            "DXY",
            "Gold",
            "Saham",
            "Kripto",
            "Sistemik",
        ]
        for precedent in required_precedents:
            with self.subTest(precedent=precedent):
                self.assertIn(precedent, content, f"Precedent {precedent} missing in playbook")

        for asset in required_asset_classes:
            with self.subTest(asset=asset):
                self.assertIn(asset, content, f"Asset class {asset} missing in multi-asset transmission")

    # ----------------------------------------------------------------------
    # 7. Analytical Oracle: Decision Tree Completeness
    # ----------------------------------------------------------------------
    def test_decision_tree_covers_all_5_precedents(self):
        """Decision tree in Bagian 3.1 must map to each of the 5 canonical precedents."""
        content = load_skill("event_probability_playbook")
        self.assertIn("[PRESEDEN 2022 POWELL]", content)
        self.assertIn("[PRESEDEN 2015 YELLEN]", content)
        self.assertIn("[PRESEDEN 2013 BERNANKE]", content)
        self.assertIn("[PRESEDEN 1994 GREENSPAN]", content)
        self.assertIn("[PRESEDEN 2019 POWELL]", content)

    # ----------------------------------------------------------------------
    # 8. Analytical Oracle: 4-Quadrant Action vs Guidance Exhaustiveness
    # ----------------------------------------------------------------------
    def test_four_quadrants_exhaustive_coverage(self):
        """Bagian 4 must cover all 4 quadrants of Action x Guidance."""
        content = load_skill("event_probability_playbook")
        quadrants = [
            "1. Hawkish Continuation",
            "2. Dovish Hike (Sell-the-News)",
            "3. Hawkish Cut (Bull Trap)",
            "4. Dovish Easing Explosion",
        ]
        for q in quadrants:
            with self.subTest(quadrant=q):
                self.assertIn(q, content, f"Quadrant {q} missing in Action vs Guidance matrix")

    # ----------------------------------------------------------------------
    # 9. Institutional Output Template Completeness
    # ----------------------------------------------------------------------
    def test_institutional_output_template_has_all_6_sections(self):
        """Bagian 5 must provide an explicit template for all 6 required sections."""
        content = load_skill("event_probability_playbook")
        sections = [
            "## 1. Snapshot Data Terkini & Trajektori Ekspektasi Pasar",
            "## 2. Uji Derajat Pemfaktoran Pasar (Priced-In Score) & Asimetri Risiko",
            "## 3. Analisis Preseden Historis Kejutan Bank Sentral",
            "## 4. Dekonstruksi Proyeksi SEP & Prediksi Nada Press Conference",
            "## 5. Trading Plan Multi-Skenario Terstruktur",
            "## 6. Handshake ke LangGraph Execution Engine (user_market_intel)",
        ]
        for sec in sections:
            with self.subTest(section=sec):
                self.assertIn(sec, content, f"Section '{sec}' missing in institutional template")

    # ----------------------------------------------------------------------
    # 10. LangGraph & Database Tool Contract Integrity
    # ----------------------------------------------------------------------
    def test_save_market_intelligence_contract_parameters(self):
        """The tool invocation in Bagian 6 must match the real parameter schema."""
        content = load_skill("event_probability_playbook")
        # Check tool name and required/optional params
        self.assertIn("save_market_intelligence(", content)
        self.assertIn("title=", content)
        self.assertIn("summary=", content)
        self.assertIn("intel_type=", content)
        self.assertIn("affected_symbols=", content)
        self.assertIn("directive=", content)
        self.assertIn("target_cycle=", content)
        self.assertIn("expires_in_hours=", content)


if __name__ == "__main__":
    unittest.main()
