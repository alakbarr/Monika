// ==============================================================================
// File: src/components/charts/candlestick/ChartHud.tsx
// Description: Real-time crosshair HUD and indicator telemetry overlay.
// ==============================================================================

import React from 'react';
import { formatPrice, type HudData } from './chartUtils';

interface ChartHudProps {
  activeHud: HudData | null;
  symbol: string;
  timeframe: string;
  palette: {
    upColor: string;
    downColor: string;
    [key: string]: any;
  };
  isLight: boolean;
}

export const ChartHud: React.FC<ChartHudProps> = ({
  activeHud,
  symbol,
  timeframe,
  palette,
  isLight,
}) => {
  if (!activeHud) return null;

  return (
    <div
      style={{
        position: 'absolute',
        top: '8px',
        left: '10px',
        zIndex: 10,
        pointerEvents: 'none',
        background: isLight ? 'rgba(255, 255, 255, 0.90)' : 'rgba(18, 19, 22, 0.90)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--color-border)',
        borderRadius: '2px',
        padding: '4px 8px',
        fontSize: '11px',
        fontFamily: 'var(--font-mono)',
        color: 'var(--color-ink)',
        boxShadow: '0 2px 6px rgba(0, 0, 0, 0.1)',
        display: 'flex',
        flexDirection: 'column',
        gap: '3px',
        maxWidth: 'calc(100% - 120px)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <strong style={{ color: 'var(--color-ink)' }}>{symbol}</strong>
        <span style={{ color: 'var(--color-ink-muted)' }}>{timeframe}</span>
        <span style={{ color: 'var(--color-ink-muted)' }}>{activeHud.timeStr}</span>
        <span className="tabular-nums">
          O: <strong>{formatPrice(activeHud.open, symbol)}</strong>
        </span>
        <span className="tabular-nums">
          H: <strong>{formatPrice(activeHud.high, symbol)}</strong>
        </span>
        <span className="tabular-nums">
          L: <strong>{formatPrice(activeHud.low, symbol)}</strong>
        </span>
        <span className="tabular-nums">
          C: <strong>{formatPrice(activeHud.close, symbol)}</strong>
        </span>
        {typeof activeHud.changePct === 'number' && (
          <span
            className="tabular-nums"
            style={{
              fontWeight: 700,
              color: activeHud.changePct >= 0 ? palette.upColor : palette.downColor,
            }}
          >
            {activeHud.changePct >= 0 ? '+' : ''}{activeHud.changePct.toFixed(2)}%
          </span>
        )}
        {typeof activeHud.volume === 'number' && activeHud.volume > 0 && (
          <span className="tabular-nums" style={{ color: 'var(--color-ink-muted)' }}>
            V: {activeHud.volume.toLocaleString()}
          </span>
        )}
      </div>
      {activeHud.indicators.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', fontSize: '10px' }}>
          {activeHud.indicators.slice(0, 7).map((ind, i) => (
            <span key={i} className="tabular-nums" style={{ color: ind.color || 'var(--color-ink-muted)' }}>
              <strong>{ind.name}:</strong> {typeof ind.value === 'number' ? formatPrice(ind.value, symbol) : String(ind.value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
