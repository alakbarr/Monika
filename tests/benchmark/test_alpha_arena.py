"""
Unit tests for benchmark/alpha_arena.py (Elo rating calculations and tournament management).
"""
import pytest
from benchmark.alpha_arena import (
    AlphaArenaTournament,
    update_elo,
)


def test_update_elo():
    # Equal players, A wins
    new_a, new_b, d_a, d_b = update_elo(1200.0, 1200.0, score_a=1.0, k=32.0)
    assert new_a == 1216.0
    assert new_b == 1184.0
    assert d_a == 16.0
    assert d_b == -16.0

    # Draw
    new_a, new_b, d_a, d_b = update_elo(1200.0, 1200.0, score_a=0.5, k=32.0)
    assert new_a == 1200.0
    assert new_b == 1200.0


def test_alpha_arena_tournament():
    tournament = AlphaArenaTournament(k_factor=32.0)

    # Match 1: Claude (higher Sharpe) vs GPT
    m1 = tournament.record_match(
        "Claude-3.7-Sonnet",
        "GPT-4o",
        metrics_a={"sharpe_ratio": 1.8, "pnl_pct": 5.0},
        metrics_b={"sharpe_ratio": 1.1, "pnl_pct": 3.2},
    )

    assert m1.winner == "Claude-3.7-Sonnet"
    assert m1.new_elo_a > 1200.0
    assert m1.new_elo_b < 1200.0

    # Match 2: DeepSeek vs GPT
    m2 = tournament.record_match(
        "DeepSeek-R1",
        "GPT-4o",
        metrics_a={"sharpe_ratio": 1.5, "pnl_pct": 4.0},
        metrics_b={"sharpe_ratio": 0.9, "pnl_pct": 1.0},
    )
    assert m2.winner == "DeepSeek-R1"

    leaderboard = tournament.get_leaderboard()
    assert len(leaderboard) == 3
    assert leaderboard[0]["name"] == "Claude-3.7-Sonnet"
    assert leaderboard[-1]["name"] == "GPT-4o"
    assert leaderboard[-1]["record"] == "0-2-0"
