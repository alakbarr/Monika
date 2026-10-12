"""
Bayesian Multi-Armed Bandit (Thompson Sampling) & A/B testing framework for prompt variations.
Allows testing new prompts against baseline with dynamic traffic allocation based on live performance rewards.
"""
import random
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig

logger = logging.getLogger('TradingAgent.PromptABTest')


class PromptABTest:
    """
    Adaptive Multi-Armed Bandit & A/B testing framework for prompt variations.
    Uses Thompson Sampling (Beta-Bernoulli conjugate model) with recency decay
    to allocate traffic towards optimal prompt variants while maintaining exploration.
    """

    def __init__(
        self,
        test_name: str,
        variant_a_pct: float = 0.5,
        variants: Optional[List[str]] = None,
        decay_factor: float = 0.98,
        min_warmup_samples: int = 10,
    ):
        self.test_name = test_name
        self.variant_a_pct = variant_a_pct
        self.variants = variants or ['A', 'B']
        self.decay_factor = max(0.80, min(1.0, decay_factor))
        self.min_warmup_samples = min_warmup_samples

    def get_variant(self) -> str:
        """
        Synchronous heuristic fallback: Return 'A' (control) or 'B' (treatment).
        """
        if len(self.variants) == 2:
            return 'A' if random.random() < self.variant_a_pct else 'B'
        return random.choice(self.variants)

    async def get_variant_bandit(self, session: Optional[AsyncSession] = None) -> str:
        """
        Bayesian Thompson Sampling: Draw a sample from Beta(alpha, beta) posterior for each variant
        and select the variant with the highest expected reward.
        Falls back to uniform/proportional exploration during warmup phase (N < min_warmup_samples).
        """
        if session is None:
            return self.get_variant()

        state = await self.get_bandit_state(session)
        total_samples = sum(v.get("count", 0) for v in state.values())

        if total_samples < self.min_warmup_samples:
            # Exploration warmup phase
            return self.get_variant()

        # Thompson Sampling from Beta posterior
        samples = {}
        for var in self.variants:
            var_data = state.get(var, {"alpha": 1.0, "beta": 1.0})
            alpha = max(0.1, float(var_data.get("alpha", 1.0)))
            beta = max(0.1, float(var_data.get("beta", 1.0)))
            samples[var] = random.betavariate(alpha, beta)

        selected_variant = max(samples, key=samples.__getitem__)
        logger.debug(f"[Bandit:{self.test_name}] Sampled {samples} -> Selected Variant {selected_variant}")
        return selected_variant

    async def record_outcome(
        self,
        session: AsyncSession,
        variant: str,
        outcome: str,  # 'win', 'loss', 'wait', 'skip', 'breakeven'
        pnl_pct: float = 0.0
    ):
        """
        Record the trade/cycle outcome of a variant.
        Updates daily log and Bayesian Multi-Armed Bandit posterior with recency decay.
        """
        if variant not in self.variants:
            self.variants.append(variant)

        # 1. Update daily aggregate log
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        daily_key = f'ab_test_{self.test_name}_{variant}_{date_str}'
        existing_daily = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == daily_key)
        )).scalar_one_or_none()

        if existing_daily and existing_daily.value:
            daily_data = json.loads(existing_daily.value)
        else:
            daily_data = {'wins': 0, 'losses': 0, 'waits': 0, 'skips': 0, 'total_pnl': 0.0, 'count': 0}

        daily_data['count'] += 1
        daily_data['total_pnl'] += float(pnl_pct)
        if outcome == 'win' or (outcome not in ('wait', 'skip') and pnl_pct > 0):
            daily_data['wins'] += 1
        elif outcome == 'loss' or (outcome not in ('wait', 'skip') and pnl_pct < 0):
            daily_data['losses'] += 1
        elif outcome == 'wait':
            daily_data['waits'] += 1
        elif outcome == 'skip':
            daily_data['skips'] += 1

        daily_json = json.dumps(daily_data)
        if existing_daily:
            existing_daily.value = daily_json
        else:
            session.add(SystemConfig(key=daily_key, value=daily_json))

        # 2. Update Bayesian Thompson Sampling Posterior state with recency decay
        mab_key = f'mab_bandit_{self.test_name}'
        existing_mab = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == mab_key)
        )).scalar_one_or_none()

        if existing_mab and existing_mab.value:
            mab_data = json.loads(existing_mab.value)
        else:
            mab_data = {v: {"alpha": 1.0, "beta": 1.0, "count": 0, "total_pnl": 0.0} for v in self.variants}

        if variant not in mab_data:
            mab_data[variant] = {"alpha": 1.0, "beta": 1.0, "count": 0, "total_pnl": 0.0}

        # Apply recency decay across all variants to adapt to non-stationary market regimes
        for v in mab_data:
            cur_a = mab_data[v].get("alpha", 1.0)
            cur_b = mab_data[v].get("beta", 1.0)
            mab_data[v]["alpha"] = max(1.0, 1.0 + (cur_a - 1.0) * self.decay_factor)
            mab_data[v]["beta"] = max(1.0, 1.0 + (cur_b - 1.0) * self.decay_factor)

        # Update posterior for the chosen variant
        mab_data[variant]["count"] += 1
        mab_data[variant]["total_pnl"] += float(pnl_pct)

        if outcome == 'win' or (outcome not in ('wait', 'skip') and pnl_pct > 0):
            mab_data[variant]["alpha"] += 1.0
        elif outcome == 'loss' or (outcome not in ('wait', 'skip') and pnl_pct < 0):
            mab_data[variant]["beta"] += 1.0

        mab_json = json.dumps(mab_data)
        if existing_mab:
            existing_mab.value = mab_json
        else:
            session.add(SystemConfig(key=mab_key, value=mab_json))

        await session.commit()

    async def get_bandit_state(self, session: AsyncSession) -> Dict[str, Dict[str, Any]]:
        """
        Get current Thompson Sampling bandit posterior parameters and expected win rates.
        """
        mab_key = f'mab_bandit_{self.test_name}'
        existing_mab = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == mab_key)
        )).scalar_one_or_none()

        if existing_mab and existing_mab.value:
            state = json.loads(existing_mab.value)
        else:
            state = {v: {"alpha": 1.0, "beta": 1.0, "count": 0, "total_pnl": 0.0} for v in self.variants}

        for v, d in state.items():
            a = float(d.get("alpha", 1.0))
            b = float(d.get("beta", 1.0))
            d["expected_win_rate"] = round(a / (a + b), 4)
            cnt = d.get("count", 0)
            d["avg_pnl"] = round(d.get("total_pnl", 0.0) / cnt, 4) if cnt > 0 else 0.0

        return state

    async def get_results(self, session: AsyncSession, days_back: int = 7) -> dict:
        """Get A/B test results comparison over historical window."""
        results = {v: {'wins': 0, 'losses': 0, 'count': 0, 'total_pnl': 0.0} for v in self.variants}

        for days_ago in range(days_back):
            date_str = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime('%Y%m%d')
            for variant in self.variants:
                key = f'ab_test_{self.test_name}_{variant}_{date_str}'
                cfg = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == key)
                )).scalar_one_or_none()

                if cfg and cfg.value:
                    data = json.loads(cfg.value)
                    for k in results[variant]:
                        results[variant][k] += data.get(k, 0)

        # Compute win rates
        for variant in self.variants:
            total_market = results[variant]['wins'] + results[variant]['losses']
            results[variant]['win_rate'] = (
                results[variant]['wins'] / total_market * 100 if total_market > 0 else 0
            )
            results[variant]['avg_pnl'] = (
                results[variant]['total_pnl'] / results[variant]['count']
                if results[variant]['count'] > 0 else 0
            )

        return results


