import React from 'react';

interface AnalogDialProps {
  value: number;
  min?: number;
  max?: number;
  label?: string;
  unit?: string;
  size?: number;
  dangerZone?: number;
  style?: React.CSSProperties;
}

export const AnalogDial: React.FC<AnalogDialProps> = ({
  value,
  min = 0,
  max = 100,
  label,
  unit = '%',
  size = 140,
  dangerZone,
  style,
}) => {
  const clamped = Math.max(min, Math.min(max, value));
  const ratio = (clamped - min) / (max - min || 1);

  const startAngle = 135;
  const endAngle = 405;
  const currentAngle = startAngle + ratio * (endAngle - startAngle);

  const cx = 50;
  const cy = 52;
  const r = 36;

  const polarToCartesian = (centerX: number, centerY: number, radius: number, angleInDegrees: number) => {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
    return {
      x: centerX + radius * Math.cos(angleInRadians),
      y: centerY + radius * Math.sin(angleInRadians),
    };
  };

  const needleTip = polarToCartesian(cx, cy, r - 4, currentAngle);
  const pStart = polarToCartesian(cx, cy, r, startAngle);
  const pEnd = polarToCartesian(cx, cy, r, endAngle);

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => {
    const angle = startAngle + t * (endAngle - startAngle);
    const outer = polarToCartesian(cx, cy, r + 2, angle);
    const inner = polarToCartesian(cx, cy, r - 2, angle);
    return { outer, inner, angle };
  });

  return (
    <div
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'center',
        fontFamily: 'var(--font-precision)',
        ...style,
      }}
    >
      <svg
        width={size}
        height={size * 0.85}
        viewBox="0 0 100 85"
        style={{ overflow: 'visible' }}
      >
        {/* Outer casing retro bezel ring */}
        <circle
          cx={cx}
          cy={cy}
          r={r + 6}
          fill="none"
          stroke="var(--color-rule)"
          strokeWidth="2"
        />

        {/* Dial Face */}
        <circle
          cx={cx}
          cy={cy}
          r={r + 4}
          fill="var(--color-paper-raised)"
          stroke="var(--color-rule)"
          strokeWidth="1.5"
        />

        {/* Dial Track Arc */}
        <path
          d={`M ${pStart.x} ${pStart.y} A ${r} ${r} 0 1 1 ${pEnd.x} ${pEnd.y}`}
          fill="none"
          stroke="var(--color-paper)"
          strokeWidth="4"
          strokeLinecap="round"
        />

        {/* Danger zone arc if specified */}
        {dangerZone !== undefined && (
          <path
            d={`M ${polarToCartesian(cx, cy, r, startAngle + (dangerZone / max) * (endAngle - startAngle)).x} ${
              polarToCartesian(cx, cy, r, startAngle + (dangerZone / max) * (endAngle - startAngle)).y
            } A ${r} ${r} 0 0 1 ${pEnd.x} ${pEnd.y}`}
            fill="none"
            stroke="var(--color-win-coral)"
            strokeWidth="4"
            strokeLinecap="round"
          />
        )}

        {/* Scale Ticks */}
        {ticks.map((t, idx) => (
          <line
            key={idx}
            x1={t.inner.x}
            y1={t.inner.y}
            x2={t.outer.x}
            y2={t.outer.y}
            stroke="var(--color-rule)"
            strokeWidth="1.5"
          />
        ))}

        {/* Retro Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleTip.x}
          y2={needleTip.y}
          stroke="var(--color-win-salmon)"
          strokeWidth="2.5"
          strokeLinecap="round"
          style={{ transition: 'all 200ms ease-out' }}
        />

        {/* Needle Center Hub */}
        <circle cx={cx} cy={cy} r="4.5" fill="var(--color-win-yellow)" stroke="var(--color-rule)" strokeWidth="1.5" />
        <circle cx={cx} cy={cy} r="1.5" fill="var(--color-rule)" />
      </svg>

      {/* Readout Value */}
      <div style={{ textAlign: 'center', marginTop: '-12px' }}>
        <span
          className="tabular-nums"
          style={{
            fontSize: 'var(--text-title-md)',
            fontWeight: 'var(--weight-bold)',
            color: 'var(--color-ink)',
          }}
        >
          {typeof value === 'number' ? value.toFixed(1) : value}
        </span>
        {unit && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-soft)', marginLeft: '2px' }}>
            {unit}
          </span>
        )}
      </div>

      {label && (
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink-soft)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            marginTop: '2px',
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
};
