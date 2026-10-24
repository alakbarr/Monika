// ==============================================================================
// File: src/components/ui/WindowFrame.tsx
// Description: Unboxed Swiss Editorial Section Container with Toolbar & ErrorBoundary
// ==============================================================================

import React, { useState } from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { Maximize2, Minimize2, X } from 'lucide-react';

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
  toolbar?: React.ReactNode;
  statusBar?: React.ReactNode;
  padding?: string;
  defaultCollapsed?: boolean;
  isFocused?: boolean;
  onFocus?: () => void;
}

export const WindowFrame: React.FC<WindowFrameProps> = ({
  title,
  icon,
  children,
  className = '',
  style,
  bodyStyle,
  onClose,
  actions,
  toolbar,
  statusBar,
  padding = '16px 0',
  defaultCollapsed = false,
  onFocus,
}) => {
  const [isCollapsed] = useState(defaultCollapsed);
  const [isMaximized, setIsMaximized] = useState(false);

  return (
    <section
      className={`editorial-section swiss-crosshair ${className}`}
      onClick={onFocus}
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: isMaximized ? 'var(--color-canvas)' : 'transparent',
        borderTop: '1px solid var(--color-rule)',
        ...(isMaximized
          ? {
              position: 'fixed',
              inset: '16px',
              zIndex: 999,
              padding: '24px',
              border: '1px solid var(--color-rule-strong)',
              boxShadow: 'var(--shadow-modal)',
            }
          : {}),
        ...style,
      }}
    >
      {/* Editorial Section Header */}
      <header
        className="editorial-section-header"
        style={{
          padding: '12px 0',
          borderBottom: '1px solid var(--color-rule)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
          {icon && (
            <span style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--color-ink-muted)' }}>
              {icon}
            </span>
          )}
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.09em',
              color: 'var(--color-ink)',
            }}
          >
            {title}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {actions}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsMaximized((prev) => !prev);
            }}
            title={isMaximized ? 'Exit Fullscreen' : 'Expand Section'}
            aria-label={isMaximized ? 'Exit Fullscreen' : 'Expand Section'}
            style={{
              background: 'transparent',
              border: '1px solid var(--color-rule)',
              color: 'var(--color-ink-muted)',
              width: '24px',
              height: '24px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 'var(--radius-xs)',
              cursor: 'pointer',
            }}
          >
            {isMaximized ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
          {onClose && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClose();
              }}
              title="Close"
              aria-label="Close"
              style={{
                background: 'transparent',
                border: '1px solid var(--color-rule)',
                color: 'var(--color-ink-muted)',
                width: '24px',
                height: '24px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 'var(--radius-xs)',
                cursor: 'pointer',
              }}
            >
              <X size={12} />
            </button>
          )}
        </div>
      </header>

      {/* Optional Toolbar */}
      {toolbar && !isCollapsed && (
        <div
          style={{
            padding: '10px 0',
            borderBottom: '1px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            flexWrap: 'wrap',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
          }}
        >
          {toolbar}
        </div>
      )}

      {/* Body */}
      {!isCollapsed && (
        <>
          <div
            style={{
              padding,
              flex: 1,
              overflowY: isMaximized ? 'auto' : undefined,
              ...bodyStyle,
            }}
          >
            <ErrorBoundary>{children}</ErrorBoundary>
          </div>

          {statusBar && (
            <footer
              style={{
                padding: '8px 0',
                borderTop: '1px solid var(--color-rule)',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-ink-muted)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              {statusBar}
            </footer>
          )}
        </>
      )}
    </section>
  );
};
