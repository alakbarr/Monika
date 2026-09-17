# ==============================================================================
# File: utils/performance_reviewer.py
# ==============================================================================

"""
Performance Reviewer — Peninjau performa trading mingguan.
Otomatis menghasilkan 'lessons learned' (evaluasi) & perbarui file skills/trading/performance_notes.md.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from database.models import PaperTradeRecord, AssetAnalysis, SystemConfig
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

logger = logging.getLogger("TradingAgent.PerformanceReviewer")

import os
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PERFORMANCE_NOTES_PATH = _REPO_ROOT / "skills" / "trading" / "performance_notes.md"
FUNDAMENTAL_PERFORMANCE_NOTES_PATH = _REPO_ROOT / "skills" / "trading" / "fundamental_performance_notes.md"

async def generate_fundamental_performance_review(session: AsyncSession) -> Optional[str]:
    """
    Analisa akurasi Stage 1 Fundamental Bias dan hasilkan evaluasi.
    Buat file markdown (catatan evaluasi performa fundamental) & kembalikan kontennya.
    """
    from utils.analytics.agent_performance_monitor import compute_agent_accuracy_report
    report = await compute_agent_accuracy_report(session, days_back=30)
    stage1 = report.get('stage1_bias_accuracy', {})
    
    if stage1.get('total_checked', 0) < 25:
        logger.info(f"Fundamental performance notes skipped: insufficient sample size (N={stage1.get('total_checked', 0)} < 25)")
        return None
        
    lines = [
        f"# Fundamental Stage Performance Notes — Auto-Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"## Overall Macro Bias Accuracy (Last 30 Days)",
        f"- **Accuracy**: {stage1.get('overall', 0)}% (over {stage1.get('total_checked', 0)} briefs)",
        f"- **Brier Score**: {stage1.get('brier_score', 0)} (lower is better, 0 is perfect)",
        f"- **System Verdict**: {stage1.get('interpretation', 'Unknown')}",
        "",
        "## Performance by Currency (Min N>=15 for Actionable Directives)",
    ]
    
    for ccy, data in stage1.get('by_currency', {}).items():
        n_ccy = data.get('total', 0)
        lines.append(f"- **{ccy}**: {data.get('accuracy', 0)}% WR, Brier Score: {data.get('brier_score', 0)} (from {n_ccy} briefs{' [low sample]' if n_ccy < 15 else ''})")
        
    lines.append("")
    lines.append("## Directives for Stage 1")
    lines.append("- If accuracy is below 50% or Brier Score > 0.25, you are being overconfident or relying on stale macro narratives.")
    lines.append("- For currencies with N >= 15 and < 40% accuracy, heavily discount your internal bias and rely more on technical price action (Stage 2).")
    lines.append("- For low-accuracy currencies, require stronger alignment from COT and Sentiment data.")
    
    content = "\n".join(lines)
    
    try:
        FUNDAMENTAL_PERFORMANCE_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        FUNDAMENTAL_PERFORMANCE_NOTES_PATH.write_text(content, encoding="utf-8")
        logger.info(f"Fundamental performance notes updated: {FUNDAMENTAL_PERFORMANCE_NOTES_PATH}")
        try:
            from skills.loader import invalidate_cache
            invalidate_cache()
        except Exception:
            pass
        return content
    except Exception as e:
        logger.error(f"Failed to write fundamental performance notes: {e}")
        return None

async def generate_weekly_review(session: AsyncSession, settings: dict) -> Optional[str]:
    """
    Analisa riwayat paper trade 30 hari terakhir.
    Buat file markdown (catatan evaluasi performa) & kembalikan kontennya.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30)
    
    from utils.analytics.paper_tracker import PaperTracker
    tracker = PaperTracker()
    stats = await tracker.get_statistics(session)
    
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.closed_at >= since)
        .order_by(PaperTradeRecord.closed_at.asc())
    )).all()

    if stats["total_trades"] < 10:
        return None  # Not enough data
        
    total = stats["total_trades"]
    win_rate = stats["win_rate_pct"]
    
    # Analyze by confluence score bucket
    by_confluence = stats.get("by_confluence", {})
    by_symbol = stats.get("by_symbol", {})
    
    STATISTICALLY_SIGNIFICANT_N = 30
    statistical_warning = ''
    if total < STATISTICALLY_SIGNIFICANT_N:
        statistical_warning = (
            f'## ⚠️ STATISTICAL WARNING: SMALL SAMPLE\n\n'
            f'**{total} trades is NOT statistically significant (need ≥{STATISTICALLY_SIGNIFICANT_N}).**\n'
            f'**DO NOT adjust thresholds or strategy based solely on this data.**\n'
            f'Treat all recommendations below as preliminary observations only.\n\n'
        )
    
    # Generate markdown content
    now = datetime.now(timezone.utc)
    lines = [
        f"# Performance Notes — Auto-Generated {now.strftime('%Y-%m-%d')}",
        f"",
        f"## IMPORTANT: These notes are INFORMATIONAL ONLY.",
        f"## Do NOT treat these as hard constraints. Each setup must be evaluated on its own merits.",
        f"",
        statistical_warning,
        f"## System Performance (Last 30 Days)",
        f"",
        f"- Total trades: {total}",
        f"- Win rate: {win_rate:.1f}%",
        f"- Breakeven minimum: ~44% (for R:R 1:1.3, intraday-range strategy)",
        f"",
    ]
    
    # Overall verdict
    if win_rate < 44:
        lines.append('## ⚠️ ATTENTION: Win rate below theoretical breakeven')
        lines.append('')
        lines.append(
            f'**Win rate {win_rate:.1f}% is below theoretical breakeven ({total} trades).**\n'
            f'NOTE: {total} trades may be insufficient for statistical significance (need ~50+). '
            f'Before raising confluence threshold, verify: (1) Is this a setup quality issue or market regime issue? '
            f'(2) Are recent losing trades clustering in one symbol or asset class? '
            f'(3) Did a recent high-impact event create a structural shift? '
            f'Apply judgment — do NOT mechanically raise threshold based solely on short-term win rate.'
        )
        lines.append("")
    elif win_rate < 55:
        lines.append('## ℹ️ MONITORING: Win rate below optimal range')
        lines.append('')
        lines.append(
            f'**Win rate {win_rate:.1f}% is below the 55% target ({total} trades analyzed).**\n'
            f'Standard confluence threshold still applies. '
            f'Focus on: entry timing quality, SL placement relative to structure, ADR-band compliance, '
            f'and whether entries are occurring too close to high-impact events.'
        )
        lines.append("")
    elif win_rate > 60:
        lines.append("## ✅ Performance Strong")
        lines.append("")
        lines.append("System performing well. Standard thresholds apply.")
        lines.append("")
    
    # Per-symbol performance
    lines.append("## Per-Symbol Win Rates (Reference Only — Past ≠ Future)")
    lines.append("")
    for sym, data in sorted(by_symbol.items()):
        sym_total = data.get("total", data.get("trades", data.get("wins", 0) + data.get("losses", 0)))
        sym_wins = data.get("wins", 0)
        sym_wr = data.get("win_rate", round(sym_wins / sym_total * 100, 1) if sym_total > 0 else 0)
        if sym_total >= 3:
            lines.append(
                f"- {sym}: {sym_wr:.0f}% WR ({sym_total} trades) "
                f"{'— UNDERPERFORMING, investigate root cause' if sym_wr < 35 else ''}"
            )
    
    lines.append("")
    lines.append("## Confluence Score Effectiveness (Reference)")
    lines.append("These show historical correlation — a low-scoring setup can still win if context changed.")
    lines.append("")
    
    for score in sorted(by_confluence.keys(), key=lambda x: int(x)):
        data = by_confluence[score]
        wr = data["wins"] / data["total"] * 100 if data["total"] > 0 else 0
        verdict = "✅ profitable" if wr >= 45 else ("⚠️ borderline" if wr >= 33 else "❌ losing")
        lines.append(f"- Score {score}: {wr:.0f}% WR ({data['total']} trades) — {verdict}")

    # --- Section: Performance by Market Session ---
    lines.append('')
    lines.append('## Performance by Market Session (Reference)')
    lines.append('Based on UTC hour of trade entry:')
    lines.append('')
    
    session_buckets = stats.get("session_buckets", {})
    
    for key, data in session_buckets.items():
        if data['total'] >= 3:
            wr = data['wins'] / data['total'] * 100
            verdict = '✅ profitable' if wr >= 45 else '⚠️ borderline' if wr >= 33 else '❌ losing — avoid this session'
            lines.append(f"- {data['label']}: {wr:.0f}% WR ({data['total']} trades) — {verdict}")
        elif data['total'] > 0:
            lines.append(f"- {data['label']}: {data['total']} trades (insufficient data)")
    
    # --- Section: Performance by Priced-In Score ---
    lines.append('')
    lines.append('## Performance by Priced-In Score (Reference)')
    lines.append('Higher priced-in score = more risk. Expected: lower win rate at high priced-in scores.')
    lines.append('')
    
    pi_buckets = stats.get("by_priced_in", {})
    
    for bucket in sorted(pi_buckets.keys(), key=lambda x: int(x.split('_')[1])):
        data = pi_buckets[bucket]
        if data['total'] >= 3:
            wr = data['wins'] / data['total'] * 100
            pi_score = data['score']
            if pi_score >= 8 and wr > 50:
                verdict = '⚠️ WARNING: High win rate at high priced-in score is suspicious — check if entries are actually post-event'
            elif pi_score >= 8 and wr < 40:
                verdict = '✅ Expected: high priced-in score correctly associated with lower win rate'
            elif pi_score <= 4 and wr >= 50:
                verdict = '✅ Good: low priced-in setups are profitable'
            else:
                verdict = ''
            lines.append(f"- Priced-In {pi_score}/10: {wr:.0f}% WR ({data['total']} trades) {verdict}")
    
    # --- Section: Holding Duration Analysis ---
    lines.append('')
    lines.append('## Trade Duration Analysis')
    
    avg_win_hold = stats.get("avg_win_hold_hours", 0)
    avg_loss_hold = stats.get("avg_loss_hold_hours", 0)
    
    if avg_win_hold > 0 or avg_loss_hold > 0:
        lines.append(f'- Average winning trade duration: {avg_win_hold:.1f} hours')
        lines.append(f'- Average losing trade duration: {avg_loss_hold:.1f} hours')
        
        if avg_loss_hold > avg_win_hold * 1.5:
            lines.append('⚠️ CONCERN: Losses are held significantly longer than wins. Possible "let losers run, cut winners short" bias. Review SL placement and trailing stop settings.')
        elif avg_win_hold > avg_loss_hold * 2:
            lines.append('✅ Good: Winning trades are held significantly longer — allowing trades to run to full TP.')
    
    # --- Section: Day of Week Analysis ---
    lines.append('')
    lines.append('## Performance by Day of Week (Reference)')
    
    dow_buckets = {'Monday': {'wins':0,'total':0}, 'Tuesday': {'wins':0,'total':0},
                   'Wednesday': {'wins':0,'total':0}, 'Thursday': {'wins':0,'total':0}, 
                   'Friday': {'wins':0,'total':0}, 'Saturday': {'wins':0,'total':0}, 
                   'Sunday': {'wins':0,'total':0}}
    
    dow_names = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    for r, a in records:
        if r.opened_at:
            dow = dow_names[r.opened_at.weekday()]
            dow_buckets[dow]['total'] += 1
            if (r.pnl_pct or 0) > 0:
                dow_buckets[dow]['wins'] += 1
    
    for day in dow_names:
        data = dow_buckets[day]
        if data['total'] >= 3:
            wr = data['wins'] / data['total'] * 100
            flag = '❌ avoid' if wr < 33 else '⚠️ borderline' if wr < 45 else '✅'
            lines.append(f"- {day}: {wr:.0f}% WR ({data['total']} trades) {flag}")

    try:
        from utils.analytics.analysis_tracker import compute_factor_effectiveness
        factor_data = await compute_factor_effectiveness(session, days_back=30)
        if not factor_data.get('insufficient_data') and factor_data.get('total_trades_analyzed', 0) >= 10:
            lines.append('')
            lines.append('## Confluence Factor Effectiveness (Reference — What Actually Predicts Wins)')
            lines.append('These are HISTORICAL correlations. High-performing factors deserve more weight.')
            lines.append('')
            factors = factor_data.get('factor_effectiveness', {})
            strong = [(k, v) for k, v in factors.items() if v.get('assessment') == 'STRONG_PREDICTOR']
            weak = [(k, v) for k, v in factors.items() if v.get('assessment') in ('WEAK_PREDICTOR', 'NEGATIVE_PREDICTOR')]
            
            if strong:
                lines.append('**Historically Strong Factors (prioritize these):**')
                for k, v in strong[:5]:
                    lines.append(f"- {k.replace('_', ' ').title()}: {v['win_rate']:.0f}% WR ({v['total']} trades)")
            
            if weak:
                lines.append('')
                lines.append('**Historically Weak/Negative Factors (be skeptical of these alone):**')
                for k, v in weak[:3]:
                    lines.append(f"- {k.replace('_', ' ').title()}: {v['win_rate']:.0f}% WR ({v['total']} trades) — {v['assessment']}")
    except Exception as e:
        logger.debug(f'Factor effectiveness section skipped: {e}')

    # Generate specific recommendations untuk confluence threshold
    try:
        from utils.analytics.analysis_tracker import get_confluence_calibration_status
        calibration = await get_confluence_calibration_status(session)
        if not calibration.get('insufficient_data') and calibration.get('recommendation') != 'MAINTAIN':
            optimal = calibration.get('optimal_threshold_from_data', 7)
            current = calibration.get('current_threshold', 7)
            lines.append('')
            lines.append(f'## THRESHOLD CALIBRATION RECOMMENDATION')
            lines.append(f'')
            lines.append(f'Based on {calibration.get("calibration_data", {}).keys().__len__()} data points:')
            if optimal > current:
                lines.append(f'- Current threshold: {current}/14 → **Recommended: {optimal}/14**')
                lines.append(f'- Reason: Trades scoring {current}-{optimal-1} have historically underperformed breakeven')
                lines.append(f'- Action: Model should be more selective — only enter at confluence ≥ {optimal}')
            elif optimal < current:
                lines.append(f'- Current threshold: {current}/14 → **Could lower to: {optimal}/14**')
                lines.append(f'- Note: High-quality setups being missed. Consider lowering threshold.')
            lines.append('')
            lines.append(f'*Note: This is a DATA-DRIVEN recommendation. Apply judgment before implementing.*')
    except Exception as e:
        logger.debug(f'Calibration section in review failed: {e}')

    # Phase 6 Task 1: Auto-drop NEGATIVE_PREDICTOR factors
    try:
        from utils.analytics.analysis_tracker import compute_factor_weights_recommendation
        from database.models import SystemConfig
        import json
        
        weight_recs = await compute_factor_weights_recommendation(session, min_trades=30)
        if weight_recs.get("status") == "success":
            drop_factors = weight_recs.get("recommendations", {}).get("drop_factors", [])
            
            # Retrieve history of dropped factors to track ">= 2 weeks" logic
            cfg_key = "factor_negative_weeks_count"
            cfg_row = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key)
            )).scalar_one_or_none()
            
            negative_weeks = {}
            if cfg_row and cfg_row.value:
                negative_weeks = json.loads(cfg_row.value)
                
            # Increment count for current drop factors and apply decay
            keep_factors = weight_recs.get('recommendations', {}).get('increase_weight', []) + \
                           weight_recs.get('recommendations', {}).get('keep_as_is', [])
            
            new_negative_weeks = dict(negative_weeks)
            for f in drop_factors:
                new_negative_weeks[f] = new_negative_weeks.get(f, 0) + 1
                
            for f in keep_factors:
                if f in new_negative_weeks:
                    new_negative_weeks[f] = max(0, new_negative_weeks[f] - 1)
                    if new_negative_weeks[f] == 0:
                        del new_negative_weeks[f]
                        logger.info(f"Factor '{f}' recovered — removed from negative weeks tracking")
                        
            dropped_final = [f for f, count in new_negative_weeks.items() if count >= 2]
                    
            if dropped_final:
                lines.append('')
                lines.append('## AUTO-DROPPED FACTORS (DO NOT USE)')
                lines.append('The following factors have been statistically proven to result in losses for >=2 weeks.')
                lines.append('They are automatically removed from valid confluence checklist:')
                for f in dropped_final:
                    lines.append(f'- {f}')
                    
            # Update DB for next week
            if cfg_row:
                cfg_row.value = json.dumps(new_negative_weeks)
            else:
                session.add(SystemConfig(key=cfg_key, value=json.dumps(new_negative_weeks)))
                
            # Save dropped_final so per_asset_stage.py can read it and mutate STAGE2_TOOLS
            final_key = "confluence_dropped_factors"
            final_row = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == final_key)
            )).scalar_one_or_none()
            
            if final_row:
                final_row.value = json.dumps(dropped_final)
            else:
                session.add(SystemConfig(key=final_key, value=json.dumps(dropped_final)))
                
            await session.commit()
    except Exception as e:
        logger.error(f'Factor weights recommendation failed: {e}')

    try:
        patterns = await analyze_failure_patterns(session, records)
        if patterns:
            lines.append("")
            lines.append("## FAILURE PATTERNS (STRUCTURAL LEARNING)")
            lines.append("These are specific, recurring situations where trades have failed. ADJUST bias accordingly.")
            lines.append("")
            for p in patterns:
                lines.append(f"- {p}")
    except Exception as e:
        logger.error(f'Failure pattern analysis failed: {e}')

    lines.append("")
    lines.append("*This file is auto-generated each week by the performance reviewer.*")
    lines.append("*Do not edit manually — changes will be overwritten.*")
    
    content = "\n".join(lines)
    
    # Write to file
    try:
        PERFORMANCE_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERFORMANCE_NOTES_PATH.write_text(content, encoding="utf-8")
        logger.info(f"Performance notes updated: {PERFORMANCE_NOTES_PATH}")
        # CRITICAL: Clear LRU cache so next analysis cycle reads the new content
        try:
            from skills.loader import invalidate_cache
            invalidate_cache()
            logger.info('Skills LRU cache cleared — AI will read updated performance notes on next cycle')
        except Exception as e:
            logger.debug(f'Cache invalidation failed: {e}')
        return content
    except Exception as e:
        logger.error(f"Failed to write performance notes: {e}")
        return None

