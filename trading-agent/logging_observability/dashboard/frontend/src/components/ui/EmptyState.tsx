// ==============================================================================
// File: src/components/ui/EmptyState.tsx
// Description: Reusable Retro OS Empty State with Teletype Stamp & Action Slot
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
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'CLEAR LEDGER',
  message,
  icon,
  actionLabel,
  onAction,
  style,
}) => {
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
