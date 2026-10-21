"""Phase 1 follow-up: the strategy evidence store must age on its own.

Since Phase 1 the evidence store is the only promotion source, so its aging
rules have to work without a scheduler. The stored status flag is a derived
value: it is always recalculated from the evidence window when the file is
read, so forged or outdated "FRESH" flags cannot keep a strategy trading.
"""

import json
from datetime import datetime, timedelta, timezone

from monika.application.analysis.strategies.evidence_store import (
    EvidenceStatus,
    StrategyEvidenceStore,
)


def _write_store(path, entries) -> None:
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _entry(strategy_id: str, window_end: datetime, status: str = EvidenceStatus.FRESH.value) -> dict:
    return {
        "strategy_id": strategy_id,
        "symbol": "EURUSD",
        "timeframe": "H1",
        "data_window_end": window_end.strftime("%Y-%m-%d"),
        "gross_return": 0.12,
        "total_trades": 40,
        "avg_position_size": 1.0,
        "max_concurrent_positions": 1,
        "breakeven_bps": 6.0,
        "regime_breakdown": {},
        "status": status,
        "evidence_age_days": 0,
        "updated_at": 0.0,
    }


def test_fresh_evidence_is_accepted(tmp_path):
    path = tmp_path / "evidence.json"
    _write_store(path, [_entry("fresh_alpha", datetime.now(timezone.utc) - timedelta(days=5))])

    store = StrategyEvidenceStore(path)
    eligible, reason = store.is_strategy_eligible_to_trade("fresh_alpha")
    assert eligible is True
    assert "Approved" in reason


def test_stored_fresh_flag_cannot_hide_stale_evidence(tmp_path):
    path = tmp_path / "evidence.json"
    # The file claims FRESH, but the window ended more than 180 days ago.
    _write_store(path, [_entry("stale_alpha", datetime.now(timezone.utc) - timedelta(days=200))])

    store = StrategyEvidenceStore(path)
    assert store._store["stale_alpha"].status == EvidenceStatus.STALE
    eligible, reason = store.is_strategy_eligible_to_trade("stale_alpha")
    assert eligible is False
    assert "STALE" in reason


def test_aging_evidence_keeps_trading_but_is_marked(tmp_path):
    path = tmp_path / "evidence.json"
    _write_store(path, [_entry("aging_alpha", datetime.now(timezone.utc) - timedelta(days=120))])

    store = StrategyEvidenceStore(path)
    assert store._store["aging_alpha"].status == EvidenceStatus.AGING
    eligible, _reason = store.is_strategy_eligible_to_trade("aging_alpha")
    assert eligible is True


def test_evidence_below_the_fee_hurdle_is_rejected(tmp_path):
    path = tmp_path / "evidence.json"
    entry = _entry("cheap_alpha", datetime.now(timezone.utc) - timedelta(days=5))
    entry["breakeven_bps"] = 1.2
    _write_store(path, [entry])

    store = StrategyEvidenceStore(path)
    eligible, reason = store.is_strategy_eligible_to_trade("cheap_alpha")
    assert eligible is False
    assert "breakeven" in reason.lower()
