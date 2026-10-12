"""
Unit Test Suite for TradingSkillLinter.
Verifies description length, market regime validation, heading enforcement,
conversational bloat detection, and directory scanning.
"""

import pytest
from pathlib import Path
from skills.trading_skill_linter import TradingSkillLinter, LintIssue


def test_valid_skill_passes():
    linter = TradingSkillLinter()
    valid_content = """---
name: breakout_playbook
description: High-momentum breakout strategy outside Asian session ranges.
regimes: [breakout, trending]
---

# Breakout Playbook

## Rules
1. Identify high/low of Asian session.
2. Wait for H1 candle close beyond range with volume > 1.5x average.
3. Entry at retest of broken level with minimum 1.5 R:R.
"""
    is_valid, errors = linter.is_valid_skill(valid_content)
    assert is_valid is True
    assert len(errors) == 0


def test_description_too_long():
    linter = TradingSkillLinter()
    long_desc_content = """---
name: bad_skill
description: This is an extraordinarily verbose and rambling description of a trading playbook that exceeds eighty characters easily.
regimes: [trending]
---

# Title
Valid rules here with enough characters to pass min length easily.
"""
    is_valid, errors = linter.is_valid_skill(long_desc_content)
    assert is_valid is False
    assert any("DESCRIPTION_TOO_LONG" in e for e in errors)


def test_invalid_market_regime():
    linter = TradingSkillLinter()
    bad_regime_content = """---
name: bad_regime
description: Short desc.
regimes: [trending, moonshot_crypto_pump]
---

# Title
Valid rules here with enough characters to pass min length easily.
"""
    is_valid, errors = linter.is_valid_skill(bad_regime_content)
    assert is_valid is False
    assert any("INVALID_REGIME" in e for e in errors)


def test_conversational_bloat_detection():
    linter = TradingSkillLinter()
    bloat_content = """---
name: bloat_skill
description: Short desc.
---

# Title
Hello! As an AI assistant, let's dive in and explore how we trade EURUSD today.
Here are the rules to make sure we reach the minimum length limit safely.
"""
    is_valid, errors = linter.is_valid_skill(bloat_content)
    assert is_valid is False
    assert any("CONVERSATIONAL_BLOAT" in e for e in errors)


def test_missing_h1_heading_warning():
    linter = TradingSkillLinter()
    no_h1_content = """---
name: no_h1
description: Short desc.
---

## Subsection Only
Here are the rules to make sure we reach the minimum length limit safely without H1.
"""
    issues = linter.lint_skill(no_h1_content)
    warnings = [i for i in issues if i.severity == "WARNING"]
    assert any(i.rule == "MISSING_H1" for i in warnings)


def test_lint_directory(tmp_path):
    linter = TradingSkillLinter()
    valid_file = tmp_path / "valid.md"
    valid_file.write_text("""---
name: valid
description: Clean strategy.
regimes: [ranging]
---
# Clean Strategy
Rules for range bound trading with enough content to satisfy minimum length requirements.
""", encoding="utf-8")

    invalid_file = tmp_path / "invalid.md"
    invalid_file.write_text("""---
name: invalid
description: Short.
---
# Title
As an AI, I suggest trading carefully when market is choppy.
""", encoding="utf-8")

    results = linter.lint_directory(tmp_path)
    assert "invalid.md" in results
    assert any(i.rule == "CONVERSATIONAL_BLOAT" for i in results["invalid.md"])
