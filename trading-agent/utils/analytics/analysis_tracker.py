# ==============================================================================
# File: utils/analysis_tracker.py
# ==============================================================================

"""
Analysis Quality Tracker.
Menganalisa kualitas trading (win rate) berdasarkan faktor/kondisi analisis (misal confidence score).
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import AssetAnalysis, TradeOutcome, SystemConfig, PaperTradeRecord
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

logger = logging.getLogger("TradingAgent.AnalysisTracker")


async def compute_analysis_quality_report(session: AsyncSession, days_back: int = 30) -> dict:
    """
    Hitung laporan kualitas analisis: profil win rate berdasarkan parameter konfluensi.
    Identifikasi kondisi sistematis untung/rugi.
    """
    from utils.analytics.paper_tracker import PaperTracker
    tracker = PaperTracker()
    stats = await tracker.get_statistics(session, days_back=days_back)
    
    total = stats.get("total_trades", 0)
    wins = stats.get("wins", 0)
    
    # Format according to what the system expects
    by_confluence = stats.get("by_confluence", {})
    by_priced_in = stats.get("by_priced_in", {})
    by_symbol = stats.get("by_symbol", {})
    by_symbol_dir = stats.get("by_symbol_direction", {})
    
    formatted_by_symbol = {}
    for k, v in sorted(by_symbol.items()):
        sym_total = v.get("total", v.get("trades", 0))
        sym_wins = v.get("wins", 0)
        sym_losses = v.get("losses", sym_total - sym_wins)
        sym_wr = v.get("win_rate", round(sym_wins / sym_total * 100, 1) if sym_total > 0 else 0.0)
        formatted_by_symbol[k] = {
            **v,
            "total": sym_total,
            "trades": sym_total,
            "wins": sym_wins,
            "losses": sym_losses,
            "win_rate": sym_wr,
            "pnl_pct": v.get("pnl_pct", 0.0),
            "total_pnl_pct": v.get("total_pnl_pct", v.get("pnl_pct", 0.0)),
        }
        
    formatted_by_symbol_dir = {}
    for k, v in sorted(by_symbol_dir.items()):
        sd_total = v.get("total", v.get("trades", 0))
        sd_wins = v.get("wins", 0)
        sd_losses = v.get("losses", sd_total - sd_wins)
        sd_wr = v.get("win_rate", round(sd_wins / sd_total * 100, 1) if sd_total > 0 else 0.0)
        formatted_by_symbol_dir[k] = {
            **v,
            "total": sd_total,
            "trades": sd_total,
            "wins": sd_wins,
            "losses": sd_losses,
            "win_rate": sd_wr,
            "pnl_pct": v.get("pnl_pct", 0.0),
            "total_pnl_pct": v.get("total_pnl_pct", v.get("pnl_pct", 0.0)),
        }
    
    report = {
        "total_outcomes": total,
        "total_wins": wins,
        "overall_win_rate": stats.get("win_rate_pct", 0),
        "days_back": days_back,
        "by_confluence_score": {
            k: {
                "win_rate": round(v["wins"] / v["total"] * 100, 1) if v.get("total", 0) > 0 else 0,
                **v
            }
            for k, v in sorted(by_confluence.items())
        },
        "by_priced_in_score": {
            k: {
                "win_rate": round(v["wins"] / v["total"] * 100, 1) if v.get("total", 0) > 0 else 0,
                **v
            }
            for k, v in sorted(by_priced_in.items())
        },
        "by_symbol": formatted_by_symbol,
        "by_symbol_direction": formatted_by_symbol_dir,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Save to SystemConfig for dashboard access
    cfg_key = "analysis_quality_report"
    existing = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == cfg_key)
    )).scalar_one_or_none()
    
    if existing:
        existing.value = json.dumps(report)
    else:
        session.add(SystemConfig(key=cfg_key, value=json.dumps(report)))
    await session.commit()
    
    return report


async def get_adaptive_threshold_hints(session: AsyncSession) -> dict:
    """
    Usulkan penyesuaian threshold konfluensi dinamis per aset berdasarkan performa terkini.
    Dipanggil oleh _get_adaptive_confluence_note() di per_asset_stage.py.
    """
    # Get the saved report
    cfg = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == "analysis_quality_report")
    )).scalar_one_or_none()
    
    if not cfg or not cfg.value:
        return {}
    
    try:
        report = json.loads(cfg.value)
    except Exception:
        return {}
    
    hints = {}
    breakeven_wr = 35  # With R:R ≥ 1:2, need > 33% WR to be profitable
    
    for symbol, data in report.get("by_symbol", {}).items():
        wr = data.get("win_rate", 50)
        total = data.get("total", data.get("trades", 0))
        
        if total < 15:
            hints[symbol] = {"threshold_adjustment": 0, "reason": "insufficient_data"}
        elif wr < breakeven_wr:
            adjustment = +2  # Raise threshold
            hints[symbol] = {
                "threshold_adjustment": adjustment,
                "reason": f"win_rate_{wr:.0f}pct_below_breakeven_{breakeven_wr}pct",
                "current_win_rate": wr,
            }
        elif wr > 60:
            hints[symbol] = {
                "threshold_adjustment": 0,
                "reason": f"performing_well_{wr:.0f}pct_win_rate",
                "current_win_rate": wr,
            }
        else:
            hints[symbol] = {"threshold_adjustment": 0, "reason": "acceptable_performance"}
    
    return hints


async def get_per_asset_bias_report(session: AsyncSession, days_back: int = 14) -> dict:
    """
    Deteksi bias terarah sistematis per aset.
    Jika satu arah terus rugi, indikasikan perlunya modifikasi sistem analisis, bukan sekadar penyesuaian threshold.
    """
    cfg = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == "analysis_quality_report")
    )).scalar_one_or_none()
    
    if not cfg or not cfg.value:
        return {"flagged_combinations": {}, "raw_data": {}}
    
    try:
        report = json.loads(cfg.value)
    except Exception:
        return {"flagged_combinations": {}, "raw_data": {}}
        
    bias_report = report.get("by_symbol_direction", {})
    
    # Flag problematic combinations (≥5 trades, <30% win rate)
    flagged = {}
    for key, data in bias_report.items():
        total = data.get("total", data.get("trades", 0))
        if total >= 5:
            wr = data.get("win_rate", 0)
            if wr < 30.0:
                parts = key.split('_')
                sym = parts[0]
                direction = parts[1] if len(parts) > 1 else "UNKNOWN"
                flagged[key] = {
                    "win_rate": round(wr, 1),
                    "trades": total,
                    "recommendation": f"AVOID {direction.upper()} on {sym} — systematic losing bias detected",
                }
    
    return {"flagged_combinations": flagged, "raw_data": bias_report}


async def analyze_debate_impact(session: AsyncSession, days_back: int = 30) -> dict:
    """
    (Phase 3): Analyzes the impact of the multi-agent debate stage.
    Compares the win rates of trades that were modified by debate vs those that were not.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    # Using the new was_debate_modified field
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
    )).all()
    
    if not records:
        return {"insufficient_data": True}
        
    debate_modified_trades = []
    original_trades = []
    
    for record, analysis in records:
        if analysis and analysis.was_debate_modified:
            debate_modified_trades.append(record)
        else:
            original_trades.append(record)
            
    def get_stats(trades_list):
        if not trades_list:
            return {"total": 0, "win_rate": 0.0, "avg_pnl": 0.0}
        wins = sum(1 for t in trades_list if (t.pnl_pct or 0) > 0)
        total = len(trades_list)
        avg_pnl = sum((t.pnl_pct or 0) for t in trades_list) / total
        return {
            "total": total,
            "win_rate": round((wins / total) * 100, 1),
            "avg_pnl": round(avg_pnl, 2)
        }
        
    return {
        "days_analyzed": days_back,
        "debate_modified": get_stats(debate_modified_trades),
        "original_unmodified": get_stats(original_trades),
        "total_analyzed": len(records),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


async def compute_factor_effectiveness(session: AsyncSession, days_back: int = 60) -> dict:
    """
    Analisa efektivitas faktor konfluensi dari confluence_factors_json.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
    )).all()
    
    if not records:
        return {"insufficient_data": True, "min_required": 20}
        
    overall_wins = sum(1 for record, _ in records if (record.pnl_pct or 0) > 0)
    p0 = overall_wins / len(records)
    
    factor_stats = {}
    
    for record, analysis in records:
        if not analysis or not analysis.confluence_factors_json:
            continue
            
        try:
            factors = json.loads(analysis.confluence_factors_json)
            if not isinstance(factors, list):
                continue
        except Exception:
            continue
            
        was_profitable = (record.pnl_pct or 0) > 0
        
        for factor in factors:
            if not isinstance(factor, str):
                continue
            if factor not in factor_stats:
                factor_stats[factor] = {"wins": 0, "losses": 0, "total": 0}
            
            factor_stats[factor]["total"] += 1
            if was_profitable:
                factor_stats[factor]["wins"] += 1
            else:
                factor_stats[factor]["losses"] += 1
                
    # Calculate p-values using normal approximation (z-test)
    import math
    p_values = []
    results = {}
    
    for factor, stats in factor_stats.items():
        if stats["total"] >= 5:
            wr = stats["wins"] / stats["total"]
            # z-statistic against p0
            se = math.sqrt(p0 * (1 - p0) / stats["total"]) if p0 > 0 and p0 < 1 else 0
            if se > 0:
                z = (wr - p0) / se
                # Two-tailed p-value using math.erf
                p_val = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
            else:
                p_val = 1.0
                
            p_values.append((factor, p_val, wr, stats))
            
    # Benjamini-Hochberg FDR
    p_values.sort(key=lambda x: x[1])
    alpha = 0.10 # FDR threshold
    m = len(p_values)
    
    thresholds = [(i+1)/m * alpha for i in range(m)]
    
    # Find the largest k such that P_k <= threshold_k
    k_max = -1
    for i, (factor, p_val, wr, stats) in enumerate(p_values):
        if p_val <= thresholds[i]:
            k_max = i
            
    for i, (factor, p_val, wr, stats) in enumerate(p_values):
        is_significant = i <= k_max
        if is_significant:
            assessment = "STRONG_PREDICTOR" if wr > p0 else "NEGATIVE_PREDICTOR"
        else:
            assessment = "INSIGNIFICANT"
            
        results[factor] = {
            "win_rate": round(wr * 100, 1),
            "total": stats["total"],
            "wins": stats["wins"],
            "assessment": assessment,
            "p_value": round(p_val, 4),
            "significant": is_significant
        }
    
    # Sort by win rate for display
    results_sorted = dict(sorted(results.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True))
    
    return {
        "days_analyzed": days_back,
        "total_trades_analyzed": len(records),
        "overall_win_rate": round(p0 * 100, 1),
        "factor_effectiveness": results_sorted,
        "insight": f"Applied Benjamini-Hochberg FDR (alpha={alpha}). Factors marked SIGNIFICANT truly differ from overall baseline.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_confluence_calibration_status(session: AsyncSession) -> dict:
    """
    Cek kalibrasi threshold konfluensi (misal 7/14) berdasarkan tingkat keberhasilan skor secara riil.
    
    Returns: Rekomendasi apakah threshold perlu dinaikkan atau diturunkan.
    """
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
        .where(AssetAnalysis.confluence_score.is_not(None))
    )).all()
    
    if len(records) < 30:
        return {
            "status": "insufficient_data",
            "trades_needed": 30 - len(records),
            "message": "Need at least 30 closed trades with confluence scores to calibrate"
        }
    
    # Group by confluence score
    score_buckets = {}
    for record, analysis in records:
        if not analysis or analysis.confluence_score is None:
            continue
        score = analysis.confluence_score
        if score not in score_buckets:
            score_buckets[score] = {"wins": 0, "total": 0}
        score_buckets[score]["total"] += 1
        if (record.pnl_pct or 0) > 0:
            score_buckets[score]["wins"] += 1
    
    # Find the minimum score where win rate >= 40% (breakeven for 1:2 R:R)
    BREAKEVEN_WIN_RATE = 44  # ~1/(1+1.3) for the intraday-range strategy's min R:R
    
    calibration_data = {}
    for score in sorted(score_buckets.keys()):
        stats = score_buckets[score]
        wr = stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
        calibration_data[score] = {"win_rate": round(wr, 1), "trades": stats["total"]}
    
    # Find actual optimal threshold
    optimal_threshold = None
    for score in sorted(calibration_data.keys()):
        data = calibration_data[score]
        if data["trades"] >= 3 and data["win_rate"] >= BREAKEVEN_WIN_RATE:
            optimal_threshold = score
            break
    
    current_threshold = 7
    recommendation = "MAINTAIN"
    if optimal_threshold and optimal_threshold > current_threshold + 1:
        recommendation = f"INCREASE_TO_{optimal_threshold}"
    elif optimal_threshold and optimal_threshold < current_threshold - 1:
        recommendation = f"DECREASE_TO_{optimal_threshold}"
    
    return {
        "current_threshold": current_threshold,
        "optimal_threshold_from_data": optimal_threshold,
        "recommendation": recommendation,
        "calibration_data": calibration_data,
        "breakeven_win_rate_used": BREAKEVEN_WIN_RATE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_direction_accuracy_report(session: AsyncSession, days_back: int = 30) -> dict:
    """
    Menghitung akurasi prediksi arah market (ground truth), terlepas dari hit SL/TP.
    Berguna untuk mengukur apakah market understanding model sebenarnya bagus tapi eksekusinya salah.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    analyses = (await session.execute(
        select(AssetAnalysis)
        .where(AssetAnalysis.generated_at >= since)
        .where(AssetAnalysis.decision.in_(['buy', 'sell']))
        .where(AssetAnalysis.direction_correct_4h.is_not(None))
    )).scalars().all()
    
    if not analyses:
        return {'insufficient_data': True}
        
    by_symbol = {}
    total_correct_4h = 0
    total_correct_24h = 0
    total_evaluated_4h = 0
    total_evaluated_24h = 0
    brier_scores = []
    
    for a in analyses:
        sym = a.symbol
        if sym not in by_symbol:
            by_symbol[sym] = {"total": 0, "correct_4h": 0, "correct_24h": 0, "brier_sum": 0.0}
            
        by_symbol[sym]["total"] += 1
        total_evaluated_4h += 1
        
        # 4H evaluation
        if a.direction_correct_4h:
            by_symbol[sym]["correct_4h"] += 1
            total_correct_4h += 1
            outcome = 1.0
        else:
            outcome = 0.0
            
        # Brier Score calculation for confidence calibration: (confidence - outcome)^2
        conf = float(a.confidence or 0.5)
        brier = (conf - outcome) ** 2
        by_symbol[sym]["brier_sum"] += brier
        brier_scores.append(brier)
        
        # 24H evaluation
        if a.direction_correct_24h is not None:
            total_evaluated_24h += 1
            if a.direction_correct_24h:
                by_symbol[sym]["correct_24h"] += 1
                total_correct_24h += 1
                
    overall_accuracy_4h = round(total_correct_4h / total_evaluated_4h * 100, 1) if total_evaluated_4h > 0 else 0
    overall_accuracy_24h = round(total_correct_24h / total_evaluated_24h * 100, 1) if total_evaluated_24h > 0 else 0
    mean_brier = round(sum(brier_scores) / len(brier_scores), 3) if brier_scores else 0
    
    report = {
        "status": "success",
        "total_evaluated_4h": total_evaluated_4h,
        "total_evaluated_24h": total_evaluated_24h,
        "overall_accuracy_4h_pct": overall_accuracy_4h,
        "overall_accuracy_24h_pct": overall_accuracy_24h,
        "direction_accuracy_4h": overall_accuracy_4h,
        "direction_accuracy_24h": overall_accuracy_24h,
        "mean_brier_score": mean_brier,
        "brier_score": mean_brier,
        "by_symbol": {},
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    
    for sym, data in by_symbol.items():
        report["by_symbol"][sym] = {
            "total": data["total"],
            "accuracy_4h_pct": round(data["correct_4h"] / data["total"] * 100, 1) if data["total"] > 0 else 0,
            "brier_score": round(data["brier_sum"] / data["total"], 3) if data["total"] > 0 else 0
        }
        
    return report

async def detect_score_inflation(session: AsyncSession, days_back: int = 30) -> dict:
    """
    Deteksi apakah model secara sistematis meningkatkan/menurunkan
    confluence score dari waktu ke waktu (score drift).
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    analyses = (await session.execute(
        select(AssetAnalysis.generated_at, AssetAnalysis.confluence_score)
        .where(AssetAnalysis.generated_at >= since)
        .where(AssetAnalysis.confluence_score.is_not(None))
        .where(AssetAnalysis.decision.in_(['buy', 'sell']))
        .order_by(AssetAnalysis.generated_at.asc())
    )).all()
    
    if len(analyses) < 20:
        return {'insufficient_data': True}
    
    # Split in halves and compare averages
    mid = len(analyses) // 2
    first_half_avg = sum(a.confluence_score for a in analyses[:mid]) / mid
    second_half_avg = sum(a.confluence_score for a in analyses[mid:]) / (len(analyses) - mid)
    
    drift = second_half_avg - first_half_avg
    
    return {
        'first_half_avg_score': round(first_half_avg, 2),
        'second_half_avg_score': round(second_half_avg, 2),
        'drift': round(drift, 2),
        'alert': abs(drift) > 1.5,
        'direction': 'INFLATING' if drift > 1.5 else 'DEFLATING' if drift < -1.5 else 'STABLE',
        'interpretation': (
            'Score inflation detected — Model may be lowering standards' if drift > 1.5 else
            'Score deflation detected — Model may be overly conservative' if drift < -1.5 else
            'Score stable — no systematic drift detected'
        )
    }

async def compute_factor_weights_recommendation(session: AsyncSession, min_trades: int = 50) -> dict:
    """
    Berdasarkan historical paper trade data, hitung:
    - Apakah setiap factor benar-benar predictive?
    - Apakah ada factor yang lebih baik di-drop atau diberi bobot lebih tinggi?
    
    Output: recommendation untuk system prompt update
    """
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
    )).all()
    
    if len(records) < min_trades:
        return {
            "status": "insufficient_data",
            "trades_analyzed": len(records),
            "min_trades_required": min_trades,
            "message": f"Need at least {min_trades} closed paper trades to compute reliable recommendations"
        }
        
    effectiveness = await compute_factor_effectiveness(session, days_back=90)
    
    recommendations = {
        "drop_factors": [],
        "increase_weight": [],
        "decrease_weight": [],
        "keep_as_is": []
    }
    
    factor_data = effectiveness.get("factor_effectiveness", {})
    for factor, data in factor_data.items():
        assessment = data.get("assessment")
        win_rate = data.get("win_rate", 0)
        
        if assessment == "NEGATIVE_PREDICTOR" or win_rate < 35:
            recommendations["drop_factors"].append(factor)
        elif assessment == "STRONG_PREDICTOR" or win_rate >= 55:
            recommendations["increase_weight"].append(factor)
        elif assessment == "WEAK_PREDICTOR" or win_rate < 45:
            recommendations["decrease_weight"].append(factor)
        else:
            recommendations["keep_as_is"].append(factor)
            
    return {
        "status": "success",
        "trades_analyzed": len(records),
        "recommendations": recommendations,
        "factor_data": factor_data,
        "prompt_update_suggestion": "Review factors in 'drop_factors' and consider removing them from AI prompt instructions as they negatively correlate with success." if recommendations["drop_factors"] else "Current factor weights are performing adequately.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

async def compute_dynamic_factor_weights(session: AsyncSession) -> str:
    """
    Returns a dynamically generated prompt note overriding factor weights based on live win rates.
    """
    rec_data = await compute_factor_weights_recommendation(session)
    if rec_data.get("status") != "success":
        return ""
        
    recs = rec_data.get("recommendations", {})
    drop = recs.get("drop_factors", [])
    increase = recs.get("increase_weight", [])
    
    if not drop and not increase:
        return ""
        
    lines = ["\n[SYSTEM DIRECTIVE: DYNAMIC FACTOR WEIGHTS ACTIVE]"]
    lines.append("Based on recent real-world paper trading performance, adjust your confluence scoring as follows:")
    
    if increase:
        lines.append(f"- HEAVILY WEIGHT these factors (Proven >55% win rate): {', '.join(increase)}")
    if drop:
        lines.append(f"- IGNORE OR PENALIZE these factors (Proven <35% win rate / false signals): {', '.join(drop)}")
        
    lines.append("Do not stubbornly follow theoretical weights if they contradict this empirical data.\n")
    return "\n".join(lines)

async def compute_model_source_performance(session: AsyncSession, days_back: int=30) -> dict:
    """Kelompokkan trade paper yang closed berdasarkan decision_source
    (model LLM mana — primary/fallback — yang benar-benar menghasilkan
    keputusan) untuk mendeteksi apakah fallback chain menghasilkan
    keputusan berkualitas setara dengan model primer."""
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
    )).all()
    by_source: dict[str, dict] = {}
    for record, analysis in records:
        source = (analysis.decision_source if analysis and analysis.decision_source else 'unknown')
        bucket = by_source.setdefault(source, {'wins': 0, 'total': 0, 'pnl_sum': 0.0})
        bucket['total'] += 1
        bucket['pnl_sum'] += record.pnl_pct or 0.0
        if record.exit_reason == 'tp_hit':
            bucket['wins'] += 1
    out = {}
    for source, data in by_source.items():
        if data['total'] >= 5:
            out[source] = {'trades': data['total'], 'win_rate': round(data['wins'] / data['total'] * 100, 1), 'avg_pnl_pct': round(data['pnl_sum'] / data['total'], 3)}
    return {'days_analyzed': days_back, 'by_decision_source': out, 'generated_at': datetime.now(timezone.utc).isoformat()}
async def compute_and_persist_factor_point_overrides(session: AsyncSession, min_trades: int = 30) -> dict:
    """Ubah rekomendasi kualitatif (STRONG/WEAK/NEGATIVE) menjadi delta poin numerik
    yang benar-benar dipakai saat validasi konsistensi skor (bukan cuma teks di prompt)."""
    rec_data = await compute_factor_weights_recommendation(session, min_trades=min_trades)
    if rec_data.get('status') != 'success':
        return {'status': 'skipped'}
    recs = rec_data['recommendations']
    factor_data = rec_data.get('factor_data', {})
    overrides = {}
    for factor, data in factor_data.items():
        win_rate = data.get('win_rate', 0)
        total = data.get('total', data.get('total_appearances', 0))
        if total < 5: continue
        
        # Proporsional override
        if win_rate >= 65:
            overrides[factor] = 2
        elif win_rate >= 55:
            overrides[factor] = 1
        elif win_rate < 30:
            overrides[factor] = -2
        elif win_rate < 40:
            overrides[factor] = -1
    
    # drop_factors sudah ditangani terpisah lewat 'confluence_dropped_factors' (exclude total)

    cfg_key = 'dynamic_factor_point_overrides'
    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))).scalar_one_or_none()
    val = json.dumps({'overrides': overrides, 'computed_at': datetime.now(timezone.utc).isoformat()})
    if cfg:
        cfg.value = val
    else:
        session.add(SystemConfig(key=cfg_key, value=val))
    await session.commit()
    return {'status': 'applied', 'overrides': overrides}
