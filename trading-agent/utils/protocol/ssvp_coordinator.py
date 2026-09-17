"""
SSVP Coordinator — Shared State Verification Protocol
Implements research-compliant SSVP with selective, threshold-gated synchronization.

Key improvements over initial implementation:
1. Per-symbol CDS (not global)
2. Selective sync (only when CDS > threshold)
3. Explicit ContextMerge integration
4. Anti-contamination guards
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger('TradingAgent.SSVPCoordinator')


class SSVPCoordinator:
    """
    Coordinates context synchronization between Stage 1 and Stage 2 agents.
    
    Per research: SSVP pauses joint reasoning only when CDS exceeds threshold,
    prevents contamination via selective synchronization.
    """

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        from utils.protocol.enhanced_cds import get_cds_thresholds
        self.thresholds = get_cds_thresholds(settings)
        self.warning_threshold = self.thresholds['warning']
        self.sync_threshold = self.thresholds['sync_trigger']
        self.block_threshold = self.thresholds['block_buysell']
        self.abort_threshold = self.thresholds['abort_all']

    async def _refresh_thresholds(self, session: AsyncSession):
        """Refresh dynamic thresholds from database."""
        from utils.protocol.enhanced_cds import get_cds_thresholds_async
        self.thresholds = await get_cds_thresholds_async(session, self.settings)
        self.warning_threshold = self.thresholds['warning']
        self.sync_threshold = self.thresholds['sync_trigger']
        self.block_threshold = self.thresholds['block_buysell']
        self.abort_threshold = self.thresholds['abort_all']

    async def check_pre_stage2_sync(
        self,
        session: AsyncSession,
        settings: dict
    ) -> tuple[bool, float, str]:
        """
        Pre-Stage-2 SSVP check.
        
        Returns: (should_proceed_globally, max_cds_across_symbols, status_message)
        
        Note: Even if should_proceed=True, individual symbols may still have
        high CDS and need ContextMerge. Use compute_per_symbol_safety() for that.
        """
        from database.models import FundamentalBrief
        from utils.protocol.brief_contamination_guard import BriefContaminationGuard

        # Get latest brief
        brief = (await session.execute(
            select(FundamentalBrief)
            .order_by(FundamentalBrief.generated_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if not brief or not brief.structured_json:
            return False, 0.0, "No fundamental brief available"

        await self._refresh_thresholds(session)

        try:
            brief_data = json.loads(brief.structured_json)
        except Exception:
            return False, 0.0, "Cannot parse fundamental brief"

        # Validate brief integrity (contamination guard)
        is_safe, contamination_issues, contamination_risk = \
            await BriefContaminationGuard.validate_brief_integrity(
                session, brief_data, settings
            )

        # Compute per-symbol CDS
        asset_universe = settings.get('trading', {}).get('asset_universe', [])
        per_symbol_safety = await BriefContaminationGuard.compute_per_symbol_safety(
            session, brief_data, asset_universe, settings
        )

        # Aggregate stats
        cds_values = [v['cds'] for v in per_symbol_safety.values()]
        max_cds = max(cds_values) if cds_values else 0.0
        avg_cds = sum(cds_values) / len(cds_values) if cds_values else 0.0
        
        abort_count = sum(1 for v in per_symbol_safety.values() if v['safety_level'] == 'abort')
        blocked_count = sum(1 for v in per_symbol_safety.values() if v['safety_level'] in ('abort', 'block_buysell'))
        total_count = len(per_symbol_safety)

        # Log summary
        logger.info(
            f"[SSVP] Pre-Stage-2 sync check: "
            f"max_cds={max_cds:.3f}, avg_cds={avg_cds:.3f}, "
            f"aborted={abort_count}/{total_count}, blocked={blocked_count}/{total_count}, "
            f"brief_contamination_risk={contamination_risk:.2f}"
        )

        # Phase 5: Budget-aware SSVP
        from database.models import SystemConfig
        budget_cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "api_cost_tracking")
        )).scalar_one_or_none()
        budget_remaining_pct = 100.0
        if budget_cfg and budget_cfg.value:
            try:
                history = json.loads(budget_cfg.value)
                now = datetime.now(timezone.utc)
                current_day = now.strftime("%Y-%m-%d")
                daily_tokens = sum(
                    e.get("stage1_tokens", 0) + e.get("stage2_tokens", 0)
                    for e in history if e.get("cycle_date", "").startswith(current_day)
                )
                daily_limit = int(settings.get("cost_tracking", {}).get("daily_token_limit", settings.get("cost_tracking", {}).get("daily_anthropic_limit", 10_000_000)))
                daily_pct_used = (daily_tokens / daily_limit) * 100 if daily_limit else 0
                budget_remaining_pct = 100.0 - daily_pct_used
            except Exception:
                pass

        # Decision: abort ALL only if majority of symbols have high CDS
        # This implements selective sync (not full-broadcast abort)
        abort_ratio_threshold = 0.8 if budget_remaining_pct < 15.0 else 0.6
        if budget_remaining_pct < 15.0:
            logger.warning(f"[SSVP] Daily token budget < 15% (remaining {budget_remaining_pct:.1f}%). Limiting fallback triggers.")
            
        if total_count > 0 and abort_count / total_count > abort_ratio_threshold:
            msg = (
                f"[SSVP ABORT] Majority of assets ({abort_count}/{total_count}) "
                f"have CDS >= {self.abort_threshold}. "
                f"Stage 1 brief has high contamination risk. "
                f"Triggering Stage 1 re-run. avg_cds={avg_cds:.3f} (budget remaining: {budget_remaining_pct:.1f}%)"
            )
            logger.warning(msg)
            return False, max_cds, msg

        # If brief is contaminated but CDS per-symbol varies, still proceed
        # (selective sync handles it per-symbol)
        contamination_note = ''
        if contamination_risk > 0.50:
            contamination_note = (
                f" [BRIEF WARNING: contamination_risk={contamination_risk:.2f}]"
            )

        msg = (
            f"[SSVP] Proceeding with per-symbol protection. "
            f"max_cds={max_cds:.3f}{contamination_note}"
        )
        return True, max_cds, msg

    async def compute_per_symbol_contexts(
        self,
        session: AsyncSession,
        brief_data: dict,
        symbols: list[str]
    ) -> dict[str, str]:
        """
        Compute per-symbol SSVP context injection strings.
        Only symbols with CDS > warning threshold get context injection.
        Others get empty string (no unnecessary noise).
        """
        from utils.protocol.brief_contamination_guard import BriefContaminationGuard

        await self._refresh_thresholds(session)
        
        per_symbol_safety = await BriefContaminationGuard.compute_per_symbol_safety(
            session, brief_data, symbols, self.settings
        )

        contexts = {}
        for symbol, safety_info in per_symbol_safety.items():
            cds = safety_info['cds']
            
            if cds >= self.warning_threshold:
                contexts[symbol] = safety_info['context']
                logger.info(
                    f"[SSVP] {symbol}: CDS={cds:.3f} "
                    f"safety={safety_info['safety_level']} "
                    f"→ context injected"
                )
            else:
                contexts[symbol] = ''  # No injection for low-CDS symbols
        
        return contexts

    async def compute_post_stage2_sync(
        self,
        session: AsyncSession,
        pa_results: dict
    ) -> tuple[dict, list[str]]:
        """
        Post-Stage-2 cross-agent synchronization.
        
        Implements SELECTIVE suppression of contradicting agents per research:
        - Only suppress the LOWER-CONFIDENCE agent in contradicting pairs
        - Do NOT propagate the "winning" agent's belief to others (no full-broadcast)
        
        Returns: (updated_pa_results, suppressed_symbols_list)
        """
        ssvp_enabled = self.settings.get('ssvp', {}).get('cross_agent_sync_enabled', True)
        if not ssvp_enabled:
            return pa_results, []

        from utils.protocol.cross_agent_sync import CrossAgentSynchronizer

        synchronizer = CrossAgentSynchronizer(
            contradiction_threshold=self.settings.get('ssvp', {}).get(
                'cross_agent_contradiction_threshold', 0.65
            )
        )

        pairs_with_contradiction = synchronizer.detect_contradictions(pa_results)

        if not pairs_with_contradiction:
            return pa_results, []

        # Log contradictions
        for pair_info in pairs_with_contradiction:
            logger.warning(
                f"[SSVP Cross-Agent] Contradiction: "
                f"{pair_info['sym1']} ({pair_info['dir1']}) vs "
                f"{pair_info['sym2']} ({pair_info['dir2']}), "
                f"expected_corr={pair_info['expected_corr']:.2f}, "
                f"suspect={pair_info['suspect']}"
            )

        updated_results, suppressed = synchronizer.apply_selective_suppression(
            pa_results, pairs_with_contradiction
        )

        return updated_results, suppressed

    def build_reconciliation_context(
        self,
        symbol: Optional[str] = None,
        cds: Optional[float] = None,
        breakdown: Optional[dict] = None
    ) -> str:
        """
        Build reconciliation context string for a symbol.
        Returns empty string if CDS is below warning threshold.
        """
        if symbol is None or cds is None:
            return ''

        if cds < self.warning_threshold:
            return ''

        from utils.protocol.brief_contamination_guard import (
            _build_warning_context, _build_contextmerge_prompt
        )

        if cds < self.sync_threshold:
            return _build_warning_context(symbol, cds, breakdown or {})
        else:
            force_wait = cds >= self.block_threshold
            return _build_contextmerge_prompt(symbol, cds, breakdown or {}, force_wait=force_wait)
