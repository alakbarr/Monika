// ==============================================================================
// File: src/components/ui/SegmentedProgressBar.tsx
// Description: Retro 90s Segmented Pill Block Progress Bar (vintage-ui.jpg)
// ==============================================================================

import React from 'react';

interface SegmentedProgressBarProps {
  value: number; // 0 to 100
  max?: number;
  segments?: number;
  label?: string;
  valueDisplay?: string;
  variant?: 'salmon' | 'yellow' | 'blue' | 'green';
  style?: React.CSSProperties;
}

const colorMap = {
  salmon: '#E86C53',
  yellow: '#F5BD38',
  blue: '#3BA4C4',
  green: '#48A9A6',
};

export const SegmentedProgressBar: React.FC<SegmentedProgressBarProps> = ({
  value,
  max = 100,
  segments = 12,
  label,
  valueDisplay,
  variant = 'salmon',
  style,
}) => {
  const clamped = Math.max(0, Math.min(max, value));
  const ratio = clamped / (max || 1);
  const activeSegments = Math.round(ratio * segments);
  const fillColor = colorMap[variant] || colorMap.salmon;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontFamily: 'var(--font-precision)', ...style }}>
      {(label || valueDisplay) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-xs)', fontWeight: 'bold' }}>
          {label && <span style={{ color: 'var(--color-ink-soft)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</span>}
          {valueDisplay && <span style={{ color: 'var(--color-ink)' }} className="tabular-nums">{valueDisplay}</span>}
        </div>
      )}

      {/* Retro Outer Capsule Track */}
      <div
        style={{
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          borderRadius: '8px',
          padding: '3px 4px',
          display: 'flex',
          gap: '3px',
          boxShadow: 'inset 1px 1px 0 rgba(0,0,0,0.15)',
          height: '24px',
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
                borderRadius: '4px',
                background: isActive ? fillColor : 'transparent',
                border: isActive ? '1px solid var(--color-rule)' : '1px dashed var(--color-rule)',
                opacity: isActive ? 1 : 0.25,
                transition: 'all 0.15s ease-out',
                boxShadow: isActive ? '1px 1px 0 rgba(0,0,0,0.1)' : 'none',
              }}
            />
          );
        })}
      </div>
    </div>
  );
};
