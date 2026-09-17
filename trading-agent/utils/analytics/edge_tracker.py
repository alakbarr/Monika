# ==============================================================================
# File: utils/edge_tracker.py
# ==============================================================================

"""
Edge Tracker — Statistical significance testing untuk memantau apakah sistem 
memiliki positive edge atau sedang berjalan secara random/negative.
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PaperTradeRecord, SystemConfig
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

logger = logging.getLogger('TradingAgent.EdgeTracker')

def binomial_confidence_interval(wins: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval untuk win rate confidence interval."""
    if total == 0:
        return (0.0, 1.0)
    
    z = 1.96 if confidence == 0.95 else 1.645  # z-score
    p_hat = wins / total
    
    denominator = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denominator
    margin = (z * math.sqrt(p_hat * (1 - p_hat) / total + z**2 / (4 * total**2))) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


__all__ = ['binomial_confidence_interval', 'is_trade_win', 'compute_edge_status']


def is_trade_win(r) -> bool:
    """Evaluasi apakah record trade adalah WIN (berdasarkan PnL positif atau exit reason yang menguntungkan).
    Mendukung objek ORM (PaperTradeRecord), class instance, dan mapping/dict.
    """
    if r is None:
        return False

    # 1. Ekstraksi nilai pnl_pct, realized_pnl, exit_reason
    if isinstance(r, dict):
        pnl = r.get('pnl_pct')
        pnl_usd = r.get('realized_pnl')
        exit_reason = r.get('exit_reason', '')
    else:
        pnl = getattr(r, 'pnl_pct', None)
        pnl_usd = getattr(r, 'realized_pnl', None)
        exit_reason = getattr(r, 'exit_reason', '')

    # 2. Cek pnl_pct (jika bukan nol & bukan NaN)
    if isinstance(pnl, (int, float)) and not math.isnan(pnl) and pnl != 0:
        return pnl > 0

    # 3. Cek realized_pnl (jika bukan nol & bukan NaN)
    if isinstance(pnl_usd, (int, float)) and not math.isnan(pnl_usd) and pnl_usd != 0:
        return pnl_usd > 0

    # 4. Jika pnl bernilai 0.0 atau None, fallback ke exit_reason
    if isinstance(exit_reason, str):
        return exit_reason in ('tp_hit', 'partial_tp')

    return False


