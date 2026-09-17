import unittest
from skills.loader import load_skill, compose_system_prompt, list_skills

class TestCentralBanksFramework(unittest.TestCase):
    def test_central_banks_framework_exists(self):
        """Skill must be listed in available skills and loadable without error."""
        skills = list_skills()
        self.assertIn("central_banks_framework", skills)
        content = load_skill("central_banks_framework")
        self.assertTrue(len(content) > 1000)

    def test_mandates_of_all_five_central_banks(self):
        """Skill must document the mandates and indicators of all 5 major central banks."""
        content = load_skill("central_banks_framework")
        # 1. The Fed
        self.assertIn("The Fed", content)
        self.assertIn("Dual Mandate", content)
        self.assertIn("Core PCE", content)
        self.assertIn("Maximum Employment", content)
        # 2. ECB
        self.assertIn("ECB", content)
        self.assertIn("Single Mandate", content)
        self.assertIn("HICP", content)
        self.assertIn("Two-Pillar", content)
        self.assertIn("TPI", content)
        # 3. BoE
        self.assertIn("BoE", content)
        self.assertIn("Tiered Mandate", content)
        self.assertIn("CPI", content)
        self.assertIn("MPC", content)
        self.assertIn("twin deficits", content)
        # 4. BoJ
        self.assertIn("BoJ", content)
        self.assertIn("Shunto", content)
        self.assertIn("Core-core", content)
        self.assertIn("funding currency", content)
        # 5. RBA
        self.assertIn("RBA", content)
        self.assertIn("Triple Mandate", content)
        self.assertIn("Trimmed Mean", content)
        self.assertIn("terms of trade", content)
        self.assertIn("0.88", content)

    def test_seven_independent_non_rate_channels(self):
        """Skill must detail the 7 independent non-rate channels."""
        content = load_skill("central_banks_framework")
        self.assertIn("Safe-Haven vs Risk-On", content)
        self.assertIn("Reserve Currency Global", content)
        self.assertIn("Risiko Fiskal", content)
        self.assertIn("Terms of Trade", content)
        self.assertIn("Carry Trade Positioning", content)
        self.assertIn("Geopolitik", content)
        self.assertIn("Independensi Kelembagaan", content)

    def test_compose_system_prompt_includes_central_banks(self):
        """Composing Stage 1 skills must properly include central banks framework."""
        composed = compose_system_prompt("central_banks_framework", "macro_analysis_framework")
        self.assertIn("Dual Mandate", composed)
        self.assertIn("Data Priority Hierarchy", composed)
        self.assertIn("Relative Currency Attractiveness", composed)

if __name__ == '__main__':
    unittest.main()