async def analyze_failure_patterns(session: AsyncSession, records) -> list[str]:
    """Identify specific, actionable failure patterns."""
    patterns = []
    
    # Pattern 1: Losses concentrated in specific DXY trend context
    losses_in_dxy_up = []  # BUY ketika DXY trending up
    for r, a in records:
        if r.exit_reason == 'sl_hit' and a and a.rationale:
            if 'DXY' in (a.rationale or '') and 'strengthen' in (a.rationale or '').lower():
                if a.decision == 'buy':
                    losses_in_dxy_up.append(r.symbol)
    
    if len(losses_in_dxy_up) >= 3:
        patterns.append(
            f"WARNING: {len(losses_in_dxy_up)} BUY trades hit SL during DXY strengthening "
            f"({', '.join(set(losses_in_dxy_up))}). "
            "When DXY is in confirmed uptrend, reduce BUY bias on USD pairs."
        )
    
    # Pattern 2: Consecutive losses in specific session
    # Pattern 3: High confluence score but still losing (score inflation indicator)
    
    return patterns

async def should_regenerate_fundamental_notes(session: AsyncSession) -> tuple[bool, str]:
    from utils.analytics.agent_performance_monitor import compute_agent_accuracy_report
    from database.models import SystemConfig
    from sqlalchemy import select
    report = await compute_agent_accuracy_report(session, days_back=14)
    stage1 = report.get('stage1_bias_accuracy', {})
    total_checked = stage1.get('total_checked', 0)
    if total_checked < 15:
        return (False, f'insufficient_stage1_samples ({total_checked}/15)')
    accuracy, brier = stage1.get('overall', 50), stage1.get('brier_score', 0.25)
    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'fundamental_notes_last_gen'))).scalar_one_or_none()
    hours_since = 999
    if cfg and cfg.value:
        try:
            last_time = datetime.fromisoformat(cfg.value)
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600
        except Exception:
            pass
    if accuracy < 45 and hours_since >= 12:
        return (True, f'stage1_accuracy_{accuracy:.0f}pct_below_random')
    if brier > 0.3 and hours_since >= 24:
        return (True, f'stage1_brier_{brier:.2f}_poorly_calibrated')
    if hours_since >= 24 * 7:
        return (True, 'weekly_scheduled')
    return (False, 'no_trigger')