class OfflinePromptOptimizer:
    """
    Offline A/B Prompt Optimizer.
    Statistically evaluates prompt variants against historical replay cases and
    selects winning champion prompts based on empirical edge.
    """

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    def score_variant_performance(
        self,
        variant_name: str,
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Computes win rate, profit factor, and Sharpe-proxy score on replay evaluations.
        """
        if not results:
            return {
                "variant": variant_name,
                "count": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0
            }

        wins = sum(1 for r in results if r.get("pnl", 0.0) > 0)
        losses = sum(1 for r in results if r.get("pnl", 0.0) < 0)
        total_market = wins + losses
        win_rate = (wins / total_market * 100.0) if total_market > 0 else 0.0

        gross_profit = sum(r.get("pnl", 0.0) for r in results if r.get("pnl", 0.0) > 0)
        gross_loss = abs(sum(r.get("pnl", 0.0) for r in results if r.get("pnl", 0.0) < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        total_pnl = sum(r.get("pnl", 0.0) for r in results)

        return {
            "variant": variant_name,
            "count": len(results),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_pnl": round(total_pnl, 2)
        }

    def select_champion(
        self,
        scores: Dict[str, Dict[str, Any]],
        min_win_rate_delta: float = 3.0
    ) -> Tuple[str, bool]:
        """
        Selects the best performing prompt variant. Returns (champion_variant, is_promotable).
        Promotion requires beating baseline (Control 'A') by at least min_win_rate_delta.
        """
        if not scores:
            return "A", False

        control = scores.get("A", {})
        control_wr = float(control.get("win_rate", 50.0))

        best_variant = "A"
        best_score = control_wr

        for v, sc in scores.items():
            if v == "A":
                continue
            wr = float(sc.get("win_rate", 0.0))
            if wr > best_score:
                best_score = wr
                best_variant = v

        is_promotable = (best_score >= control_wr + min_win_rate_delta) and (scores.get(best_variant, {}).get("count", 0) >= 10)
        return best_variant, is_promotable

    async def record_champion(
        self,
        session: AsyncSession,
        test_name: str,
        champion_variant: str,
        scores: dict
    ) -> None:
        """Persists the champion prompt configuration to PostgreSQL SystemConfig."""
        key = f"champion_prompt_{test_name}"
        data_str = json.dumps({
            "champion": champion_variant,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "scores": scores
        })
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )).scalar_one_or_none()

        if cfg:
            cfg.value = data_str
        else:
            session.add(SystemConfig(key=key, value=data_str))
        await session.commit()
        logger.info(f"[OfflinePromptOptimizer] Promoted champion '{champion_variant}' for '{test_name}'.")