async def compute_edge_status(session: AsyncSession) -> dict:
    """
    Compute apakah sistem memiliki statistical edge.
    Return status: 'positive_edge', 'uncertain', 'no_edge', 'insufficient_data'
    """
    # Ambil semua closed paper trades
    records = (await session.execute(
        select(PaperTradeRecord)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
        .order_by(PaperTradeRecord.closed_at.desc())
    )).scalars().all()
    
    MIN_TRADES_FOR_SIGNIFICANCE = 30
    
    if len(records) < MIN_TRADES_FOR_SIGNIFICANCE:
        return {
            'status': 'insufficient_data',
            'trades': len(records),
            'min_required': MIN_TRADES_FOR_SIGNIFICANCE,
            'message': f'Need {MIN_TRADES_FOR_SIGNIFICANCE - len(records)} more trades for statistical significance'
        }
    
    # Compute statistics
    wins = sum(1 for r in records if is_trade_win(r))
    total = len(records)
    win_rate = wins / total
    
    # Wilson confidence interval
    ci_lower, ci_upper = binomial_confidence_interval(wins, total)
    
    # Dynamic breakeven win rate calculation from actual historical R:R.
    # Formula: Breakeven WR = Risk / (Risk + Reward) = 1 / (1 + avg_RR)
    FALLBACK_BREAKEVEN_WIN_RATE = 0.43  # Corresponds to ~1.3 min R:R (1/(1+1.3)) default fallback
    
    try:
        # Hitung rata-rata R:R dari pips actual (TP pips / SL pips per trade)
        # Gunakan entry_price, sl, tp dari record jika tersedia
        rr_values = []
        for r in records:
            try:
                sl_val = getattr(r, 'stop_loss', None) or getattr(r, 'sl', None)
                tp_val = getattr(r, 'take_profit', None) or getattr(r, 'tp', None)
                if (r.entry_price and sl_val and tp_val and 
                    r.entry_price > 0 and sl_val > 0 and tp_val > 0):
                    sl_dist = abs(r.entry_price - sl_val)
                    tp_dist = abs(r.entry_price - tp_val)
                    if sl_dist > 0 and tp_dist > 0:
                        rr_values.append(tp_dist / sl_dist)
            except (TypeError, ZeroDivisionError, AttributeError):
                continue
        
        if len(rr_values) >= 10:  # Min 10 trades untuk kalkulasi R:R yang reliable
            avg_rr = sum(rr_values) / len(rr_values)
            # Clamp R:R ke range masuk akal (1:0.5 - 1:5)
            avg_rr = max(0.5, min(5.0, avg_rr))
            BREAKEVEN_WIN_RATE = 1.0 / (1.0 + avg_rr)
            logger.debug(
                f'[EdgeTracker] Dynamic breakeven WR: avg_RR={avg_rr:.2f} → '
                f'breakeven={BREAKEVEN_WIN_RATE*100:.1f}% (from {len(rr_values)} trades)'
            )
        else:
            BREAKEVEN_WIN_RATE = FALLBACK_BREAKEVEN_WIN_RATE
            logger.debug(
                f'[EdgeTracker] Using fallback breakeven WR {BREAKEVEN_WIN_RATE*100:.1f}% '
                f'(only {len(rr_values)} trades have R:R data, need >= 10)'
            )
    except Exception as rr_err:
        BREAKEVEN_WIN_RATE = FALLBACK_BREAKEVEN_WIN_RATE
        logger.debug(f'[EdgeTracker] R:R calculation failed, using fallback: {rr_err}')
    
    # P-value test: apakah win rate secara signifikan > breakeven?
    # Gunakan simple z-test
    expected_wins_null = total * BREAKEVEN_WIN_RATE
    z_score = (wins - expected_wins_null) / math.sqrt(total * BREAKEVEN_WIN_RATE * (1 - BREAKEVEN_WIN_RATE))
    
    # Z > 1.645 = p < 0.05 (one-tailed, significant positive edge)
    # Z < 0 = edge negative
    # 0 <= Z <= 1.645 = uncertain
    
    # Last 20 trades (recent performance)
    recent_20 = records[:20]
    recent_wins = sum(1 for r in recent_20 if is_trade_win(r))
    recent_wr = recent_wins / len(recent_20) if recent_20 else 0
    
    if z_score > 1.645 and win_rate > BREAKEVEN_WIN_RATE:
        status = 'positive_edge'
        action = 'System has statistical edge. Continue current approach.'
    elif z_score < 0 or win_rate < BREAKEVEN_WIN_RATE - 0.05:
        status = 'no_edge'
        action = (
            'System shows NO statistical edge. '
            'Review: (1) confluence threshold too low? '
            '(2) SL placement systematically wrong? '
            '(3) Entry timing off (chasing)? '
            'Consider pausing live trading until reviewed.'
        )
    else:
        status = 'uncertain'
        action = 'Edge uncertain. Maintain conservative position sizing.'
    
    result = {
        'status': status,
        'total_trades': total,
        'win_rate': round(win_rate * 100, 1),
        'ci_lower': round(ci_lower * 100, 1),
        'ci_upper': round(ci_upper * 100, 1),
        'z_score': round(z_score, 2),
        'recent_20_win_rate': round(recent_wr * 100, 1),
        'breakeven_win_rate_pct': round(BREAKEVEN_WIN_RATE * 100, 1),
        'action': action,
        'computed_at': datetime.now(timezone.utc).isoformat()
    }
    
    # Automatic trading pause enforcement when no edge is detected with significant negative z-score.
    # Threshold: z < -1.0 indicates statistically significant negative edge.
    AUTO_PAUSE_Z_THRESHOLD = -1.0
    if status == 'no_edge' and z_score < AUTO_PAUSE_Z_THRESHOLD:
        try:
            from database.models import SystemConfig
            from sqlalchemy import update
            
            # Cek apakah trading sudah di-pause sebelumnya karena alasan ini
            existing_pause = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == 'trading_paused')
            )).scalar_one_or_none()
            
            pause_reason = (
                f'Auto-paused by EdgeTracker: z={z_score:.2f}, '
                f'WR={win_rate*100:.1f}% < {BREAKEVEN_WIN_RATE*100:.1f}% breakeven '
                f'over {total} trades. Resume after strategy review.'
            )
            
            if existing_pause and existing_pause.value == 'true':
                # Sudah paused — tidak perlu update, log saja
                logger.info('[EdgeTracker] Trading already paused. No_edge condition persists.')
            else:
                # Set pause
                if existing_pause:
                    existing_pause.value = 'true'
                    existing_pause.description = pause_reason
                else:
                    session.add(SystemConfig(
                        key='trading_paused',
                        value=f'true:{pause_reason[:200]}'
                    ))
                await session.commit()
                
                logger.critical(
                    f'[EdgeTracker] AUTO-PAUSE ACTIVATED: z={z_score:.2f}, '
                    f'WR={win_rate*100:.1f}%. System has no statistical edge.'
                )
                
                # Kirim alert kritis via Telegram
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_critical(
                        f'🚨 <b>EDGE TRACKER — AUTO PAUSE AKTIF</b>\n\n'
                        f'Win Rate: <b>{win_rate*100:.1f}%</b> '
                        f'(breakeven: {BREAKEVEN_WIN_RATE*100:.1f}%)\n'
                        f'Z-Score: <b>{z_score:.2f}</b> (threshold: {AUTO_PAUSE_Z_THRESHOLD})\n'
                        f'Jumlah Trade: {total}\n\n'
                        f'⚠️ Trading dihentikan otomatis. '
                        f'Review strategi lalu gunakan /resume untuk melanjutkan.'
                    )
                except Exception as notify_err:
                    logger.error(f'EdgeTracker: Failed to send Telegram alert: {notify_err}')
                
                result['auto_paused'] = True
                result['action'] = pause_reason
                
        except Exception as pause_err:
            logger.error(f'EdgeTracker: Failed to auto-pause trading: {pause_err}')
    
    return result