async def evaluate_candidate_lessons(session: AsyncSession, settings: Optional[dict] = None) -> dict:
    """
    Evaluates CandidateLesson records in shadow mode against out-of-sample holdout trades.
    Promotes only candidate lessons with verified positive performance delta (N >= 30).
    """
    from database.models import CandidateLesson, PaperTradeRecord
    from analysis.memory.lesson_consolidator import promote_lesson_to_playbook
    import utils.clock as clock

    now = clock.now()
    candidates = (await session.execute(
        select(CandidateLesson).where(CandidateLesson.status == 'shadow')
    )).scalars().all()

    evaluated_summary = {'promoted': 0, 'rejected': 0, 'pending': 0}

    for cand in candidates:
        post_stmt = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == cand.symbol)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.closed_at >= cand.proposed_at)
            .order_by(PaperTradeRecord.closed_at.asc())
        )
        post_trades = (await session.execute(post_stmt)).scalars().all()
        
        # Setup matching filter if candidate has specific condition tags or keywords
        target_tags = getattr(cand, "condition_tags", None) or getattr(cand, "trigger_condition", None) or []
        if isinstance(target_tags, str):
            try:
                target_tags = json.loads(target_tags)
            except Exception:
                target_tags = [t.strip().lower() for t in target_tags.replace(";", ",").split(",") if t.strip()]
        elif isinstance(target_tags, list):
            target_tags = [str(t).lower() for t in target_tags]
            
        if target_tags and len(post_trades) >= 15:
            matched_post = []
            for t in post_trades:
                conf_factors = []
                cf_raw = getattr(t, "confluence_factors_json", None) or getattr(t, "confluence_factors", None)
                if isinstance(cf_raw, str):
                    try:
                        conf_factors = [str(x).lower() for x in json.loads(cf_raw)]
                    except Exception:
                        conf_factors = [cf_raw.lower()]
                elif isinstance(cf_raw, list):
                    conf_factors = [str(x).lower() for x in cf_raw]

                matches = any(
                    tag in str(getattr(t, "detection_method", "") or "").lower() or 
                    tag in str(getattr(t, "decision_source", "") or "").lower() or
                    tag in str(getattr(t, "exit_reason", "") or "").lower() or
                    any(tag in cf for cf in conf_factors)
                    for tag in target_tags
                )
                if matches:
                    matched_post.append(t)

            eval_cohort = matched_post if len(matched_post) >= 10 else post_trades
        else:
            eval_cohort = post_trades

        cand.evaluated_trades_count = len(eval_cohort)

        # FAST-PATH CORROBORATION (3-Strike Pattern):
        # If candidate setup has accumulated at least 3 out-of-sample trades and ALL 3 were wins (100% win rate),
        # or at least 4 trades with win rate >= 75%, promote to playbook immediately!
        if len(eval_cohort) >= 3:
            fast_wins = sum(1 for t in eval_cohort if t.exit_reason == 'tp_hit' or (t.pnl_pct is not None and t.pnl_pct > 0))
            fast_wr = (fast_wins / len(eval_cohort)) * 100.0
            if (len(eval_cohort) == 3 and fast_wins == 3) or (len(eval_cohort) >= 4 and fast_wr >= 75.0):
                cand.status = 'promoted'
                cand.promoted_at = now
                cand.win_rate_delta = round(fast_wr - 50.0, 2)
                await promote_lesson_to_playbook(f"### {cand.symbol}\n{cand.lesson_text}")
                logger.info(f"[AdaptiveMemory][Fast-Path] Candidate lesson promoted early for {cand.symbol}: {len(eval_cohort)} trades, WR={fast_wr:.1f}%")
                evaluated_summary['promoted'] += 1
                continue

        min_required = 15 if (target_tags and eval_cohort is not post_trades) else 25
        if len(eval_cohort) < min_required:
            evaluated_summary['pending'] += 1
            continue

        wins = sum(1 for t in eval_cohort if t.exit_reason == 'tp_hit' or (t.pnl_pct is not None and t.pnl_pct > 0))
        post_wr = (wins / len(eval_cohort)) * 100.0

        # Query baseline win rate prior to proposal
        pre_trades = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == cand.symbol)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.closed_at < cand.proposed_at)
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(30)
        )).scalars().all()

        if target_tags and len(pre_trades) >= 15:
            matched_pre = []
            for t in pre_trades:
                conf_factors = []
                cf_raw = getattr(t, "confluence_factors_json", None) or getattr(t, "confluence_factors", None)
                if isinstance(cf_raw, str):
                    try:
                        conf_factors = [str(x).lower() for x in json.loads(cf_raw)]
                    except Exception:
                        conf_factors = [cf_raw.lower()]
                elif isinstance(cf_raw, list):
                    conf_factors = [str(x).lower() for x in cf_raw]

                matches = any(
                    tag in str(getattr(t, "detection_method", "") or "").lower() or 
                    tag in str(getattr(t, "decision_source", "") or "").lower() or
                    tag in str(getattr(t, "exit_reason", "") or "").lower() or
                    any(tag in cf for cf in conf_factors)
                    for tag in target_tags
                )
                if matches:
                    matched_pre.append(t)

            pre_eval_cohort = matched_pre if len(matched_pre) >= 8 else pre_trades
        else:
            pre_eval_cohort = pre_trades

        pre_wins = sum(1 for t in pre_eval_cohort if t.exit_reason == 'tp_hit' or (t.pnl_pct is not None and t.pnl_pct > 0))
        pre_wr = (pre_wins / len(pre_eval_cohort) * 100.0) if pre_eval_cohort else 50.0

        wr_delta = round(post_wr - pre_wr, 2)
        cand.win_rate_delta = wr_delta

        if post_wr >= 52.0 and wr_delta >= 3.0:
            cand.status = 'promoted'
            cand.promoted_at = now
            await promote_lesson_to_playbook(f"### {cand.symbol}\n{cand.lesson_text}")
            logger.info(f"[AdaptiveMemory] Candidate lesson promoted for {cand.symbol} with causal attribution: WR={post_wr:.1f}% (delta={wr_delta:+.1f}%)")
            evaluated_summary['promoted'] += 1
        elif post_wr < 40.0 and wr_delta < -5.0:
            cand.status = 'rejected'
            cand.rejection_reason = f"OOS win rate dropped to {post_wr:.1f}% (delta={wr_delta:+.1f}%) on causal setup cohort"
            logger.warning(f"[AdaptiveMemory] Candidate lesson rejected for {cand.symbol}: {cand.rejection_reason}")
            evaluated_summary['rejected'] += 1
        else:
            evaluated_summary['pending'] += 1

    await session.commit()
    return evaluated_summary
