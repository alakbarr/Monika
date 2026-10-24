import React from 'react';

export interface VuMeterProps {
  label: string;
  value: number;
  min?: number;
  max?: number;
  unit?: string;
  warnThreshold?: number;
  critThreshold?: number;
  width?: number;
  height?: number;
  variant?: 'green' | 'amber' | 'red';
}

/**
 * Swiss Precision Linear Threshold Gauge (replaces retro analog needle meter)
 */
export const VuMeter: React.FC<VuMeterProps> = ({
  label,
  value,
  min = 0,
  max = 100,
  unit = '%',
  warnThreshold = 70,
  critThreshold = 85,
  width = 210,
}) => {
  const clamped = Math.max(min, Math.min(max, value));
  const ratio = Math.min(1, Math.max(0, (clamped - min) / (max - min || 1)));
  const warnRatio = Math.min(1, Math.max(0, (warnThreshold - min) / (max - min || 1)));
  const critRatio = Math.min(1, Math.max(0, (critThreshold - min) / (max - min || 1)));

  const isCrit = clamped >= critThreshold;
  const isWarn = clamped >= warnThreshold && !isCrit;
  const statusColor = isCrit
    ? 'var(--color-loss)'
    : isWarn
    ? 'var(--color-warn)'
    : 'var(--color-gain)';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '14px 16px',
        border: '1px solid var(--color-rule)',
        background: 'var(--color-canvas)',
        fontFamily: 'var(--font-mono)',
        minWidth: width,
        flex: '1 1 200px',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '8px' }}>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            color: 'var(--color-ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          {label}
        </span>
        <span
          className="tabular-nums"
          style={{
            fontSize: 'var(--text-title-md)',
            fontWeight: 700,
            color: statusColor,
          }}
        >
          {typeof value === 'number' ? value.toFixed(1) : '0.0'}
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)', marginLeft: '2px' }}>
            {unit}
          </span>
        </span>
      </div>

      {/* Linear Track with Threshold Hairlines */}
      <div
        style={{
          position: 'relative',
          height: '6px',
          width: '100%',
          background: 'var(--color-well)',
          border: '1px solid var(--color-rule)',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${ratio * 100}%`,
            background: statusColor,
            transition: 'width 200ms ease-out',
          }}
        />
        {/* Warn marker */}
        <div
          title={`Warning Threshold: ${warnThreshold}${unit}`}
          style={{
            position: 'absolute',
            top: -2,
            bottom: -2,
            left: `${warnRatio * 100}%`,
            width: '1px',
            background: 'var(--color-warn)',
          }}
        />
        {/* Critical marker */}
        <div
          title={`Critical Limit: ${critThreshold}${unit}`}
          style={{
            position: 'absolute',
            top: -2,
            bottom: -2,
            left: `${critRatio * 100}%`,
            width: '1px',
            background: 'var(--color-loss)',
          }}
        />
      </div>

      <div
        className="tabular-nums"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 'var(--text-xs)',
          color: 'var(--color-ink-muted)',
        }}
      >
        <span>{min}{unit}</span>
        <span>WARN {warnThreshold}{unit}</span>
        <span>MAX {max}{unit}</span>
      </div>
    </div>
  );
};
