// ==============================================================================
// File: src/components/ui/WindowFrame.tsx
// Description: Interactive Retro Window Frame with minimize, maximize, and sound
// ==============================================================================

import React, { useState } from 'react';
import { sounds } from '../../lib/soundEffects';

export type WindowVariant = 'blue' | 'yellow' | 'salmon' | 'coral' | 'green' | 'gray';

interface WindowFrameProps {
  title: React.ReactNode;
  icon?: React.ReactNode;
  variant?: WindowVariant;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  bodyStyle?: React.CSSProperties;
  showControls?: boolean;
  onClose?: () => void;
  actions?: React.ReactNode;
  statusBar?: React.ReactNode;
  padding?: string;
  defaultCollapsed?: boolean;
}

const variantClassMap: Record<WindowVariant, string> = {
  blue: '',
  yellow: 'win-titlebar--yellow',
  salmon: 'win-titlebar--salmon',
  coral: 'win-titlebar--coral',
  green: 'win-titlebar--green',
  gray: 'win-titlebar--gray',
};

export const WindowFrame: React.FC<WindowFrameProps> = ({
  title,
  icon,
  variant = 'blue',
  children,
  className = '',
  style,
  bodyStyle,
  showControls = true,
  onClose,
  actions,
  statusBar,
  padding = '16px',
  defaultCollapsed = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);
  const [isMaximized, setIsMaximized] = useState(false);

  const handleMinimize = (e: React.MouseEvent) => {
    e.stopPropagation();
    sounds.playClick('shutter');
    setIsCollapsed(!isCollapsed);
  };

  const handleMaximize = (e: React.MouseEvent) => {
    e.stopPropagation();
    sounds.playClick('shutter');
    setIsMaximized(!isMaximized);
    if (isCollapsed) setIsCollapsed(false);
  };

  const handleClose = (e: React.MouseEvent) => {
    e.stopPropagation();
    sounds.playClick('toggle');
    if (onClose) onClose();
  };

  return (
    <div
      className={`win-window ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: 'var(--color-paper-raised)',
        border: '2px solid var(--color-rule)',
        borderRadius: 'var(--radius-card)',
        boxShadow: isMaximized ? '8px 8px 0 var(--color-rule)' : 'var(--shadow-card)',
        transition: 'box-shadow 0.2s ease',
        ...(isMaximized
          ? {
              position: 'fixed',
              top: '16px',
              left: '16px',
              right: '16px',
              bottom: '16px',
              zIndex: 999,
              maxHeight: 'calc(100vh - 32px)',
            }
          : {}),
        ...style,
      }}
    >
      {/* Title bar */}
      <div
        className={`win-titlebar ${variantClassMap[variant]}`}
        style={{
          userSelect: 'none',
          cursor: 'default',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
          {icon && (
            <span style={{ display: 'inline-flex', alignItems: 'center', flexShrink: 0 }}>
              {icon}
            </span>
          )}
          <span
            style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontWeight: 'bold',
            }}
          >
            {title}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {actions}
          {showControls && (
            <div className="win-controls" aria-hidden="true">
              <button
                type="button"
                className="win-control-btn"
                onClick={handleMinimize}
                title={isCollapsed ? 'Restore Window' : 'Minimize Window'}
              >
                _
              </button>
              <button
                type="button"
                className="win-control-btn"
                onClick={handleMaximize}
                title={isMaximized ? 'Restore Size' : 'Maximize Window'}
              >
                □
              </button>
              {onClose && (
                <button
                  type="button"
                  className="win-control-btn"
                  onClick={handleClose}
                  title="Close Window"
                  style={{ color: 'var(--color-ink)' }}
                >
                  ×
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Window Body (collapsible) */}
      {!isCollapsed && (
        <>
          <div
            style={{
              padding,
              flex: 1,
              background: 'var(--color-paper-raised)',
              overflowY: isMaximized ? 'auto' : undefined,
              ...bodyStyle,
            }}
          >
            {children}
          </div>

          {/* Window Status Bar */}
          {statusBar && (
            <div
              style={{
                padding: '4px 10px',
                borderTop: '2px solid var(--color-rule)',
                background: 'var(--color-paper)',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-ink-soft)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              {statusBar}
            </div>
          )}
        </>
      )}
    </div>
  );
};
