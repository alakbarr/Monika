import pytest
from benchmark.prompt_evolution import GEPAFullEvolver


def test_gepa_evolution_triggers():
    evolver = GEPAFullEvolver()

    # 1. In cooldown
    triggered, reason = evolver.check_evolution_triggers(
        closed_trades_count=10,
        rolling_drawdown_pct=1.0,
        days_since_last_evolution=3
    )
    assert triggered is False
    assert "cooldown" in reason

    # 2. Emergency Drawdown breaker (bypasses cooldown)
    triggered, reason = evolver.check_evolution_triggers(
        closed_trades_count=10,
        rolling_drawdown_pct=5.5,
        days_since_last_evolution=2
    )
    assert triggered is True
    assert "Emergency" in reason

    # 3. 40 trades sample trigger
    triggered, reason = evolver.check_evolution_triggers(
        closed_trades_count=45,
        rolling_drawdown_pct=2.0,
        days_since_last_evolution=8
    )
    assert triggered is True
    assert "Sample trigger" in reason

    # 4. 14-day scheduled trigger
    triggered, reason = evolver.check_evolution_triggers(
        closed_trades_count=15,
        rolling_drawdown_pct=1.0,
        days_since_last_evolution=14
    )
    assert triggered is True
    assert "Scheduled" in reason


def test_gepa_pareto_filter():
    evolver = GEPAFullEvolver()
    candidates = [
        {"name": "Prompt A", "score": 8.5, "tokens": 400, "invariant_score": 1.0},
        {"name": "Prompt B", "score": 8.0, "tokens": 500, "invariant_score": 1.0},  # dominated by A (worse score, more tokens)
        {"name": "Prompt C", "score": 9.2, "tokens": 700, "invariant_score": 1.0},  # Pareto: highest score
        {"name": "Prompt D", "score": 8.0, "tokens": 250, "invariant_score": 1.0},  # Pareto: lowest tokens
    ]

    frontier = evolver.pareto_filter(candidates)
    names = [c["name"] for c in frontier]
    assert "Prompt A" in names
    assert "Prompt C" in names
    assert "Prompt D" in names
    assert "Prompt B" not in names


def test_gepa_invariant_compliance():
    evolver = GEPAFullEvolver()
    valid_prompt = "Always use calculate_position_size and check priced_in score. Sanitize <untrusted_external_content>."
    valid, violations = evolver.verify_invariant_compliance(valid_prompt)
    assert valid is True
    assert len(violations) == 0

    bad_prompt = "You are a casual trader. Guess position sizes."
    valid, violations = evolver.verify_invariant_compliance(bad_prompt)
    assert valid is False
    assert len(violations) >= 2
