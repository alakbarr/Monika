# ==============================================================================
# File: tests/skills/test_loader.py
# ==============================================================================
"""Unit tests for the skills loader module (Phase 5)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestSkillLoader(unittest.TestCase):

    def setUp(self):
        """Set up a temporary skills directory for tests."""
        self.tmpdir = tempfile.mkdtemp()
        self.trading_dir = Path(self.tmpdir) / "trading"
        self.trading_dir.mkdir()

    def _write_skill(self, name: str, content: str) -> None:
        (self.trading_dir / f"{name}.md").write_text(content, encoding="utf-8")

    def _make_loader(self):
        """Import loader with patched _SKILLS_DIR pointing to temp dir."""
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()  # clear LRU cache
        original = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        return loader_mod, original

    def _restore_loader(self, loader_mod, original):
        loader_mod._SKILLS_DIR = original
        loader_mod.load_skill.cache_clear()

    def test_load_skill_basic(self):
        self._write_skill("test_skill", "Hello World")
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            content = loader_mod.load_skill("test_skill")
            self.assertEqual(content, "Hello World")
        finally:
            loader_mod._SKILLS_DIR = original_dir
            loader_mod.load_skill.cache_clear()

    def test_load_skill_not_found_raises(self):
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            with self.assertRaises(FileNotFoundError):
                loader_mod.load_skill("nonexistent_skill")
        finally:
            loader_mod._SKILLS_DIR = original_dir
            loader_mod.load_skill.cache_clear()

    def test_compose_system_prompt_single(self):
        self._write_skill("alpha", "Alpha content")
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            result = loader_mod.compose_system_prompt("alpha")
            self.assertIn("Alpha content", result)
        finally:
            loader_mod._SKILLS_DIR = original_dir
            loader_mod.load_skill.cache_clear()

    def test_compose_system_prompt_multi(self):
        self._write_skill("part1", "Part One")
        self._write_skill("part2", "Part Two")
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            result = loader_mod.compose_system_prompt("part1", "part2")
            self.assertIn("Part One", result)
            self.assertIn("Part Two", result)
        finally:
            loader_mod._SKILLS_DIR = original_dir
            loader_mod.load_skill.cache_clear()

    def test_compose_template_substitution(self):
        self._write_skill("tmpl", "Analyze {{symbol}} with COT {{cot_code}}")
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            result = loader_mod.compose_system_prompt("tmpl", symbol="XAUUSD", cot_code="088691")
            self.assertIn("XAUUSD", result)
            self.assertIn("088691", result)
        finally:
            loader_mod._SKILLS_DIR = original_dir
            loader_mod.load_skill.cache_clear()

    def test_compose_missing_skill_is_skipped_gracefully(self):
        """Missing skill in compose should be skipped, not crash."""
        self._write_skill("present", "Present content")
        import skills.loader as loader_mod
        loader_mod.load_skill.cache_clear()
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            # "missing_skill" doesn't exist — should be skipped
            result = loader_mod.compose_system_prompt("present", "missing_skill")
            self.assertIn("Present content", result)
        finally:
            loader_mod._SKILLS_DIR = original_dir
            loader_mod.load_skill.cache_clear()

    def test_list_skills(self):
        self._write_skill("skill_a", "A")
        self._write_skill("skill_b", "B")
        import skills.loader as loader_mod
        original_dir = loader_mod._SKILLS_DIR
        loader_mod._SKILLS_DIR = self.trading_dir
        try:
            skills = loader_mod.list_skills()
            self.assertIn("skill_a", skills)
            self.assertIn("skill_b", skills)
        finally:
            loader_mod._SKILLS_DIR = original_dir

    def test_safe_dict_leaves_unknown_placeholder(self):
        """_SafeDict should leave unknown {keys} in place instead of raising KeyError."""
        from skills.loader import _SafeDict
        template = "Hello {name}, your code is {code}"
        result = template.format_map(_SafeDict({"name": "Alice"}))
        self.assertEqual(result, "Hello Alice, your code is {code}")

    def test_load_real_lessons_learned(self):
        """Verify that lessons_learned exists in the actual trading skills directory."""
        from skills.loader import load_skill, list_skills
        skills = list_skills()
        self.assertIn("lessons_learned", skills)
        content = load_skill("lessons_learned")
        self.assertIn("Lessons Learned", content)


if __name__ == "__main__":
    unittest.main()
