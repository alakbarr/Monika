// ==============================================================================
// File: src/components/panels/RetroCockpitBar.tsx
// Description: Compact Retro Cockpit Instrument Cluster (Replaces bulky MetricCard row)
// ==============================================================================

import React from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { SegmentedProgressBar } from '../ui/SegmentedProgressBar';
import { fmt, vixSentiment } from '../../lib/formatters';

export const RetroCockpitBar: React.FC = () => {
  const { overview, paperStats, loading } = useDashboardStore();

  const dailyPnl = overview?.daily_pnl ?? 0;
  const isProfit = dailyPnl >= 0;
  const pnlSign = isProfit ? '+' : '';
  const winRate = paperStats?.win_rate_pct ?? 0;
  const totalTrades = paperStats?.total_trades ?? 0;
  const vix = overview?.vix ?? 16.5;
  const vixS = vixSentiment(vix);

  return (
    <div
      className="win-window ledger-card cockpit-bar"
      style={{
        background: 'var(--color-paper-raised)',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-card)',
        padding: '10px 14px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      {/* 1. Daily P&L & Drawdown Instrument */}
      <div className="cockpit-item">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            DAILY P&L
          </span>
          <span
            className="stamp-badge"
            style={{
              padding: '1px 6px',
              fontSize: '10px',
              background: isProfit ? 'var(--color-profit-dim)' : 'var(--color-loss-dim)',
              color: isProfit ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
              border: `1px solid ${isProfit ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)'}`,
            }}
          >
            {isProfit ? 'PROFIT' : 'LOSS'}
          </span>
        </div>
        <div
          className="tabular-nums"
          style={{
            fontSize: 'var(--text-title-md)',
            fontWeight: 800,
            color: isProfit ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
            lineHeight: 1.1,
          }}
        >
          {loading ? '...' : `${pnlSign}${fmt.usd(dailyPnl)}`}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }} className="tabular-nums">
          Max DD: {fmt.usd(overview?.current_drawdown ?? 0)}
        </div>
      </div>

      {/* 2. Win Rate Instrument (Segmented Pill Block Bar) */}
      <div className="cockpit-item" style={{ justifyContent: 'center' }}>
        <SegmentedProgressBar
          value={winRate}
          max={100}
          segments={10}
          variant="salmon"
          label="WIN RATE"
          valueDisplay={`${winRate.toFixed(1)}%`}
        />
        <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)', marginTop: '3px' }}>
          SOP Benchmark: ≥ 55.0% ({totalTrades} Trades)
        </div>
      </div>

      {/* 3. Edge Status & Expectancy Instrument */}
      <div className="cockpit-item">
        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          EDGE STATUS & R:R
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'nowrap' }}>
          <span
            style={{
              fontWeight: 800,
              fontSize: 'var(--text-body-sm)',
              color: paperStats?.has_positive_edge ? 'var(--color-ledger-green)' : 'var(--color-brass)',
              whiteSpace: 'nowrap',
            }}
          >
            {paperStats?.has_positive_edge ? '[ POSITIVE ]' : '[ NEUTRAL ]'}
          </span>
          <span style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink)', whiteSpace: 'nowrap' }} className="tabular-nums">
            {fmt.pct(paperStats?.expectancy_per_trade_pct, true)}
          </span>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }} className="tabular-nums">
          Avg R:R {paperStats?.avg_rr_achieved?.toFixed(2) ?? '1.50'}
        </div>
      </div>

      {/* 4. VIX Volatility Instrument */}
      <div className="cockpit-item">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            VIX VOLATILITY
          </span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10px',
              fontWeight: 800,
              padding: '1px 5px',
              borderRadius: '4px',
              background: 'var(--color-paper)',
              border: '1px solid var(--color-rule)',
              color: vixS.color,
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: vixS.color }} />
            {vixS.label.toUpperCase()}
          </span>
        </div>
        <div
          className="tabular-nums"
          style={{
            fontSize: 'var(--text-title-md)',
            fontWeight: 800,
            color: 'var(--color-ink)',
            lineHeight: 1.1,
          }}
        >
          {vix.toFixed(2)}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--color-ink-soft)' }}>
          S&P 500 Implied Vol Regime
        </div>
      </div>

      {/* 5. Open Positions & System State Instrument */}
      <div className="cockpit-item">
        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: 'var(--color-ink-soft)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          ACTIVE POSITIONS
        </span>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
          <span
            className="tabular-nums"
            style={{
              fontSize: 'var(--text-title-md)',
              fontWeight: 800,
              color: 'var(--color-win-blue)',
              lineHeight: 1.1,
            }}
          >
            {overview?.open_positions_count ?? 0}
          </span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)' }}>
            OPEN POSITIONS
          </span>
        </div>
        <div style={{ fontSize: '11px', color: overview?.trading_paused ? 'var(--color-ledger-red)' : 'var(--color-ledger-green)', fontWeight: 'bold' }}>
          {overview?.trading_paused ? '● PAUSED' : '● ACTIVE'}
        </div>
      </div>
    </div>
  );
};
