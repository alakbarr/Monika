import React from 'react';
import { TypewriterButton } from './TypewriterButton';

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  actionSummary: string;
  details?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  title,
  actionSummary,
  details,
  confirmLabel = 'OK',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}) => {
  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        background: 'rgba(28, 25, 23, 0.75)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        fontFamily: 'var(--font-precision)',
      }}
    >
      <div
        className="win-window"
        style={{
          width: '100%',
          maxWidth: '460px',
          background: 'var(--color-paper-raised)',
          border: '2px solid var(--color-rule)',
          boxShadow: '4px 4px 0 var(--color-rule)',
          borderRadius: 'var(--radius-card)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Retro Dialog Title Bar */}
        <div
          id="confirm-modal-title"
          className="win-titlebar"
          style={{
            background: danger ? 'var(--color-win-coral)' : 'var(--color-win-blue)',
            color: 'var(--color-titlebar-text)',
            padding: '6px 10px',
            borderBottom: '2px solid var(--color-rule)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontWeight: 'bold',
            fontSize: 'var(--text-body-sm)',
          }}
        >
          <span>{title}</span>
          <div className="win-controls">
            <button
              type="button"
              className="win-control-btn"
              onClick={onCancel}
              title="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* Dialog Content */}
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
            {/* Retro icon circle */}
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                background: danger ? 'var(--color-win-coral)' : 'var(--color-win-yellow)',
                border: '2px solid var(--color-rule)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
                fontWeight: 900,
                color: '#1C1917',
                flexShrink: 0,
                boxShadow: '2px 2px 0 var(--color-rule)',
              }}
            >
              {danger ? '✕' : '!'}
            </div>

            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: 'var(--text-body-md)',
                  color: 'var(--color-ink)',
                  lineHeight: 1.5,
                  fontWeight: 'bold',
                  marginBottom: '6px',
                }}
              >
                {actionSummary}
              </div>
              {details && (
                <div style={{ fontSize: 'var(--text-body-sm)', color: 'var(--color-ink-soft)', lineHeight: 1.4 }}>
                  {details}
                </div>
              )}
            </div>
          </div>

          {/* Action Buttons Row (OK / Cancel) */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', paddingTop: '10px' }}>
            <TypewriterButton variant="secondary" onClick={onCancel}>
              {cancelLabel}
            </TypewriterButton>
            <TypewriterButton variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>
              {confirmLabel}
            </TypewriterButton>
          </div>
        </div>
      </div>
    </div>
  );
};
