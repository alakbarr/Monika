import React from 'react';

type StatusVariant = 'connected' | 'disconnected' | 'unknown' | 'connecting';

interface StatusIndicatorProps {
  status: StatusVariant;
  label?: string;
  size?: 'sm' | 'md';
  tooltip?: string;
}

const statusConfig: Record<StatusVariant, { color: string; labelText: string }> = {
  connected: { color: 'var(--color-gain)', labelText: 'ONLINE' },
  disconnected: { color: 'var(--color-loss)', labelText: 'OFFLINE' },
  unknown: { color: 'var(--color-ink-muted)', labelText: 'UNKNOWN' },
  connecting: { color: 'var(--color-warn)', labelText: 'SYNCING' },
};

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  size = 'sm',
  tooltip,
}) => {
  const config = statusConfig[status] || statusConfig.unknown;
  const dotSize = size === 'sm' ? 6 : 8;
  const fontSize = size === 'sm' ? 'var(--text-xs)' : 'var(--text-body-sm)';

  return (
    <div
      title={tooltip || `${label ? `${label}: ` : ''}${config.labelText}`}
      aria-label={`${label ? `${label}: ` : ''}${config.labelText}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '7px',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <span
        style={{
          width: dotSize,
          height: dotSize,
          borderRadius: '0px',
          backgroundColor: config.color,
          display: 'inline-block',
          flexShrink: 0,
        }}
        aria-hidden="true"
      />
      {label && (
        <span
          style={{
            color: 'var(--color-ink-secondary)',
            fontSize,
            fontWeight: 500,
            letterSpacing: '0.03em',
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
};
