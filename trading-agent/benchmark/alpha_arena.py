"""
Alpha Arena: Head-to-Head Tournament Engine for LLM Models & Strategies.
Evaluates competitors on identical historical tick/candle windows using Elo ratings.
Source: FinceptTerminal Alpha Arena
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ArenaCompetitor:
    name: str
    elo: float = 1200.0
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    total_pnl_pct: float = 0.0


@dataclass
class ArenaMatchResult:
    competitor_a: str
    competitor_b: str
    winner: Optional[str]  # None for draw
    score_a: float        # 1.0 = win, 0.5 = draw, 0.0 = loss
    score_b: float
    elo_delta_a: float
    elo_delta_b: float
    new_elo_a: float
    new_elo_b: float
    pnl_diff_pct: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def update_elo(
    rating_a: float,
    rating_b: float,
    score_a: float,
    k: float = 32.0,
) -> Tuple[float, float, float, float]:
    """
    Standard Elo rating calculation.
    Returns: (new_rating_a, new_rating_b, delta_a, delta_b)
    """
    expected_a = 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))
    expected_b = 1.0 - expected_a

    score_b = 1.0 - score_a

    delta_a = round(k * (score_a - expected_a), 2)
    delta_b = round(k * (score_b - expected_b), 2)

    new_a = round(rating_a + delta_a, 2)
    new_b = round(rating_b + delta_b, 2)

    return new_a, new_b, delta_a, delta_b


class AlphaArenaTournament:
    """
    Manages head-to-head evaluation of LLM trading models or strategy variations.
    """

    def __init__(self, k_factor: float = 32.0):
        self.k_factor = k_factor
        self.competitors: Dict[str, ArenaCompetitor] = {}
        self.match_history: List[ArenaMatchResult] = []

    def register_competitor(self, name: str, initial_elo: float = 1200.0) -> ArenaCompetitor:
        if name not in self.competitors:
            self.competitors[name] = ArenaCompetitor(name=name, elo=initial_elo)
        return self.competitors[name]

    def record_match(
        self,
        name_a: str,
        name_b: str,
        metrics_a: dict,
        metrics_b: dict,
    ) -> ArenaMatchResult:
        """
        Record head-to-head match outcome on identical evaluation interval.
        Winner determined by:
        1. Higher Sharpe Ratio (if both > 0)
        2. Higher total PnL % (if Sharpe tied or <= 0)
        """
        comp_a = self.register_competitor(name_a)
        comp_b = self.register_competitor(name_b)

        pnl_a = float(metrics_a.get("pnl_pct", 0.0) or 0.0)
        pnl_b = float(metrics_b.get("pnl_pct", 0.0) or 0.0)
        sr_a = float(metrics_a.get("sharpe_ratio", 0.0) or 0.0)
        sr_b = float(metrics_b.get("sharpe_ratio", 0.0) or 0.0)

        pnl_diff = round(pnl_a - pnl_b, 2)

        # Scoring decision
        if sr_a > 0 and sr_b > 0 and abs(sr_a - sr_b) > 0.05:
            score_a = 1.0 if sr_a > sr_b else 0.0
        elif abs(pnl_diff) > 0.1:
            score_a = 1.0 if pnl_a > pnl_b else 0.0
        else:
            score_a = 0.5  # draw

        score_b = 1.0 - score_a
        winner = name_a if score_a == 1.0 else (name_b if score_b == 1.0 else None)

        new_a, new_b, d_a, d_b = update_elo(
            comp_a.elo, comp_b.elo, score_a=score_a, k=self.k_factor
        )

        # Update records
        comp_a.elo = new_a
        comp_b.elo = new_b
        comp_a.matches_played += 1
        comp_b.matches_played += 1
        comp_a.total_pnl_pct += pnl_a
        comp_b.total_pnl_pct += pnl_b

        if score_a == 1.0:
            comp_a.wins += 1
            comp_b.losses += 1
        elif score_b == 1.0:
            comp_b.wins += 1
            comp_a.losses += 1
        else:
            comp_a.draws += 1
            comp_b.draws += 1

        res = ArenaMatchResult(
            competitor_a=name_a,
            competitor_b=name_b,
            winner=winner,
            score_a=score_a,
            score_b=score_b,
            elo_delta_a=d_a,
            elo_delta_b=d_b,
            new_elo_a=new_a,
            new_elo_b=new_b,
            pnl_diff_pct=pnl_diff,
        )
        self.match_history.append(res)
        return res

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Return leaderboard ranked by Elo rating."""
        ranked = sorted(self.competitors.values(), key=lambda c: c.elo, reverse=True)
        return [
            {
                "rank": i + 1,
                "name": c.name,
                "elo": round(c.elo, 1),
                "matches": c.matches_played,
                "record": f"{c.wins}-{c.losses}-{c.draws}",
                "win_rate": round((c.wins / c.matches_played * 100.0), 1) if c.matches_played else 0.0,
                "total_pnl_pct": round(c.total_pnl_pct, 2),
            }
            for i, c in enumerate(ranked)
        ]
