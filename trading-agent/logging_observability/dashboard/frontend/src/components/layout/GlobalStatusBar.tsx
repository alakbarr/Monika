// ==============================================================================
// File: src/components/layout/GlobalStatusBar.tsx
// Description: Dashboard Taskbar Footer focused strictly on Live Trading Metrics
// ==============================================================================

import React from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';

export const GlobalStatusBar: React.FC = () => {
  const { overview, positions } = useDashboardStore();

  const openCount = positions.filter((p) => p.status === 'open').length;
  const isPaused = overview?.trading_paused ?? false;

  return (
    <footer className="status-bar-global" role="status" aria-label="Global Trading Status Bar">
      {/* Left side: System / Engine Trading Status & Open Positions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              display: 'inline-block',
              width: 8,
              height: 8,
              borderRadius: '2px',
              background: isPaused ? 'var(--color-win-coral)' : 'var(--color-ledger-green)',
            }}
          />
          <span style={{ fontWeight: 800, color: 'var(--color-ink)' }}>
            {isPaused ? '[ PAUSED ]' : '[ ENGINE ONLINE ]'}
          </span>
        </div>

        <span style={{ opacity: 0.4 }}>│</span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ color: 'var(--color-ink-soft)' }}>POSITIONS:</span>
          <span className="tabular-nums" style={{ fontWeight: 800, color: 'var(--color-ink)' }}>
            {openCount}
          </span>
        </div>
      </div>

      {/* Center: System Telemetry & Heartbeat */}
      <div className="status-bar-secondary" style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: 'var(--text-xs)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ color: 'var(--color-ink-soft)' }}>HEARTBEAT:</span>
          <span className="tabular-nums" style={{ fontWeight: 800, color: 'var(--color-ink)' }}>
            {overview?.timestamp ? fmt.time(overview.timestamp) : 'SYNCING...'}
          </span>
        </div>
        {overview?.vix && (
          <>
            <span style={{ opacity: 0.4 }}>│</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--color-ink-soft)' }}>VIX REGIME:</span>
              <span className="tabular-nums" style={{ fontWeight: 800, color: 'var(--color-brass)' }}>
                {overview.vix.toFixed(1)}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Right side: Session Financial Snapshot */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: 'var(--text-xs)' }}>
        {overview?.daily_pnl !== undefined && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ color: 'var(--color-ink-soft)' }}>SESSION P&L:</span>
            <span
              className="tabular-nums"
              style={{
                fontWeight: 800,
                color: (overview.daily_pnl || 0) >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
              }}
            >
              {fmt.usd(overview.daily_pnl || 0)}
            </span>
          </div>
        )}
        {overview?.drawdown_pct !== undefined && overview?.drawdown_pct !== null && (
          <>
            <span style={{ opacity: 0.4 }}>│</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--color-ink-soft)' }}>DD:</span>
              <span
                className="tabular-nums"
                style={{
                  fontWeight: 800,
                  color: overview.drawdown_pct > 0 ? 'var(--color-ledger-red)' : 'var(--color-ink)',
                }}
              >
                {overview.drawdown_pct.toFixed(1)}%
              </span>
            </div>
          </>
        )}
      </div>
    </footer>
  );
};
