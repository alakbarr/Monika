import React from 'react';

type StatusVariant = 'connected' | 'disconnected' | 'unknown' | 'connecting';

interface StatusIndicatorProps {
  status: StatusVariant;
  label?: string;
  size?: 'sm' | 'md';
  tooltip?: string;
}

const statusConfig: Record<StatusVariant, { color: string; labelText: string }> = {
  connected: { color: 'var(--color-win-green)', labelText: 'ONLINE' },
  disconnected: { color: 'var(--color-win-coral)', labelText: 'OFFLINE' },
  unknown: { color: 'var(--color-win-gray)', labelText: 'UNKNOWN' },
  connecting: { color: 'var(--color-win-yellow)', labelText: 'CONNECTING' },
};

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({ 
  status, 
  label, 
  size = 'sm',
  tooltip 
}) => {
  const config = statusConfig[status] || statusConfig.unknown;
  const dotSize = size === 'sm' ? 8 : 10;
  const fontSize = size === 'sm' ? 'var(--text-xs)' : 'var(--text-body-sm)';

  return (
    <div 
      title={tooltip}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      <span
        style={{
          width: dotSize,
          height: dotSize,
          borderRadius: '2px',
          backgroundColor: config.color,
          display: 'inline-block',
          border: '1.5px solid var(--color-rule)',
          boxShadow: '1px 1px 0 var(--color-rule)',
        }}
      />
      {label && (
        <span
          style={{
            color: 'var(--color-ink)',
            fontSize,
            fontWeight: 'var(--weight-bold)',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
};
