import React from 'react';

interface RetroVuMeterProps {
  label: string;
  value: number; // current value
  min?: number;
  max?: number;
  unit?: string;
  warnThreshold?: number;
  critThreshold?: number;
  width?: number;
  height?: number;
  variant?: 'green' | 'amber' | 'red';
}

export const RetroVuMeter: React.FC<RetroVuMeterProps> = ({
  label,
  value,
  min = 0,
  max = 100,
  unit = '%',
  warnThreshold = 70,
  critThreshold = 85,
  width = 160,
  height = 95,
}) => {
  // Clamp value
  const clamped = Math.max(min, Math.min(max, value));
  const ratio = (clamped - min) / (max - min || 1);

  // Meter needle sweep: from -50 degrees (left) to +50 degrees (right)
  const startAngle = -50;
  const endAngle = 50;
  const angle = startAngle + ratio * (endAngle - startAngle);

  // Status color
  const isCrit = clamped >= critThreshold;
  const isWarn = clamped >= warnThreshold && !isCrit;
  const statusColor = isCrit
    ? 'var(--color-ledger-red)'
    : isWarn
    ? 'var(--color-brass)'
    : 'var(--color-ledger-green)';

  // Helper to convert meter angle to (x, y) coordinates with radius r from (70, 60)
  const getMeterPoint = (deg: number, r: number = 50) => {
    const rad = (deg * Math.PI) / 180;
    return {
      x: Number((70 + r * Math.sin(rad)).toFixed(1)),
      y: Number((60 - r * Math.cos(rad)).toFixed(1)),
    };
  };

  const warnRatio = Math.min(1, Math.max(0, (warnThreshold - min) / (max - min || 1)));
  const critRatio = Math.min(1, Math.max(0, (critThreshold - min) / (max - min || 1)));

  const pStart = getMeterPoint(startAngle);
  const pWarn = getMeterPoint(startAngle + warnRatio * (endAngle - startAngle));
  const pCrit = getMeterPoint(startAngle + critRatio * (endAngle - startAngle));
  const pEnd = getMeterPoint(endAngle);

  return (
    <div
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '8px',
        background: 'var(--color-paper)',
        border: '1.5px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        boxShadow: '1.5px 1.5px 0 var(--color-rule)',
        fontFamily: 'var(--font-precision)',
        userSelect: 'none',
        width: width,
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          fontSize: '10px',
          fontWeight: 800,
          color: 'var(--color-ink)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          marginBottom: '2px',
        }}
      >
        {label}
      </div>

      {/* Analog Meter Face */}
      <svg
        width={width - 16}
        height={height - 35}
        viewBox="0 0 140 65"
        style={{ overflow: 'visible' }}
      >
        {/* Dial Face Background Arc */}
        <path
          d={`M ${pStart.x} ${pStart.y} A 50 50 0 0 1 ${pEnd.x} ${pEnd.y}`}
          fill="none"
          stroke="var(--color-rule)"
          strokeWidth="6"
          strokeLinecap="round"
        />

        {/* Safe Zone (Green) */}
        <path
          d={`M ${pStart.x} ${pStart.y} A 50 50 0 0 1 ${pWarn.x} ${pWarn.y}`}
          fill="none"
          stroke="var(--color-ledger-green)"
          strokeWidth="4"
          strokeLinecap="round"
          opacity={0.8}
        />

        {/* Warning Zone (Yellow/Brass) */}
        <path
          d={`M ${pWarn.x} ${pWarn.y} A 50 50 0 0 1 ${pCrit.x} ${pCrit.y}`}
          fill="none"
          stroke="var(--color-brass)"
          strokeWidth="4"
          opacity={0.85}
        />

        {/* Critical Red Zone */}
        <path
          d={`M ${pCrit.x} ${pCrit.y} A 50 50 0 0 1 ${pEnd.x} ${pEnd.y}`}
          fill="none"
          stroke="var(--color-ledger-red)"
          strokeWidth="4"
          strokeLinecap="round"
          opacity={0.9}
        />

        {/* Tick marks */}
        {[0, 25, 50, 75, 100].map((t) => {
          const tickRatio = t / 100;
          const tickAngle = (startAngle + tickRatio * (endAngle - startAngle)) * (Math.PI / 180);
          const x1 = 70 + 44 * Math.sin(tickAngle);
          const y1 = 60 - 44 * Math.cos(tickAngle);
          const x2 = 70 + 52 * Math.sin(tickAngle);
          const y2 = 60 - 52 * Math.cos(tickAngle);
          return (
            <line
              key={t}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="var(--color-ink-soft)"
              strokeWidth={t === 0 || t === 50 || t === 100 ? '1.5' : '1'}
            />
          );
        })}

        {/* Needle */}
        <g transform={`translate(70, 60) rotate(${angle})`}>
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="-48"
            stroke="var(--color-rule)"
            strokeWidth="2.5"
            strokeLinecap="round"
            style={{ transition: 'transform 250ms ease-out' }}
          />
          <line
            x1="0"
            y1="-20"
            x2="0"
            y2="-48"
            stroke={statusColor}
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          {/* Pivot cap */}
          <circle cx="0" cy="0" r="5" fill="var(--color-win-yellow)" stroke="var(--color-rule)" strokeWidth="1.5" />
          <circle cx="0" cy="0" r="2" fill="var(--color-rule)" />
        </g>
      </svg>

      {/* Value read-out */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '2px',
          marginTop: '2px',
        }}
      >
        <span
          className="tabular-nums"
          style={{
            fontSize: '13px',
            fontWeight: 800,
            color: statusColor,
          }}
        >
          {typeof value === 'number' ? value.toFixed(1) : value}
        </span>
        <span style={{ fontSize: '10px', color: 'var(--color-ink-soft)' }}>
          {unit}
        </span>
      </div>
    </div>
  );
};
