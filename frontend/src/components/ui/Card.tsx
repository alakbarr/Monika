import React, { useState } from 'react';
import { sounds } from '../../lib/soundEffects';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  header?: React.ReactNode;
  title?: string;
  icon?: React.ReactNode;
  variant?: 'blue' | 'yellow' | 'salmon' | 'coral' | 'green' | 'gray';
  footer?: React.ReactNode;
  padding?: string;
  onClick?: () => void;
  onClose?: () => void;
  elevated?: boolean;
  collapsible?: boolean;
}

const variantClassMap: Record<string, string> = {
  blue: 'win-titlebar--blue',
  yellow: 'win-titlebar--yellow',
  salmon: 'win-titlebar--salmon',
  coral: 'win-titlebar--coral',
  green: 'win-titlebar--green',
  gray: 'win-titlebar--gray',
};

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  style,
  header,
  title,
  icon,
  variant = 'blue',
  footer,
  padding = '16px',
  onClick,
  onClose,
  elevated = false,
  collapsible = true,
}) => {
  const isInteractive = !!onClick;
  const titleBarClass = variantClassMap[variant] || 'win-titlebar--blue';
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleMinimize = (e: React.MouseEvent) => {
    e.stopPropagation();
    sounds.playClick('shutter');
    setIsCollapsed((prev) => !prev);
  };

  const handleClose = (e: React.MouseEvent) => {
    e.stopPropagation();
    sounds.playClick('toggle');
    onClose?.();
  };

  return (
    <div
      className={`win-window ledger-card ${className}`}
      onClick={onClick}
      style={{
        position: 'relative',
        background: 'var(--color-paper-raised)',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        boxShadow: elevated ? 'var(--shadow-elevated)' : 'var(--shadow-card)',
        cursor: isInteractive ? 'pointer' : 'default',
        overflow: 'hidden',
        ...style,
      }}
    >
      {(header || title) && (
        <div
          className={`win-titlebar ${titleBarClass}`}
          style={{
            padding: '6px 12px',
            borderBottom: isCollapsed ? 'none' : '2px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: 'var(--text-body-sm)',
            fontWeight: 700,
            width: '100%',
            boxSizing: 'border-box',
            alignSelf: 'stretch',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
            {icon && <span>{icon}</span>}
            {title ? (
              <div style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {title}
              </div>
            ) : (
              <div style={{ flex: 1, minWidth: 0 }}>
                {header}
              </div>
            )}
          </div>
          <div className="win-controls" style={{ marginLeft: '8px' }}>
            {collapsible && (
              <button
                type="button"
                className="win-control-btn"
                onClick={handleMinimize}
                title={isCollapsed ? 'Expand Card' : 'Collapse Card'}
                aria-label={isCollapsed ? 'Expand Card' : 'Collapse Card'}
              >
                {isCollapsed ? '□' : '_'}
              </button>
            )}
            {onClose && (
              <button
                type="button"
                className="win-control-btn"
                onClick={handleClose}
                title="Close Card"
                aria-label="Close Card"
              >
                ×
              </button>
            )}
          </div>
        </div>
      )}

      {!isCollapsed && (
        <>
          <div style={{ padding }}>{children}</div>

          {footer && (
            <div
              style={{
                padding: `8px ${padding}`,
                borderTop: '2px solid var(--color-rule)',
                background: 'var(--color-paper)',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-ink-soft)',
              }}
            >
              {footer}
            </div>
          )}
        </>
      )}
    </div>
  );
};
