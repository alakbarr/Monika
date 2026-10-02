import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from tests.conftest import create_mock_async_session
from analysis.memory.layered_memory import compute_ebbinghaus_retention
from analysis.memory.counterfactual_simulator import CounterfactualSimulator


def test_ebbinghaus_retention_decay():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    # 1. Immediate memory (0 days old) -> R = 1.0
    r0 = compute_ebbinghaus_retention(now, stability_days=14.0, now_dt=now)
    assert abs(r0 - 1.0) < 1e-4

    # 2. Exactly 1 stability period old (14 days old, S = 14) -> R = 1/e ~ 0.3679
    t14 = now - timedelta(days=14)
    r14 = compute_ebbinghaus_retention(t14, stability_days=14.0, now_dt=now)
    assert abs(r14 - math.exp(-1.0)) < 1e-3

    # 3. Old unreinforced memory (60 days old, S = 14) -> R = exp(-60/14) ~ 0.0137 (< 0.10, decayed)
    t60 = now - timedelta(days=60)
    r60 = compute_ebbinghaus_retention(t60, stability_days=14.0, now_dt=now)
    assert r60 < 0.05

    # 4. Reinforced promoted memory (60 days old, S = 60) -> R = 1/e ~ 0.3679 (still active!)
    r60_promoted = compute_ebbinghaus_retention(t60, stability_days=60.0, now_dt=now)
    assert abs(r60_promoted - math.exp(-1.0)) < 1e-3


@pytest.mark.asyncio
async def test_counterfactual_simulator_robustness_gating():
    sim = CounterfactualSimulator()

    session = MagicMock()
    # Mock closed paper trades
    mock_trades = [
        MagicMock(pnl_pct=0.015),
        MagicMock(pnl_pct=0.020),
        MagicMock(pnl_pct=-0.005),
        MagicMock(pnl_pct=0.018),
        MagicMock(pnl_pct=0.012),
        MagicMock(pnl_pct=-0.008),
    ]
    mock_execute = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = mock_trades
    mock_execute.return_value = mock_res
    session.execute = mock_execute

    with patch.object(sim.lifecycle, "register_playbook") as mock_reg, \
         patch.object(sim.lifecycle, "_save_state"):
        mock_reg.return_value = MagicMock()
        res = await sim.simulate_candidate(
            session=session,
            playbook_name="pb_eurusd_trend_continuation",
            symbol="EURUSD",
            min_sample=6,
            min_win_rate=0.50,
        )

        assert res["promoted"] is True
        assert res["win_rate"] == (4 / 6)
        assert "cf_sl_1_5x_pnl" in res
        assert "cf_delayed_pnl" in res
        assert res["status"] == "active"


@pytest.mark.asyncio
async def test_reflector_dual_branch_negative_constraint():
    from analysis.memory.reflector import TradeReflector
    from database.models import DecisionReflection

    reflector = TradeReflector(settings={})
    session = create_mock_async_session()

    reflection = DecisionReflection(
        symbol="XAUUSD",
        decision="buy",
        was_profitable=False,
        outcome_pnl_usd=-150.0,
        specific_lesson="Entered into major H4 resistance before NY open",
        lesson_tags='["counter_trend_entry"]',
        rationale_summary="Breakout attempt",
        exit_reason="sl_hit",
        holding_hours=2.5,
        status="pending",
    )
    session.get.return_value = reflection

    # Mock LLM client response for reflection
    mock_llm = MagicMock()
    mock_llm.generate_content = AsyncMock(return_value="""{
        "reflection_text": "Failed trade due to resistance rejection.",
        "lesson_tags": ["counter_trend_entry"],
        "specific_lesson": "Entered into major H4 resistance before NY open",
        "next_trade_adjustment": "Wait for H4 breakout close before entering",
        "alpha_lesson": "Avoid premature long entries into resistance",
        "process_was_sound": false,
        "outcome_process_classification": "bad_process_bad_outcome",
        "macro_thesis_correct": false,
        "synthesis_adjudication_sound": false
    }""")
    reflector.llm_client = mock_llm

    with patch("database.safe_ops.safe_commit", new=AsyncMock()), \
         patch("database.event_store.TradingEventStore.emit", new=AsyncMock()):
        await reflector.reflect_on_trade(session, 1)

    # Verify that a Negative Constraint was persisted into session via SystemConfig
    added_configs = [args[0] for args, _ in session.add.call_args_list]
    neg_constraints = [c for c in added_configs if hasattr(c, "key") and "negative_constraint_XAUUSD" in c.key]
    assert len(neg_constraints) >= 1
    assert "Entered into major H4 resistance" in neg_constraints[0].value
