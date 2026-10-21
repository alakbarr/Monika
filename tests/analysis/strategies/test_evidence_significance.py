"""Promotion evidence must be statistically significant, not merely positive.

A positive profit factor on a small sample is not separable from luck. The
evidence store is the only promotion source since Phase 1, so the admission
rule has to test the significance of the mean trade, not just its sign, and it
has to record that significance next to the evidence.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from monika.application.analysis.strategies.evidence_store import (
    StrategyEvidenceStore,
    compute_sizing_corrected_breakeven_bps,
)
from monika.application.backtest.performance_metrics import (
    MIN_T_STATISTIC_FOR_EVIDENCE,
    compute_trade_statistics,
)


def _returns(count: int, mean: float, std: float) -> list[float]:
    values = []
    for index in range(count):
        values.append(mean + (std if index % 2 == 0 else -std))
    return values


class TestEvidenceSignificanceConstant:
    def test_evidence_bar_is_two_sided_five_percent(self):
        assert MIN_T_STATISTIC_FOR_EVIDENCE == 2.0

    def test_lucky_small_sample_is_below_the_bar(self):
        lucky = compute_trade_statistics(_returns(12, 0.001, 0.012))
        assert lucky["t_statistic"] < MIN_T_STATISTIC_FOR_EVIDENCE

    def test_real_edge_is_above_the_bar(self):
        real = compute_trade_statistics(_returns(12, 0.0098, 0.012))
        assert real["t_statistic"] >= MIN_T_STATISTIC_FOR_EVIDENCE


class TestEvidenceStorePersistsSignificance:
    def test_significance_is_stored_and_reloaded(self, tmp_path):
        path = tmp_path / "evidence.json"
        store = StrategyEvidenceStore(path)
        store.record_evidence(
            strategy_id="probe_alpha",
            symbol="EURUSD",
            timeframe="H1",
            data_window_end=datetime.now(timezone.utc),
            gross_return=0.12,
            total_trades=40,
            avg_position_size=1.0,
            max_concurrent_positions=1,
            regime_metrics={
                "ALL": {
                    "sharpe": 1.9,
                    "win_rate": 0.55,
                    "profit_factor": 1.4,
                    "trades": 40,
                    "max_drawdown_pct": 4.2,
                    "t_statistic": 3.4,
                    "trades_per_year": 180.0,
                    "window_days": 120.0,
                    "annualized_sharpe": 2.1,
                    "is_reliable": True,
                }
            },
        )

        reloaded = StrategyEvidenceStore(path)
        evidence = reloaded._store["probe_alpha"]
        regime = evidence.regime_breakdown["ALL"]
        assert regime.t_statistic == pytest.approx(3.4)
        assert regime.trades_per_year == pytest.approx(180.0)
        assert regime.window_days == pytest.approx(120.0)
        assert regime.is_reliable is True

    def test_store_file_keeps_the_significance_fields(self, tmp_path):
        path = tmp_path / "evidence.json"
        store = StrategyEvidenceStore(path)
        store.record_evidence(
            strategy_id="probe_alpha",
            symbol="EURUSD",
            timeframe="H1",
            data_window_end=datetime.now(timezone.utc),
            gross_return=0.12,
            total_trades=40,
            regime_metrics={
                "ALL": {
                    "sharpe": 1.9,
                    "win_rate": 0.55,
                    "profit_factor": 1.4,
                    "trades": 40,
                    "max_drawdown_pct": 4.2,
                    "t_statistic": 3.4,
                }
            },
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload[0]["regime_breakdown"]["ALL"]["t_statistic"] == pytest.approx(3.4)


class TestBreakevenHurdle:
    def test_bigger_sample_lowers_the_breakeven_requirement(self):
        small = compute_sizing_corrected_breakeven_bps(0.10, total_trades=12, avg_position_size=1.0)
        large = compute_sizing_corrected_breakeven_bps(0.10, total_trades=120, avg_position_size=1.0)
        assert small > large

    def test_evidence_from_an_old_window_is_stale(self, tmp_path):
        path = tmp_path / "evidence.json"
        old_end = datetime.now(timezone.utc) - timedelta(days=200)
        store = StrategyEvidenceStore(path)
        store.record_evidence(
            strategy_id="old_alpha",
            symbol="EURUSD",
            timeframe="H1",
            data_window_end=old_end,
            gross_return=0.5,
            total_trades=60,
        )
        reloaded = StrategyEvidenceStore(path)
        eligible, reason = reloaded.is_strategy_eligible_to_trade("old_alpha")
        assert eligible is False
        assert "STALE" in reason
