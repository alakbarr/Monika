import React from 'react';
import { Skeleton } from './Skeleton';

interface MetricCardProps {
  title: string;
  value: React.ReactNode;
  subtitle?: string;
  trend?: { value: number; label?: string };
  icon?: React.ReactNode;
  accent?: boolean;
  loading?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  trend,
  icon,
  accent = false,
  loading = false,
}) => {
  return (
    <div
      className="win-window ledger-card"
      style={{
        background: 'var(--color-paper-raised)',
        border: '2px solid var(--color-rule)',
        borderLeft: accent ? '5px solid var(--color-win-yellow)' : '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-card)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--weight-bold)',
            color: 'var(--color-ink-soft)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontFamily: 'var(--font-precision)',
          }}
        >
          {title}
        </span>
        {icon && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '24px',
              height: '24px',
              color: accent ? 'var(--color-brass)' : 'var(--color-ink-soft)',
            }}
          >
            {icon}
          </span>
        )}
      </div>

      {loading ? (
        <Skeleton height="32px" width="70%" />
      ) : (
        <div
          className="tabular-nums"
          style={{
            fontSize: 'var(--text-display-sm)',
            fontWeight: 'var(--weight-bold)',
            fontFamily: 'var(--font-precision)',
            color: accent ? 'var(--color-brass)' : 'var(--color-ink)',
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
          }}
        >
          {value}
        </div>
      )}

      {(subtitle || trend) && !loading && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink-soft)',
            fontFamily: 'var(--font-precision)',
          }}
        >
          {trend && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                color: trend.value >= 0 ? 'var(--color-ledger-green)' : 'var(--color-ledger-red)',
                fontWeight: 'var(--weight-bold)',
                fontFamily: 'var(--font-precision)',
              }}
            >
              {trend.value >= 0 ? '▲' : '▼'} {Math.abs(trend.value).toFixed(2)}%
            </span>
          )}
          {subtitle && <span>{subtitle}</span>}
        </div>
      )}
    </div>
  );
};
