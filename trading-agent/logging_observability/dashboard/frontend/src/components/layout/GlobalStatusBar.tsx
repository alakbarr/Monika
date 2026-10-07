// ==============================================================================
// File: src/components/layout/GlobalStatusBar.tsx
// Description: Dashboard Taskbar Footer focused strictly on Live Trading Metrics
// ==============================================================================

import React, { useState, useEffect } from 'react';
import { useDashboardStore } from '../../store/dashboardStore';
import { fmt } from '../../lib/formatters';

export const GlobalStatusBar: React.FC = () => {
  const { wsConnected, health, overview, positions } = useDashboardStore();
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const openCount = positions.filter((p) => p.status === 'open').length;
  const isPaused = overview?.trading_paused ?? false;

  return (
    <footer className="status-bar-global" role="status" aria-label="Global Trading Status Bar">
      {/* Left side: System / Engine Trading Status */}
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

        <span className="status-bar-secondary" style={{ opacity: 0.4 }}>│</span>

        <div className="status-bar-secondary" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ color: 'var(--color-ink-soft)' }}>MODE:</span>
          <span style={{ fontWeight: 800, color: overview?.is_live ? 'var(--color-ledger-red)' : 'var(--color-text-warn)' }}>
            {overview?.is_live ? 'LIVE TRADING' : 'PAPER TRADING'}
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

      {/* Right side: Telemetry & UTC Time */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span
          style={{
            fontSize: '11px',
            padding: '1px 5px',
            borderRadius: '2px',
            border: '1px solid var(--color-rule)',
            background: wsConnected ? 'var(--color-profit-dim)' : 'var(--color-loss-dim)',
            color: wsConnected ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
            fontWeight: 800,
          }}
        >
          WS {wsConnected ? 'OK' : 'ERR'}
        </span>

        <span
          style={{
            fontSize: '11px',
            padding: '1px 5px',
            borderRadius: '2px',
            border: '1px solid var(--color-rule)',
            background: health?.mt5_connected ? 'var(--color-profit-dim)' : 'var(--color-loss-dim)',
            color: health?.mt5_connected ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
            fontWeight: 800,
          }}
        >
          MT5 {health?.mt5_connected ? 'OK' : 'OFF'}
        </span>

        <span className="tabular-nums" style={{ color: 'var(--color-ink)', fontWeight: 700 }}>
          {clock.toUTCString().slice(17, 25)} UTC
        </span>
      </div>
    </footer>
  );
};
