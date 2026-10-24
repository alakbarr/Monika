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
    <section
      className="editorial-section swiss-crosshair"
      style={{
        background: 'var(--color-surface)',
        borderTop: accent ? '2px solid var(--color-ink)' : '1px solid var(--color-border)',
        borderBottom: '1px solid var(--color-border)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="editorial-kicker">{title}</span>
        {icon && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '20px',
              height: '20px',
              color: 'var(--color-ink-muted)',
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
            fontSize: '26px',
            fontWeight: 600,
            fontFamily: 'var(--font-mono)',
            color: 'var(--color-ink)',
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
            fontSize: '11px',
            color: 'var(--color-ink-soft)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {trend && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                color: trend.value >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
                fontWeight: 600,
              }}
            >
              {trend.value >= 0 ? '▲' : '▼'} {Math.abs(trend.value).toFixed(2)}%
            </span>
          )}
          {subtitle && <span>{subtitle}</span>}
        </div>
      )}
    </section>
  );
};
