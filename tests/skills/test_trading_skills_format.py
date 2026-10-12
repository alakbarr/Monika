# ==============================================================================
# File: tests/skills/test_trading_skills_format.py
# ==============================================================================

"""
Unit tests validating that all skills in trading-agent/skills/trading/
follow the standardized SKILL.md format identical to trading-agent/skills/general/.
"""

import pytest
from pathlib import Path
import yaml

from skills.loader import load_skill, list_skills, parse_skill_frontmatter
from skills.skills_hub import SkillsHub
from skills.trading_skill_linter import TradingSkillLinter

EXPECTED_TRADING_SKILLS = [
    "adjudication-framework",
    "caveman-mode",
    "central-banks-framework",
    "commodity-analysis",
    "cross-asset-regime-model",
    "crypto-analysis",
    "event-probability-playbook",
    "fundamental-performance-notes",
    "lessons-learned",
    "liquidity-and-macro-edge",
    "macro-analysis-framework",
    "market-dynamics-framework",
    "orderbook-liquidity-microstructure",
    "performance-notes",
    "risk-management-principles",
    "session-timing-rules",
    "smc-ict-playbook",
    "telegram-persona",
]


def test_all_trading_skills_exist_in_directory_format():
    """Verify that every trading skill is housed in its own directory with SKILL.md."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "skills" / "trading"

    for skill_name in EXPECTED_TRADING_SKILLS:
        skill_dir = base_dir / skill_name
        skill_file = skill_dir / "SKILL.md"

        assert skill_dir.exists(), f"Skill directory missing: {skill_dir}"
        assert skill_dir.is_dir(), f"Expected directory but found file: {skill_dir}"
        assert skill_file.exists(), f"SKILL.md missing in {skill_dir}"
        assert skill_file.stat().st_size > 0, f"SKILL.md is empty: {skill_file}"


def test_all_trading_skills_have_standard_frontmatter():
    """Verify each trading SKILL.md contains standard YAML frontmatter matching skills/general."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "skills" / "trading"

    for skill_name in EXPECTED_TRADING_SKILLS:
        skill_file = base_dir / skill_name / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")

        meta, body = parse_skill_frontmatter(content)
        assert meta, f"No frontmatter found in {skill_file}"
        assert meta.get("name") == skill_name, f"Expected name '{skill_name}', got '{meta.get('name')}'"
        assert meta.get("category") == "TRADING", f"Expected category 'TRADING', got '{meta.get('category')}'"
        assert meta.get("version") == "1.0.0", f"Missing version in {skill_file}"

        desc = meta.get("description", "")
        assert desc, f"Missing description in {skill_file}"
        assert len(desc) <= 80, f"Description exceeds 80 chars in {skill_file}: ({len(desc)}) {desc}"

        platforms = meta.get("platforms", [])
        assert isinstance(platforms, list) and len(platforms) > 0, f"Missing platforms in {skill_file}"

        tags = meta.get("tags", [])
        assert isinstance(tags, list) and len(tags) > 0, f"Missing tags in {skill_file}"

        assert body.strip().startswith("#"), f"Skill body should start with H1 heading in {skill_file}"


def test_loader_resolves_both_kebab_and_snake_case():
    """Verify loader loads skills seamlessly using kebab-case or snake_case."""
    for skill_name in EXPECTED_TRADING_SKILLS:
        snake_name = skill_name.replace("-", "_")

        content_kebab = load_skill(skill_name)
        content_snake = load_skill(snake_name)

        assert content_kebab, f"Failed loading by kebab-case: {skill_name}"
        assert content_snake, f"Failed loading by snake_case: {snake_name}"
        assert content_kebab == content_snake, f"Mismatch between kebab and snake content for {skill_name}"


def test_list_skills_contains_both_cases():
    """Verify list_skills includes both kebab and snake case aliases."""
    available = list_skills()
    for skill_name in EXPECTED_TRADING_SKILLS:
        snake_name = skill_name.replace("-", "_")
        assert skill_name in available, f"Missing {skill_name} in list_skills()"
        assert snake_name in available, f"Missing {snake_name} in list_skills()"


def test_skills_hub_resolves_trading_skills():
    """Verify SkillsHub discovers and views all trading skills."""
    hub = SkillsHub()
    hub.discover_skills()

    for skill_name in EXPECTED_TRADING_SKILLS:
        snake_name = skill_name.replace("-", "_")

        meta = hub.get_skill(skill_name)
        assert meta is not None, f"SkillsHub could not find {skill_name}"
        assert meta.category == "TRADING"

        meta_snake = hub.get_skill(snake_name)
        assert meta_snake is not None, f"SkillsHub could not find snake_case alias {snake_name}"

        ok, view_content = hub.view_skill(skill_name)
        assert ok is True, f"Failed viewing skill {skill_name}"
        assert len(view_content) > 50


def test_trading_skill_linter_zero_errors():
    """Ensure TradingSkillLinter passes on trading-agent/skills/trading with 0 errors."""
    base_dir = Path(__file__).resolve().parent.parent.parent / "skills" / "trading"
    linter = TradingSkillLinter()
    issues_by_file = linter.lint_directory(base_dir)

    errors = []
    for file_name, issues in issues_by_file.items():
        for iss in issues:
            if iss.severity == "ERROR":
                errors.append(f"{file_name}: {iss}")

    assert len(errors) == 0, f"Linter found errors in skills/trading: {errors}"
