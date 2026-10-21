"""The risk-adjusted ratio must mean the same thing everywhere.

A t-statistic multiplied by sqrt(trade count) is not an annualised Sharpe
ratio. Reporting it as one produced playbooks claiming a Sharpe of 10 to 37,
which are impossible for a retail-sized strategy and were injected into the
LLM prompt as "verified" figures.
"""

from datetime import datetime, timedelta, timezone

import pytest

from monika.application.analysis.memory.playbook_linter import PlaybookLinter
from monika.application.backtest.performance_metrics import (
    compute_trade_statistics,
    window_days_from_trades,
)


def _returns(count: int = 100, mean: float = 0.003, std: float = 0.01) -> list[float]:
    values: list[float] = []
    for index in range(count):
        values.append(mean + (std if index % 2 == 0 else -std))
    return values


class TestCanonicalTradeStatistics:
    def test_t_statistic_and_annualized_sharpe_are_separate(self):
        stats = compute_trade_statistics(_returns(100), window_days=365.0)
        assert stats["trades"] == 100
        assert stats["per_trade_sharpe"] == pytest.approx(0.3, abs=0.02)
        # t-statistic = per-trade ratio * sqrt(n)
        assert stats["t_statistic"] == pytest.approx(stats["per_trade_sharpe"] * 10.0, abs=0.05)
        # annualised ratio uses the observed trade frequency, not the sample size
        assert stats["trades_per_year"] == pytest.approx(100.0, abs=0.1)
        assert stats["annualized_sharpe"] == pytest.approx(stats["per_trade_sharpe"] * 10.0, abs=0.05)

    def test_annualized_sharpe_needs_a_window(self):
        stats = compute_trade_statistics(_returns(100))
        assert stats["annualized_sharpe"] is None
        assert stats["trades_per_year"] is None
        assert stats["is_reliable"] is False

    def test_short_window_is_not_reliable(self):
        stats = compute_trade_statistics(_returns(100), window_days=20.0)
        assert stats["annualized_sharpe"] is not None
        assert stats["is_reliable"] is False

    def test_small_sample_is_not_reliable(self):
        stats = compute_trade_statistics(_returns(10), window_days=365.0)
        assert stats["is_reliable"] is False

    def test_large_sample_and_window_is_reliable(self):
        stats = compute_trade_statistics(_returns(120), window_days=365.0)
        assert stats["is_reliable"] is True

    def test_empty_input_is_safe(self):
        stats = compute_trade_statistics([])
        assert stats["trades"] == 0
        assert stats["annualized_sharpe"] is None
        assert stats["is_reliable"] is False

    def test_window_from_trades(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        trades = [
            type("T", (), {"entry_time": start, "exit_time": start + timedelta(hours=6)})(),
            type("T", (), {"entry_time": start + timedelta(days=30), "exit_time": start + timedelta(days=31)})(),
        ]
        assert window_days_from_trades(trades) == pytest.approx(31.0, abs=0.1)


class TestPlaybookLinterGuardsAgainstImplausibleSharpe:
    def _playbook(self, sharpe_line: str) -> str:
        return (
            "---\n"
            "name: probe_playbook\n"
            "symbol: EURUSD\n"
            "regime: ranging\n"
            "timeframe: H1\n"
            "min_rr: 2.0\n"
            f"{sharpe_line}\n"
            "---\n"
            "\n"
            "# Probe\n"
            "\n"
            "## Trigger Conditions\n"
            "- Buy when price sweeps support.\n"
            "\n"
            "## Invalidation\n"
            "- Invalidate below the swing low.\n"
            "\n"
            "## Entry Rules\n"
            "- Enter on the close above the zone.\n"
        )

    def test_implausible_sharpe_is_rejected(self):
        linter = PlaybookLinter()
        result = linter.lint(self._playbook("sharpe_ratio: 10.4"))
        assert result.is_valid is False
        assert any("Implausible Sharpe ratio" in error for error in result.errors)

    def test_plausible_sharpe_passes(self):
        linter = PlaybookLinter()
        result = linter.lint(self._playbook("sharpe_ratio: 1.4"))
        assert not any("Implausible Sharpe ratio" in error for error in result.errors)

    def test_missing_reliability_note_is_a_warning(self):
        linter = PlaybookLinter()
        result = linter.lint(self._playbook("sharpe_ratio: 1.4"))
        assert any("statistical reliability" in warning.lower() for warning in result.warnings)
