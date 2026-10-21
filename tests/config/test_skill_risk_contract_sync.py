"""The prompt-facing skill files must state the canonical risk contract.

The Stage 2 prompt injects markdown skill files (risk-management-principles,
lessons-learned, intent-resolution) straight into the model context. If those
files quote a different risk floor than the code enforces, the model reasons
against a contract the RiskGate will reject. This test keeps them in sync.
"""

from pathlib import Path

import pytest

from monika.core.config.risk_defaults import (
    DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT,
    DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT,
    DEFAULT_MIN_RR_RATIO,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"

PROMPT_FACING_SKILLS = (
    "trading/risk-management-principles/SKILL.md",
    "trading/lessons-learned/SKILL.md",
    "general/intent-resolution/SKILL.md",
    "operator/USER.md",
)


def _live_skill_files() -> list[Path]:
    return [path for path in SKILLS_DIR.rglob("*.md") if ".backups" not in path.parts and "archive" not in path.parts]


@pytest.mark.parametrize("relative_path", PROMPT_FACING_SKILLS)
def test_prompt_facing_skills_state_the_canonical_rr_floor(relative_path: str):
    text = (SKILLS_DIR / relative_path).read_text(encoding="utf-8")
    assert "1.30:1" not in text, f"{relative_path} still quotes the old 1.30 R:R floor"
    assert "R:R ≥ 1.3" not in text, f"{relative_path} still quotes the old 1.3 R:R floor"
    assert "minimum 1.3:1" not in text, f"{relative_path} still quotes the old 1.3 R:R floor"
    assert f"{DEFAULT_MIN_RR_RATIO:.2f}:1" in text or f"{DEFAULT_MIN_RR_RATIO}:1" in text


def test_no_live_skill_file_quotes_a_stale_daily_drawdown():
    stale = f"{3.0:.1f}%"
    for path in _live_skill_files():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            lowered = line.lower()
            if "drawdown" not in lowered:
                continue
            assert stale not in line or "Max Drawdown" in line, (
                f"{path.name} quotes a stale daily drawdown: {line.strip()}"
            )


def test_no_live_skill_file_quotes_a_stale_weekly_drawdown():
    stale = f"{6.0:.1f}%"
    for path in _live_skill_files():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            lowered = line.lower()
            if "weekly" not in lowered or "drawdown" not in lowered:
                continue
            assert stale not in line, f"{path.name} quotes a stale weekly drawdown: {line.strip()}"


def test_canonical_drawdown_numbers_are_documented():
    risk_doc = (SKILLS_DIR / "trading/risk-management-principles/SKILL.md").read_text(encoding="utf-8")
    assert f"{DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT:.1f}" in risk_doc
    assert f"{DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT:.1f}" in risk_doc
