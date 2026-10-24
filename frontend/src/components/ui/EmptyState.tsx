import React from 'react';
import { TypewriterButton } from './TypewriterButton';

interface EmptyStateProps {
  title?: string;
  message: string;
  icon?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  style?: React.CSSProperties;
  compact?: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'CLEAR LEDGER',
  message,
  icon,
  actionLabel,
  onAction,
  style,
  compact = false,
}) => {
  if (compact) {
    return (
      <div
        style={{
          padding: '16px 0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          fontFamily: 'var(--font-mono)',
          borderBottom: '1px solid var(--color-rule)',
          boxSizing: 'border-box',
          ...style,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {icon && (
            <span style={{ display: 'inline-flex', color: 'var(--color-ink-muted)', flexShrink: 0 }}>
              {icon}
            </span>
          )}
          <span
            style={{
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              color: 'var(--color-ink)',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
            }}
          >
            {title}
          </span>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-muted)' }}>
            — {message}
          </span>
        </div>
        {actionLabel && onAction && (
          <TypewriterButton size="sm" onClick={onAction}>
            {actionLabel}
          </TypewriterButton>
        )}
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '48px 24px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        borderTop: '1px solid var(--color-rule)',
        borderBottom: '1px solid var(--color-rule)',
        ...style,
      }}
    >
      {icon && (
        <div
          style={{
            color: 'var(--color-ink-muted)',
            marginBottom: '12px',
          }}
        >
          {icon}
        </div>
      )}

      <div
        style={{
          fontFamily: 'var(--font-editorial)',
          fontSize: 'var(--text-title-lg)',
          color: 'var(--color-ink)',
          marginBottom: '6px',
        }}
      >
        {title}
      </div>

      <div
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: 'var(--text-body-sm)',
          color: 'var(--color-ink-muted)',
          maxWidth: '400px',
          lineHeight: 1.55,
          marginBottom: actionLabel ? '16px' : '0',
        }}
      >
        {message}
      </div>

      {actionLabel && onAction && (
        <TypewriterButton size="sm" onClick={onAction}>
          {actionLabel}
        </TypewriterButton>
      )}
    </div>
  );
};
