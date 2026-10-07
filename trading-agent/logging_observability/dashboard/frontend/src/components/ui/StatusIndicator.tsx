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
      title={tooltip || `${label ? `${label}: ` : ''}${config.labelText}`}
      aria-label={`${label ? `${label}: ` : ''}${config.labelText}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      <span
        style={{
          width: dotSize + 3,
          height: dotSize + 3,
          borderRadius: '2px',
          backgroundColor: config.color,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1.5px solid var(--color-rule)',
          boxShadow: '1px 1px 0 var(--color-rule)',
          fontSize: '9px',
          fontWeight: 900,
          color: status === 'connecting' || status === 'unknown' ? '#1C1917' : '#FFFFFF',
          lineHeight: 1,
        }}
        aria-hidden="true"
      >
        {status === 'connected' ? '●' : status === 'disconnected' ? '×' : status === 'connecting' ? '~' : '?'}
      </span>
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
