import React from 'react';

export type BadgeVariant =
  | 'active' | 'paused' | 'error' | 'neutral'
  | 'profit' | 'loss' | 'warn' | 'info'
  | 'buy' | 'sell' | 'wait' | 'avoid'
  | 'trading' | 'analysis' | 'risk' | 'system' | 'scraping';

const variantColorMap: Record<BadgeVariant, { color: string; dotColor: string; border: string; bg: string }> = {
  active:   { color: 'var(--color-gain)', dotColor: 'var(--color-gain)', border: 'var(--color-gain-border)', bg: 'transparent' },
  profit:   { color: 'var(--color-gain)', dotColor: 'var(--color-gain)', border: 'var(--color-gain-border)', bg: 'transparent' },
  buy:      { color: 'var(--color-gain)', dotColor: 'var(--color-gain)', border: 'var(--color-gain-border)', bg: 'transparent' },

  error:    { color: 'var(--color-loss)', dotColor: 'var(--color-loss)', border: 'var(--color-loss-border)', bg: 'transparent' },
  loss:     { color: 'var(--color-loss)', dotColor: 'var(--color-loss)', border: 'var(--color-loss-border)', bg: 'transparent' },
  sell:     { color: 'var(--color-loss)', dotColor: 'var(--color-loss)', border: 'var(--color-loss-border)', bg: 'transparent' },
  risk:     { color: 'var(--color-loss)', dotColor: 'var(--color-loss)', border: 'var(--color-loss-border)', bg: 'transparent' },

  paused:   { color: 'var(--color-warn)', dotColor: 'var(--color-warn)', border: 'var(--color-warn-border)', bg: 'transparent' },
  warn:     { color: 'var(--color-warn)', dotColor: 'var(--color-warn)', border: 'var(--color-warn-border)', bg: 'transparent' },
  trading:  { color: 'var(--color-warn)', dotColor: 'var(--color-warn)', border: 'var(--color-warn-border)', bg: 'transparent' },

  info:     { color: 'var(--color-ink)', dotColor: 'var(--color-ink)', border: 'var(--color-rule)', bg: 'transparent' },
  analysis: { color: 'var(--color-ink-secondary)', dotColor: 'var(--color-ink-secondary)', border: 'var(--color-rule)', bg: 'transparent' },
  neutral:  { color: 'var(--color-ink-muted)', dotColor: 'var(--color-ink-muted)', border: 'var(--color-rule)', bg: 'transparent' },
  wait:     { color: 'var(--color-ink-muted)', dotColor: 'var(--color-ink-muted)', border: 'var(--color-rule)', bg: 'transparent' },
  avoid:    { color: 'var(--color-ink-muted)', dotColor: 'var(--color-ink-muted)', border: 'var(--color-rule)', bg: 'transparent' },
  system:   { color: 'var(--color-ink-muted)', dotColor: 'var(--color-ink-muted)', border: 'var(--color-rule)', bg: 'transparent' },
  scraping: { color: 'var(--color-ink-muted)', dotColor: 'var(--color-ink-muted)', border: 'var(--color-rule)', bg: 'transparent' },
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  size?: 'sm' | 'md';
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'neutral', children, size = 'sm', dot = true }) => {
  const v = variantColorMap[variant] || variantColorMap.neutral;

  return (
    <span
      className="win-badge stamp-badge"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        height: size === 'sm' ? '22px' : '26px',
        boxSizing: 'border-box',
        padding: size === 'sm' ? '0 7px' : '0 9px',
        borderRadius: 'var(--radius-xs)',
        background: v.bg,
        color: v.color,
        border: `1px solid ${v.border}`,
        fontSize: 'var(--text-xs)',
        fontWeight: 600,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        lineHeight: 1,
      }}
    >
      {dot && (
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: 0,
            backgroundColor: v.dotColor,
            display: 'inline-block',
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  );
};
