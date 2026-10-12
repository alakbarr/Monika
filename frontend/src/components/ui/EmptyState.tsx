// ==============================================================================
// File: src/components/ui/EmptyState.tsx
// Description: Reusable Dashboard Empty State with Teletype Stamp & Action Slot
// ==============================================================================

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
          padding: '14px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '12px',
          fontFamily: 'var(--font-precision)',
          background: 'var(--color-paper-subtle)',
          borderBottom: '1px dashed var(--color-rule)',
          boxSizing: 'border-box',
          ...style,
        }}
      >
        {icon && (
          <span style={{ display: 'inline-flex', color: 'var(--color-ink-soft)', flexShrink: 0 }}>
            {icon}
          </span>
        )}
        <span
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 800,
            color: 'var(--color-ink)',
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          [ {title} ]
        </span>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--color-ink-soft)',
          }}
        >
          {message}
        </span>
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
        padding: '36px 20px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        fontFamily: 'var(--font-precision)',
        ...style,
      }}
    >
      {icon && (
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-sm)',
            background: 'var(--color-paper)',
            border: '2px solid var(--color-rule)',
            boxShadow: '2px 2px 0 var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--color-ink-soft)',
            marginBottom: '14px',
          }}
        >
          {icon}
        </div>
      )}

      <div
        style={{
          fontSize: 'var(--text-body-sm)',
          fontWeight: 800,
          color: 'var(--color-ink)',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          marginBottom: '6px',
        }}
      >
        [ {title} ]
      </div>

      <div
        style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--color-ink-soft)',
          maxWidth: '360px',
          lineHeight: 1.5,
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
