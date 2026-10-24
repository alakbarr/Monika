import React from 'react';

interface SegmentedProgressBarProps {
  value: number;
  max?: number;
  segments?: number;
  label?: string;
  valueDisplay?: string;
  variant?: 'salmon' | 'yellow' | 'blue' | 'green';
  style?: React.CSSProperties;
}

const colorMap = {
  salmon: 'var(--color-loss)',
  yellow: 'var(--color-warn)',
  blue: 'var(--color-ink)',
  green: 'var(--color-gain)',
};

export const SegmentedProgressBar: React.FC<SegmentedProgressBarProps> = ({
  value,
  max = 100,
  segments = 12,
  label,
  valueDisplay,
  variant = 'green',
  style,
}) => {
  const clamped = Math.max(0, Math.min(max, value));
  const ratio = clamped / (max || 1);
  const activeSegments = Math.round(ratio * segments);
  const fillColor = colorMap[variant] || colorMap.green;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontFamily: 'var(--font-mono)', ...style }}>
      {(label || valueDisplay) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-xs)' }}>
          {label && (
            <span style={{ color: 'var(--color-ink-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
              {label}
            </span>
          )}
          {valueDisplay && (
            <span style={{ color: 'var(--color-ink)', fontWeight: 600 }} className="tabular-nums">
              {valueDisplay}
            </span>
          )}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          gap: '3px',
          height: '8px',
          alignItems: 'center',
        }}
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={max}
      >
        {Array.from({ length: segments }).map((_, i) => {
          const isActive = i < activeSegments;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                height: '100%',
                background: isActive ? fillColor : 'var(--color-well)',
                border: '1px solid var(--color-rule)',
                transition: 'background-color 150ms ease-out',
              }}
            />
          );
        })}
      </div>
    </div>
  );
};
