"""
Unit tests for the Institutional Deterministic Playbook Screener (5-Pillar Architecture).
Verifies:
1. Complete loading and calibration parsing across all 8 universe symbols.
2. Deterministic archetype trigger evaluation (London expansion, Asian fade, Donchian, etc.).
3. Parametric order invariant preservation (calibrated SL/TP and contractual R:R).
4. FSM cooldown circuit-breaker suppression.
5. Clean ASCII prompt card formatting (cp1252-safe).
6. Pydantic schema validation and dynamic micro-skill loader integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from monika.domain.market.playbook_screener import (
    PlaybookRegistry,
    PlaybookScreener,
    PlaybookSpec,
    PlaybookTriggerSignal,
)
from monika.application.analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema
from monika.application.skills.loader import get_dynamic_micro_skills


class TestPlaybookScreener:
    """Institutional tests for PlaybookScreener and full quantitative wiring."""

    UNIVERSE_SYMBOLS = [
        "XAUUSD",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "AUDUSD",
        "BTCUSD",
        "XTIUSD",
        "XBRUSD",
    ]

    def test_registry_loads_all_assets(self) -> None:
        """Every symbol in the universe must have at least 25 verified empirical playbooks."""
        for sym in self.UNIVERSE_SYMBOLS:
            specs = PlaybookRegistry.load_playbooks_for_symbol(sym)
            assert len(specs) >= 25, f"{sym} must have at least 25 playbooks, found {len(specs)}"
            for spec in specs:
                assert spec.symbol == sym
                assert spec.profit_factor >= 1.0, f"{spec.name} PF must be >= 1.0"
                assert spec.win_rate > 0.30, f"{spec.name} WR must be > 30%"
                assert spec.sl_atr_mult > 0, f"{spec.name} SL ATR mult must be positive"
                assert spec.tp_atr_mult > 0, f"{spec.name} TP ATR mult must be positive"
                assert spec.max_hold_bars > 0, f"{spec.name} max hold must be positive"

    def test_reserve_catalog_loader(self) -> None:
        """Reserve catalog must provide accessible bench setups with full metrics."""
        xau_reserves = PlaybookRegistry.load_reserve_playbooks("XAUUSD")
        assert len(xau_reserves) >= 100, f"Expected >= 100 XAUUSD reserve setups, got {len(xau_reserves)}"
        for r in xau_reserves:
            assert r["symbol"] == "XAUUSD"
            assert r["metrics"]["total_pnl_pct"] >= 15.0
            assert r["metrics"]["win_rate_pct"] >= 40.0
            assert r["metrics"]["profit_factor"] >= 1.15
            assert r["status"] == "candidate"

        all_reserves = PlaybookRegistry.load_reserve_playbooks()
        assert len(all_reserves) >= 150

    def _generate_synthetic_bars(
        self,
        base_price: float = 2640.0,
        count: int = 30,
        breakout_at_end: bool = True,
        breakout_direction: str = "BUY",
    ) -> List[Dict[str, Any]]:
        """Generate consistent synthetic H1 bars for deterministic testing."""
        bars: List[Dict[str, Any]] = []
        for i in range(count):
            p = base_price + (i * 0.2)
            b = {
                "time": f"2026-10-15T{i % 24:02d}:00:00Z",
                "open": p,
                "high": p + 2.0,
                "low": p - 2.0,
                "close": p + 0.5,
                "tick_volume": 1000.0,
            }
            bars.append(b)

        if breakout_at_end:
            last = bars[-1]
            if breakout_direction == "BUY":
                last["open"] = base_price + 5.0
                last["high"] = base_price + 18.0
                last["low"] = base_price + 4.5
                last["close"] = base_price + 16.5  # Breakout high
                last["tick_volume"] = 2500.0  # Volume expansion
            else:
                last["open"] = base_price - 5.0
                last["high"] = base_price - 4.5
                last["low"] = base_price - 18.0
                last["close"] = base_price - 16.5  # Breakdown low
                last["tick_volume"] = 2500.0

        return bars

    def test_london_expansion_trigger_buy(self) -> None:
        """London expansion must trigger BUY on valid breakout at 08:00 UTC."""
        bars = self._generate_synthetic_bars(base_price=2640.0, breakout_at_end=True, breakout_direction="BUY")
        eval_time = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)

        report = PlaybookScreener.screen(
            symbol="XAUUSD",
            bars=bars,
            now_utc=eval_time,
            macro_regime="risk_on_bullish",
        )

        assert report.total_evaluated >= 15
        active_names = [s.playbook_name for s in report.active_signals]
        assert any("london_expansion" in n for n in active_names), f"Expected london_expansion in {active_names}"

        london_sig = next(s for s in report.active_signals if "london_expansion" in s.playbook_name)
        assert london_sig.direction == "BUY"
        assert london_sig.sl_price < london_sig.entry_price
        assert london_sig.tp_price > london_sig.entry_price
        assert london_sig.rr_ratio >= 1.5
        assert london_sig.macro_alignment == "ALIGNED"
        assert london_sig.confidence >= 0.75

    def test_cooldown_circuit_breaker(self) -> None:
        """Playbooks marked in cooldown must be suppressed from active signals."""
        bars = self._generate_synthetic_bars(base_price=2640.0, breakout_at_end=True, breakout_direction="BUY")
        eval_time = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)

        target_pb = "xauusd_london_expansion_playbook"
        report = PlaybookScreener.screen(
            symbol="XAUUSD",
            bars=bars,
            now_utc=eval_time,
            cooldown_playbooks={target_pb},
        )

        assert target_pb in report.cooldown_playbooks
        active_names = [s.playbook_name for s in report.active_signals]
        assert target_pb not in active_names

    def test_clean_ascii_prompt_formatting(self) -> None:
        """Prompt card must format cleanly without unicode charmap errors on cp1252."""
        bars = self._generate_synthetic_bars(base_price=2640.0, breakout_at_end=True, breakout_direction="BUY")
        eval_time = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)

        report = PlaybookScreener.screen(
            symbol="XAUUSD",
            bars=bars,
            now_utc=eval_time,
        )

        card = report.format_for_prompt()
        assert "-- QUANTITATIVE PLAYBOOK SIGNAL SCREENER (XAUUSD) --" in card
        assert "-- END PLAYBOOK SCREENER --" in card
        # Verify it encodes to standard ascii/cp1252 without exceptions
        encoded = card.encode("ascii", errors="strict")
        assert len(encoded) > 100

    def test_pydantic_schema_playbook_id(self) -> None:
        """SubmitAssetAnalysisSchema must accept and validate playbook_id."""
        data = {
            "symbol": "XAUUSD",
            "decision": "buy",
            "confidence": 0.85,
            "rationale": "London expansion verified by 1.8x ATR buffer and SMC orderblock.",
            "invalidation": "Invalid if D1 closes below 2630.",
            "invalidation_price": 2630.0,
            "invalidation_direction": "below",
            "stop_loss": 2636.50,
            "take_profit": 2665.00,
            "entry_condition": {"condition_type": "market", "price": 2645.0},
            "confluence_score": 10,
            "priced_in_score": 3,
            "playbook_id": "xauusd_london_expansion_playbook",
        }

        validated = SubmitAssetAnalysisSchema.model_validate(data)
        assert validated.playbook_id == "xauusd_london_expansion_playbook"

        # Test dictionary coercion
        data["playbook_id"] = {"name": "xauusd_london_expansion_playbook"}
        validated2 = SubmitAssetAnalysisSchema.model_validate(data)
        assert validated2.playbook_id == "xauusd_london_expansion_playbook"

        # Test None coercion
        data["playbook_id"] = "none"
        validated3 = SubmitAssetAnalysisSchema.model_validate(data)
        assert validated3.playbook_id is None

    def test_dynamic_micro_skills_loader_wiring(self) -> None:
        """get_dynamic_micro_skills must include the active playbook when signaled."""
        skills = get_dynamic_micro_skills(
            "XAUUSD",
            {"active_playbook": "xauusd_london_expansion_playbook"},
        )
        assert "xauusd_london_expansion_playbook" in skills
