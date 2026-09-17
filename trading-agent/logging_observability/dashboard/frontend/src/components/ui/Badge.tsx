import React from 'react';

export type BadgeVariant =
  | 'active' | 'paused' | 'error' | 'neutral'
  | 'profit' | 'loss' | 'warn' | 'info'
  | 'buy' | 'sell' | 'wait' | 'avoid'
  | 'trading' | 'analysis' | 'risk' | 'system' | 'scraping';

const variantColorMap: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  active:   { color: '#1C1917', bg: 'var(--color-win-green)', border: 'var(--color-rule)' },
  paused:   { color: '#1C1917', bg: 'var(--color-win-yellow)', border: 'var(--color-rule)' },
  error:    { color: '#FAF7F2', bg: 'var(--color-win-coral)', border: 'var(--color-rule)' },
  neutral:  { color: 'var(--color-ink-soft)', bg: 'var(--color-paper-raised)', border: 'var(--color-rule)' },
  profit:   { color: '#1C1917', bg: 'var(--color-win-green)', border: 'var(--color-rule)' },
  loss:     { color: '#FAF7F2', bg: 'var(--color-win-coral)', border: 'var(--color-rule)' },
  warn:     { color: '#1C1917', bg: 'var(--color-win-yellow)', border: 'var(--color-rule)' },
  info:     { color: '#1C1917', bg: 'var(--color-win-blue)', border: 'var(--color-rule)' },
  buy:      { color: '#1C1917', bg: 'var(--color-win-green)', border: 'var(--color-rule)' },
  sell:     { color: '#FAF7F2', bg: 'var(--color-win-coral)', border: 'var(--color-rule)' },
  wait:     { color: 'var(--color-ink-soft)', bg: 'var(--color-paper-raised)', border: 'var(--color-rule)' },
  avoid:    { color: 'var(--color-ink-soft)', bg: 'var(--color-paper-raised)', border: 'var(--color-rule)' },
  trading:  { color: '#1C1917', bg: 'var(--color-win-yellow)', border: 'var(--color-rule)' },
  analysis: { color: '#1C1917', bg: 'var(--color-win-salmon)', border: 'var(--color-rule)' },
  risk:     { color: '#FAF7F2', bg: 'var(--color-win-coral)', border: 'var(--color-rule)' },
  system:   { color: 'var(--color-ink-soft)', bg: 'var(--color-paper-raised)', border: 'var(--color-rule)' },
  scraping: { color: 'var(--color-ink-soft)', bg: 'var(--color-paper-raised)', border: 'var(--color-rule)' },
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  size?: 'sm' | 'md';
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'neutral', children, size = 'sm', dot = false }) => {
  const v = variantColorMap[variant] || variantColorMap.neutral;

  return (
    <span
      className="win-badge stamp-badge"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        height: size === 'sm' ? '26px' : '30px',
        boxSizing: 'border-box',
        padding: size === 'sm' ? '0 8px' : '0 10px',
        borderRadius: 'var(--radius-sm)',
        background: v.bg,
        color: v.color,
        border: `1.5px solid ${v.border}`,
        fontSize: size === 'sm' ? 'var(--text-xs)' : 'var(--text-body-sm)',
        fontWeight: 'var(--weight-bold)',
        fontFamily: 'var(--font-precision)',
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        lineHeight: 1,
        boxShadow: '1px 1px 0 var(--color-rule)',
      }}
    >
      {dot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 1,
            backgroundColor: v.color,
            display: 'inline-block',
            border: '1px solid var(--color-rule)',
          }}
        />
      )}
      {children}
    </span>
  );
};
