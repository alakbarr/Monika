import React, { useState } from 'react';
import { ChevronDown, ChevronUp, X } from 'lucide-react';

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

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  style,
  header,
  title,
  icon,
  variant = 'blue',
  footer,
  padding = '16px 18px',
  onClick,
  onClose,
  collapsible = false,
}) => {
  const isInteractive = !!onClick;
  const [isCollapsed, setIsCollapsed] = useState(false);

  const accentBorder =
    variant === 'coral'
      ? 'var(--color-loss-border)'
      : variant === 'green'
      ? 'var(--color-gain-border)'
      : 'var(--color-glass-border)';

  return (
    <section
      className={`liquid-glass-panel editorial-section swiss-crosshair ${className}`}
      onClick={onClick}
      style={{
        position: 'relative',
        background: 'var(--color-glass-surface)',
        backdropFilter: 'var(--glass-blur-panel)',
        WebkitBackdropFilter: 'var(--glass-blur-panel)',
        border: `1px solid ${accentBorder}`,
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-glass-panel)',
        cursor: isInteractive ? 'pointer' : 'default',
        ...style,
      }}
    >
      {(header || title) && (
        <header
          className="editorial-section-header"
          style={{
            padding: '12px 18px',
            borderBottom: isCollapsed ? 'none' : '1px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
            {icon && (
              <span style={{ color: 'var(--color-ink-muted)', display: 'inline-flex', alignItems: 'center' }}>
                {icon}
              </span>
            )}
            {title ? (
              <h3
                style={{
                  margin: 0,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.09em',
                  color: 'var(--color-ink-secondary)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {title}
              </h3>
            ) : (
              <div style={{ flex: 1, minWidth: 0 }}>{header}</div>
            )}
          </div>

          {(collapsible || onClose) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {collapsible && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsCollapsed((prev) => !prev);
                  }}
                  aria-label={isCollapsed ? 'Expand Section' : 'Collapse Section'}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--color-rule)',
                    color: 'var(--color-ink-muted)',
                    width: '24px',
                    height: '24px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    borderRadius: 'var(--radius-xs)',
                  }}
                >
                  {isCollapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
                </button>
              )}
              {onClose && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onClose();
                  }}
                  aria-label="Close Section"
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--color-rule)',
                    color: 'var(--color-ink-muted)',
                    width: '24px',
                    height: '24px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    borderRadius: 'var(--radius-xs)',
                  }}
                >
                  <X size={13} />
                </button>
              )}
            </div>
          )}
        </header>
      )}

      {!isCollapsed && (
        <>
          <div style={{ padding }}>{children}</div>
          {footer && (
            <footer
              style={{
                padding: '10px 0',
                borderTop: '1px solid var(--color-rule)',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-ink-muted)',
              }}
            >
              {footer}
            </footer>
          )}
        </>
      )}
    </section>
  );
};
