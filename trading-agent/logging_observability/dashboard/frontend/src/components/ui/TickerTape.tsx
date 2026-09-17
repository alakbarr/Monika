import React, { useState } from 'react';

export interface TickerItem {
  symbol: string;
  price: number;
  changePct: number;
}

interface TickerTapeProps {
  items: TickerItem[];
  style?: React.CSSProperties;
}

export const TickerTape: React.FC<TickerTapeProps> = ({ items, style }) => {
  const [isPaused, setIsPaused] = useState(false);
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (!items || items.length === 0) return null;

  return (
    <div
      className="ticker-tape-container"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        height: '30px',
        padding: '0 12px',
        borderBottom: '2px solid var(--color-rule)',
        background: 'var(--color-paper-raised)',
        fontSize: 'var(--text-xs)',
        fontFamily: 'var(--font-precision)',
        position: 'relative',
        overflow: 'hidden',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginRight: '14px',
          flexShrink: 0,
          zIndex: 2,
          background: 'var(--color-paper-raised)',
          paddingRight: '6px',
        }}
      >
        <span
          className="win-badge"
          style={{
            background: 'var(--color-win-yellow)',
            color: '#1C1917',
            padding: '1px 6px',
            fontSize: '10px',
            border: '1.5px solid var(--color-rule)',
            borderRadius: '2px',
          }}
        >
          LIVE FEED
        </span>
      </div>

      <div
        className={prefersReduced ? '' : 'ticker-scroll-track'}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '24px',
          whiteSpace: 'nowrap',
          animationPlayState: isPaused ? 'paused' : 'running',
          overflowX: prefersReduced ? 'auto' : 'visible',
        }}
      >
        {[...items, ...items].map((item, idx) => {
          const isUp = item.changePct >= 0;
          return (
            <span
              key={`${item.symbol}-${idx}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                color: 'var(--color-ink)',
              }}
            >
              <span style={{ fontWeight: 'var(--weight-bold)', color: 'var(--color-ink)' }}>
                {item.symbol}
              </span>
              <span className="tabular-nums" style={{ color: 'var(--color-ink-soft)' }}>
                {item.price.toFixed(item.price > 500 ? 2 : 4)}
              </span>
              <span
                className="tabular-nums"
                style={{
                  color: isUp ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                  fontWeight: 'var(--weight-bold)',
                }}
              >
                {isUp ? '▲' : '▼'} {Math.abs(item.changePct).toFixed(2)}%
              </span>
              <span style={{ color: 'var(--color-ink-soft)', marginLeft: '8px' }}>•</span>
            </span>
          );
        })}
      </div>
    </div>
  );
};
